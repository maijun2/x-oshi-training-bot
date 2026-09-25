"""
AutonomousSelector / memory_filters / PostHistoryStore のユニットテスト（3b-1 自律投稿の材料選び）

設計書 §10-11 2026-09-21 追記の素案タイプ A（未来イベント）・B（直近の出来事）と、
除外（ファン視点・生活の細部）・重複キー・優先順位を検証する。
"""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.hokuhoku_imomaru_bot.memory_filters import (
    extract_dates,
    is_event,
    is_excluded_for_autonomous,
)
from src.hokuhoku_imomaru_bot.services.autonomous_selector import (
    AutonomousSelector,
    MemoryCandidate,
    select_from,
)
from src.hokuhoku_imomaru_bot.services.daily_reporter import JST
from src.hokuhoku_imomaru_bot.services.post_history_store import HistoryEntry, PostHistoryStore

NOW = datetime(2026, 9, 26, 21, 1, tzinfo=JST)


def _rec(record_id, text, created_days_ago=1.0):
    return MemoryCandidate(record_id=record_id, text=text, created_at=NOW - timedelta(days=created_days_ago))


BIRTHDAY = _rec("mem-birthday", "甘木ジュリは2026年9月28日に生誕祭を開催予定。チケットがまだ販売中。")
SPARK = _rec("mem-spark", "甘木ジュリは2026年9月23日にSPARK2026の2日目に出演した。", created_days_ago=2)


class TestMemoryFilters:
    def test_extract_dates_formats(self):
        text = "2026年9月28日に生誕祭。10月3日にもライブ。2026-10-10 に配信"
        assert extract_dates(text, 2026) == [date(2026, 9, 28), date(2026, 10, 10), date(2026, 10, 3)]

    def test_extract_dates_skips_invalid_and_duplicates(self):
        assert extract_dates("2月30日と9月28日と2026年9月28日", 2026) == [date(2026, 9, 28)]

    def test_year_less_date_does_not_match_inside_full_date(self):
        # 「2026年12月28日」の「2月28日」を年なしの日付として拾わない
        assert extract_dates("2026年12月28日", 2025) == [date(2026, 12, 28)]

    @pytest.mark.parametrize("text, excluded", [
        ("ユーザーは@juri_bigangelの投稿を閲覧している", True),   # ファン視点
        ("甘木ジュリは夜遅くまで寝られなかった", True),             # 睡眠（react と共通）
        ("甘木ジュリは腹痛で配信を休んだ", True),                   # 自律用の追加語
        ("甘木ジュリは家でヤモリを見つけた", True),
        ("甘木ジュリはアクセサリーを忘れた", True),
        ("甘木ジュリは2026年9月28日に生誕祭を開催予定", False),
    ])
    def test_excluded_for_autonomous(self, text, excluded):
        assert is_excluded_for_autonomous(text) is excluded

    def test_is_event(self):
        assert is_event("ラジオ大阪で収録した") is True
        assert is_event("汁なし坦々麺を食べた") is False


class TestSelectA:
    def test_future_event_countdown(self):
        selection = select_from([BIRTHDAY, SPARK], NOW, set())
        assert selection.kind == "A"
        assert selection.days_left == 2
        assert selection.event_date == date(2026, 9, 28)
        assert [c.record_id for c in selection.candidates] == ["mem-birthday"]
        assert selection.keys_for(["mem-birthday"]) == ["A:2026-09-28:2"]

    def test_day_before_is_tomorrow(self):
        selection = select_from([BIRTHDAY], NOW + timedelta(days=1), set())
        assert selection.days_left == 1

    def test_event_day_is_excluded(self):
        # 当日は対象外（maijun 決定 2026-09-26）。今日の日付を含む記憶は B にも回さない
        birthday_recent = _rec("mem-birthday", BIRTHDAY.text, created_days_ago=0.5)
        assert select_from([birthday_recent], NOW + timedelta(days=2), set()) is None

    def test_too_far_ahead_is_excluded(self):
        far = _rec("mem-far", "甘木ジュリは2026年10月11日にワンマンライブ予定")  # 15 日後
        assert select_from([far], NOW, set()) is None

    def test_same_event_records_are_grouped(self):
        other = _rec("mem-birthday-2", "甘木ジュリは9月28日の生誕祭の準備をしている", created_days_ago=3)
        selection = select_from([other, BIRTHDAY], NOW, set())
        assert [c.record_id for c in selection.candidates] == ["mem-birthday", "mem-birthday-2"]
        assert selection.keys_for(["mem-birthday", "mem-birthday-2"]) == ["A:2026-09-28:2"]

    def test_used_key_moves_to_next_event(self):
        later = _rec("mem-later", "甘木ジュリは2026年10月3日にライブ出演予定")
        selection = select_from([BIRTHDAY, later], NOW, {"A:2026-09-28:2"})
        assert selection.kind == "A"
        assert selection.event_date == date(2026, 10, 3)

    def test_excluded_record_is_not_used(self):
        sick = _rec("mem-sick", "甘木ジュリは2026年9月28日の生誕祭まで体調に気をつけている")
        assert select_from([sick], NOW, set()) is None


