"""
AutonomousSelector — 独り言（自律投稿、3b-1 (i)）の材料を推しの記憶から決定論で選ぶ

設計書 §10-11 2026-09-21 追記（素案タイプ A〜E）。候補の絞り込みは LLM に任せず Lambda で行い、
頭脳には「タイプ ＋ 候補の記憶」だけを渡す。

- 対象: facts の namespace（ListMemoryRecords）。preferences はタイプ D（3b-1 (ii)）で使う
- 除外: ファン視点・生活の細部（v19 タイプ E）。memory_filters.is_excluded_for_autonomous
- A 未来イベント: 本文の日付のうち今日より後で最も近い日（1〜MAX_DAYS_AHEAD 日後）。
  当日は対象外（22:00 公開の時点でイベントが終わっていることが多い。maijun 決定 2026-09-26）。
  同じイベント日の記憶をまとめて候補にし、重複キーは "A:<イベント日>:<残り日数>"（毎晩のカウントダウン）
- B 直近の出来事: イベント語を含み、抽出（createdAt）が RECENT_DAYS 日以内。今日以降の日付を含む記憶は除く。
  重複キーは "B:<record_id>"
- 優先 A > B。最初に候補が残ったタイプから最大 MAX_CANDIDATES 件
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

import boto3
from botocore.config import Config

from ..memory_filters import extract_dates, is_event, is_excluded_for_autonomous
from .daily_reporter import JST

logger = logging.getLogger(__name__)

DEFAULT_REGION = "ap-northeast-1"
MAX_PAGES = 5
PAGE_SIZE = 100
MAX_CANDIDATES = 3
MAX_DAYS_AHEAD = 14
RECENT_DAYS = 3


@dataclass
class MemoryCandidate:
    record_id: str
    text: str
    created_at: datetime             # aware。記憶が抽出された時刻（出来事の日時ではない）

    def to_brain(self) -> Dict[str, str]:
        return {
            "id": self.record_id,
            "text": self.text,
            "created_at": self.created_at.astimezone(JST).strftime("%Y-%m-%d %H:%M JST"),
        }


@dataclass
class AutonomousSelection:
    kind: str                                        # "A" / "B"
    candidates: List[MemoryCandidate]
    keys: Dict[str, str] = field(default_factory=dict)  # record_id → 重複キー
    days_left: Optional[int] = None
    event_date: Optional[date] = None

    def keys_for(self, record_ids: Iterable[str]) -> List[str]:
        keys: List[str] = []
        for record_id in record_ids:
            key = self.keys.get(record_id)
            if key and key not in keys:
                keys.append(key)
        return keys


def _parse_created_at(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def select_from(
    records: List[MemoryCandidate],
    now: datetime,
    used_keys: Set[str],
) -> Optional[AutonomousSelection]:
    """記憶の一覧から素案タイプと候補を選ぶ（純関数）。候補がなければ None"""
    today = now.astimezone(JST).date()
    usable = sorted(
        (r for r in records if r.text.strip() and not is_excluded_for_autonomous(r.text)),
        key=lambda r: r.created_at,
        reverse=True,
    )

    # A: 未来イベント
    by_event: Dict[date, List[MemoryCandidate]] = {}
    has_future_date: Set[str] = set()
    for record in usable:
        dates = extract_dates(record.text, record.created_at.astimezone(JST).year)
        if any(d >= today for d in dates):
            has_future_date.add(record.record_id)
        ahead = [d for d in dates if 1 <= (d - today).days <= MAX_DAYS_AHEAD]
        if ahead:
            by_event.setdefault(min(ahead), []).append(record)
    for event_date in sorted(by_event):
        days_left = (event_date - today).days
        key = f"A:{event_date.isoformat()}:{days_left}"
        if key in used_keys:
            continue
        candidates = by_event[event_date][:MAX_CANDIDATES]
        return AutonomousSelection(
            kind="A",
            candidates=candidates,
            keys={c.record_id: key for c in candidates},
            days_left=days_left,
            event_date=event_date,
        )

    # B: 直近の出来事（イベント系のみ）
    since = now - timedelta(days=RECENT_DAYS)
    recent = [
        r for r in usable
        if r.created_at >= since
        and is_event(r.text)
        and r.record_id not in has_future_date
        and f"B:{r.record_id}" not in used_keys
    ][:MAX_CANDIDATES]
    if recent:
        return AutonomousSelection(
            kind="B",
            candidates=recent,
            keys={c.record_id: f"B:{c.record_id}" for c in recent},
        )
    return None


class AutonomousSelector:
    """推しの記憶（facts）を一覧して独り言の材料を選ぶ。失敗時は例外（握りつぶしは呼び出し側）"""

    def __init__(
        self,
        memory_id: str,
        actor_id: str,
        region: str = DEFAULT_REGION,
        client: Optional[Any] = None,
    ):
        self._memory_id = memory_id
        self._actor_id = actor_id
        self._client = client or boto3.client(
            "bedrock-agentcore",
            region_name=region,
            config=Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 3}),
        )

    def list_facts(self) -> List[MemoryCandidate]:
        records: List[MemoryCandidate] = []
        kwargs: Dict[str, Any] = {
            "memoryId": self._memory_id,
            "namespace": f"/oshi/{self._actor_id}/facts/",
            "maxResults": PAGE_SIZE,
        }
        for _ in range(MAX_PAGES):
            response = self._client.list_memory_records(**kwargs)
            for summary in response.get("memoryRecordSummaries", []):
                created_at = _parse_created_at(summary.get("createdAt"))
                record_id = summary.get("memoryRecordId")
                if not record_id or created_at is None:
                    continue
                records.append(MemoryCandidate(
                    record_id=record_id,
                    text=str(summary.get("content", {}).get("text", "")),
                    created_at=created_at,
                ))
            token = response.get("nextToken")
            if not token:
                break
            kwargs["nextToken"] = token
        return records

    def select(self, now: datetime, used_keys: Set[str]) -> Optional[AutonomousSelection]:
        records = self.list_facts()
        selection = select_from(records, now, used_keys)
        logger.info(
            f"Autonomous candidates: facts={len(records)} "
            + (f"kind={selection.kind} candidates={len(selection.candidates)} days_left={selection.days_left}"
               if selection else "none")
        )
        return selection
