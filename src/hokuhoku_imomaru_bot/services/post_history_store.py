"""
PostHistoryStore — いも丸の独り言（自律投稿、3b-1）の投稿履歴

DynamoDB `imomaru-bot-post-history`（PK `posted_date` = JST の YYYY-MM-DD#HH（実行の日と時）、TTL 30 日）。
1 実行 1 アイテム（3b-1 (ii) で全実行に広げたため日単位から実行単位へ。テーブル定義は同じ）。
件数が小さい（最大 100 件程度）ので読み出しは Scan で済ませる。

用途（設計書 §10-11 2026-09-20 / 09-21 追記、§10-15）:
- 同じ記憶から続けて作らない（重複キー: A = "A:<イベント日>:<残り日数>"、B〜D = "<タイプ>:<record_id>"）。
  頭脳が skip した候補も記録し、以後の実行（重複キーの期間）で同じ記憶を渡さない
- 1 日の独り言の件数（公開・頭脳呼び出し）を数える
- 直近の独り言の本文を頭脳に渡し、言い回しの重複を避ける
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, List, Optional, Set

import boto3

logger = logging.getLogger(__name__)

DEFAULT_TABLE_NAME = "imomaru-bot-post-history"
TTL_DAYS = 30

# 重複キーを効かせる日数（タイプ別。A はキーに残り日数を含むので期間は実質無関係）
KEY_DAYS_DEFAULT = 7
KEY_DAYS_BY_KIND = {"D": 14}
HISTORY_DAYS = max(KEY_DAYS_DEFAULT, *KEY_DAYS_BY_KIND.values())

STATUS_SKIPPED = "skipped"


def history_key(moment_jst: datetime) -> str:
    """PK の値: 実行の JST の日と時（YYYY-MM-DD#HH）"""
    return f"{moment_jst:%Y-%m-%d}#{moment_jst:%H}"


@dataclass
class HistoryEntry:
    posted_date: str                 # JST の YYYY-MM-DD#HH（3b-1 (i) の記録は YYYY-MM-DD）
    kind: str                        # "A" / "B" / "C" / "D"
    text: str                        # skip のときは空
    record_ids: List[str] = field(default_factory=list)
    dedupe_keys: List[str] = field(default_factory=list)
    buffer_post_id: str = ""
    status: str = "scheduled"        # scheduled / skipped

    @property
    def day(self) -> str:
        return self.posted_date[:10]

    @property
    def skipped(self) -> bool:
        return self.status == STATUS_SKIPPED


class PostHistoryStore:
    def __init__(self, table_name: str = DEFAULT_TABLE_NAME, table: Optional[Any] = None):
        self._table = table if table is not None else boto3.resource("dynamodb").Table(table_name)

    def _scan_all(self) -> List[HistoryEntry]:
        items: List[dict] = []
        kwargs: dict = {}
        while True:
            response = self._table.scan(**kwargs)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return [
            HistoryEntry(
                posted_date=str(item.get("posted_date", "")),
                kind=str(item.get("kind", "")),
                text=str(item.get("text", "")),
                record_ids=list(item.get("record_ids", []) or []),
                dedupe_keys=list(item.get("dedupe_keys", []) or []),
                buffer_post_id=str(item.get("buffer_post_id", "")),
                status=str(item.get("status", "scheduled")),
            )
            for item in items
        ]

    def load_recent(self, today: date, days: int = HISTORY_DAYS) -> List[HistoryEntry]:
        """today から days 日前以降の履歴（新しい順）"""
        since = (today - timedelta(days=days)).isoformat()
        entries = [e for e in self._scan_all() if e.day >= since]
        return sorted(entries, key=lambda e: e.posted_date, reverse=True)

    @staticmethod
    def used_keys(entries: List[HistoryEntry], today: Optional[date] = None) -> Set[str]:
        """期間内の重複キー（today を渡すとタイプ別の日数で絞る）"""
        keys: Set[str] = set()
        for entry in entries:
            for key in entry.dedupe_keys:
                days = KEY_DAYS_BY_KIND.get(key.split(":", 1)[0], KEY_DAYS_DEFAULT)
                if today is None or entry.day >= (today - timedelta(days=days)).isoformat():
                    keys.add(key)
        return keys

    @staticmethod
    def on_day(entries: List[HistoryEntry], day: date) -> List[HistoryEntry]:
        return [e for e in entries if e.day == day.isoformat()]

    def record(self, entry: HistoryEntry) -> None:
        item = {
            "posted_date": entry.posted_date,
            "kind": entry.kind,
            "text": entry.text,
            "record_ids": entry.record_ids,
            "dedupe_keys": entry.dedupe_keys,
            "buffer_post_id": entry.buffer_post_id,
            "status": entry.status,
            "ttl": int(time.time()) + TTL_DAYS * 24 * 60 * 60,
        }
        self._table.put_item(Item=item)
        logger.info(f"Autonomous post history recorded: {entry.posted_date} kind={entry.kind} status={entry.status}")