class TestSelectB:
    def test_recent_event_when_no_future_event(self):
        selection = select_from([SPARK], NOW, set())
        assert selection.kind == "B"
        assert selection.days_left is None
        assert selection.keys_for(["mem-spark"]) == ["B:mem-spark"]

    def test_a_has_priority_over_b(self):
        assert select_from([SPARK, BIRTHDAY], NOW, set()).kind == "A"

    def test_b_window_is_three_days(self):
        old = _rec("mem-old", "甘木ジュリは福岡のライブに出演した", created_days_ago=3.01)
        assert select_from([old], NOW, set()) is None

    def test_b_requires_event_words(self):
        food = _rec("mem-food", "甘木ジュリは汁なし坦々麺を食べた")
        assert select_from([food], NOW, set()) is None

    def test_b_used_key_is_skipped(self):
        assert select_from([SPARK], NOW, {"B:mem-spark"}) is None

    def test_b_caps_candidates_newest_first(self):
        records = [_rec(f"mem-{i}", f"甘木ジュリは配信{i}をした", created_days_ago=0.1 * (i + 1)) for i in range(5)]
        selection = select_from(records, NOW, set())
        assert [c.record_id for c in selection.candidates] == ["mem-0", "mem-1", "mem-2"]


class TestAutonomousSelector:
    def test_list_facts_paginates_and_parses(self):
        client = MagicMock()
        client.list_memory_records.side_effect = [
            {
                "memoryRecordSummaries": [
                    {"memoryRecordId": "mem-1", "content": {"text": "a"},
                     "createdAt": datetime(2026, 9, 25, 14, 59, tzinfo=timezone.utc)},
                    {"memoryRecordId": "mem-bad", "content": {"text": "b"}},  # createdAt なしは捨てる
                ],
                "nextToken": "t1",
            },
            {"memoryRecordSummaries": [
                {"memoryRecordId": "mem-2", "content": {"text": "c"}, "createdAt": "2026-09-24T10:00:00+09:00"},
            ]},
        ]
        selector = AutonomousSelector("mem-id", "juri_bigangel", client=client)

        records = selector.list_facts()

        assert [r.record_id for r in records] == ["mem-1", "mem-2"]
        first, second = client.list_memory_records.call_args_list
        assert first.kwargs["namespace"] == "/oshi/juri_bigangel/facts/"
        assert "nextToken" not in first.kwargs
        assert second.kwargs["nextToken"] == "t1"

    def test_select_uses_listed_records(self):
        client = MagicMock()
        client.list_memory_records.return_value = {"memoryRecordSummaries": [
            {"memoryRecordId": BIRTHDAY.record_id, "content": {"text": BIRTHDAY.text},
             "createdAt": BIRTHDAY.created_at},
        ]}
        selection = AutonomousSelector("mem-id", "juri_bigangel", client=client).select(NOW, set())
        assert selection.kind == "A"
        assert selection.candidates[0].to_brain()["id"] == "mem-birthday"


class TestPostHistoryStore:
    def test_load_recent_filters_and_sorts(self):
        table = MagicMock()
        table.scan.side_effect = [
            {"Items": [
                {"posted_date": "2026-09-18", "kind": "B", "text": "old", "dedupe_keys": ["B:x"]},
                {"posted_date": "2026-09-24", "kind": "A", "text": "t24", "dedupe_keys": ["A:2026-09-28:4"]},
            ], "LastEvaluatedKey": {"posted_date": "2026-09-24"}},
            {"Items": [{"posted_date": "2026-09-25", "kind": "A", "text": "t25", "dedupe_keys": ["A:2026-09-28:3"]}]},
        ]
        store = PostHistoryStore(table=table)

        entries = store.load_recent(date(2026, 9, 26), days=7)

        assert [e.posted_date for e in entries] == ["2026-09-25", "2026-09-24"]
        assert store.used_keys(entries) == {"A:2026-09-28:3", "A:2026-09-28:4"}

    def test_record_puts_item_with_ttl(self):
        table = MagicMock()
        PostHistoryStore(table=table).record(HistoryEntry(
            posted_date="2026-09-26", kind="A", text="t", record_ids=["mem-1"],
            dedupe_keys=["A:2026-09-28:2"], buffer_post_id="p1",
        ))
        item = table.put_item.call_args.kwargs["Item"]
        assert item["posted_date"] == "2026-09-26"
        assert item["dedupe_keys"] == ["A:2026-09-28:2"]
        assert item["ttl"] > 0
