"""
PostHistoryStore — いも丸の独り言（自律投稿、3b-1）の投稿履歴

DynamoDB `imomaru-bot-post-history`（PK `posted_date` = JST の YYYY-MM-DD、TTL 30 日）。
独り言は 1 日 1 件なので 1 日 1 アイテム。件数が小さい（最大 30 件程度）ので読み出しは Scan 1 回で済ませる。

用途（設計書 §10-11 2026-09-20 / 09-21 追記）:
- 同じ記憶から続けて作らない（重複キー: A = "A:<イベント日>:<残り日数>"、B = "B:<record_id>"）
- 直近の独り言の本文を頭脳に渡し、言い回しの重複を避ける
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, List, Optional, Set

import boto3

logger = logging.getLogger(__name__)

DEFAULT_TABLE_NAME = "imomaru-bot-post-history"
TTL_DAYS = 30


@dataclass
class HistoryEntry:
    posted_date: str                 # JST の YYYY-MM-DD
    kind: str                        # "A" / "B"
    text: str
    record_ids: List[str] = field(default_factory=list)
    dedupe_keys: List[str] = field(default_factory=list)
    buffer_post_id: str = ""


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
            )
            for item in items
        ]

    def load_recent(self, today: date, days: int) -> List[HistoryEntry]:
        """today から days 日前以降の履歴（新しい順）"""
        since = (today - timedelta(days=days)).isoformat()
        entries = [e for e in self._scan_all() if e.posted_date >= since]
        return sorted(entries, key=lambda e: e.posted_date, reverse=True)

    @staticmethod
    def used_keys(entries: List[HistoryEntry]) -> Set[str]:
        return {key for e in entries for key in e.dedupe_keys}

    def record(self, entry: HistoryEntry) -> None:
        item = {
            "posted_date": entry.posted_date,
            "kind": entry.kind,
            "text": entry.text,
            "record_ids": entry.record_ids,
            "dedupe_keys": entry.dedupe_keys,
            "buffer_post_id": entry.buffer_post_id,
            "ttl": int(time.time()) + TTL_DAYS * 24 * 60 * 60,
        }
        self._table.put_item(Item=item)
        logger.info(f"Autonomous post history recorded: {entry.posted_date} kind={entry.kind}")
