"""
AutonomousSelector / memory_filters / PostHistoryStore のユニットテスト（3b-1 自律投稿の材料選び）

設計書 §10-11 2026-09-21 追記の素案タイプ A（未来イベント）・B（直近の出来事）・
C（進行中・これからの活動）・D（好み・小ネタ）と、除外（ファン視点・生活の細部）・重複キー・優先順位を検証する。
"""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import json

from src.hokuhoku_imomaru_bot.memory_filters import (
    extract_dates,
    is_event,
    is_excluded_for_autonomous,
    is_excluded_preference_for_autonomous,
    preference_parts,
    preference_text,
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

    def test_too_far_ahead_is_not_a(self):
        # 15 日後は A のカウントダウンにしない。告知なので C（これからの活動）に回る
        far = _rec("mem-far", "甘木ジュリは2026年10月11日にワンマンライブ予定")
        assert select_from([far], NOW, set()).kind == "C"

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

    def test_b_excludes_announcements(self):
        # 日付なし・月だけの告知は「終わった出来事」ではない（09-28 の本番で B に入っていた）
        tower = _rec("mem-tower", "甘木ジュリはタワーレコードでのライブを5箇所で開催することが決定しており", 0.2)
        campaign = _rec("mem-campaign", "甘木ジュリは2026年10月・11月にキャンペーンを開催予定", 0.2)
        selection = select_from([tower, campaign], NOW, set())
        assert selection.kind == "C"
        assert [c.record_id for c in selection.candidates] == ["mem-tower", "mem-campaign"]

    def test_b_caps_candidates_newest_first(self):
        records = [_rec(f"mem-{i}", f"甘木ジュリは配信{i}をした", created_days_ago=0.1 * (i + 1)) for i in range(5)]
        selection = select_from(records, NOW, set())
        assert [c.record_id for c in selection.candidates] == ["mem-0", "mem-1", "mem-2"]


class TestSelectC:
    def test_ongoing_effort(self):
        selection = select_from([_rec("mem-song", "甘木ジュリはもっと上手く歌えるようになりたいという向上心を持っている", 10)],
                                NOW, set())
        assert selection.kind == "C"
        assert selection.keys_for(["mem-song"]) == ["C:mem-song"]

    def test_b_has_priority_over_c(self):
        tower = _rec("mem-tower", "甘木ジュリはタワーレコードでのライブ開催が決定", 0.2)
        assert select_from([tower, SPARK], NOW, set()).kind == "B"

    def test_window_is_fourteen_days(self):
        old = _rec("mem-old", "甘木ジュリは小顔の体操をやっている", created_days_ago=14.01)
        assert select_from([old], NOW, set()) is None

    def test_stale_dated_state_is_excluded(self):
        # 「9/19 時点で〜つもり」のように日付がすべて 3 日より前なら古い状態として外す
        stale = _rec("mem-stale", "甘木ジュリは2026年9月19日時点で、作業が落ち着いたら挑戦するつもり", 7)
        fresh = _rec("mem-fresh", "甘木ジュリは2026年9月23日時点で、新曲の練習をしている", 3)
        selection = select_from([stale, fresh], NOW, set())
        assert [c.record_id for c in selection.candidates] == ["mem-fresh"]

    def test_past_event_is_not_c(self):
        # イベント語を含む終わった出来事は B の担当（期間外でも C に回さない）
        past = _rec("mem-past", "甘木ジュリは配信の準備をして2026年9月24日に配信した", 5)
        assert select_from([past], NOW, set()) is None

    def test_event_day_is_not_c(self):
        today_event = _rec("mem-today", "甘木ジュリは2026年9月26日のライブの準備をしている", 1)
        assert select_from([today_event], NOW, set()) is None

    def test_a_record_is_not_c(self):
        # A の候補（イベント日のキーが使用済み）を C に回して同じ話題を繰り返さない
        prep = _rec("mem-prep", "甘木ジュリは2026年9月28日の生誕祭の準備をしている", 1)
        assert select_from([prep], NOW, {"A:2026-09-28:2"}) is None

    def test_used_key_is_skipped(self):
        song = _rec("mem-song", "甘木ジュリは歌の練習をしている", 1)
        assert select_from([song], NOW, {"C:mem-song"}) is None


def _pref(record_id, preference, context="ユーザーが自身の投稿で好きと述べている", created_days_ago=5.0):
    text = json.dumps({"context": context, "preference": preference, "categories": ["food"]}, ensure_ascii=False)
    return _rec(record_id, text, created_days_ago)


class TestSelectD:
    def test_preference_is_last_resort(self):
        burger = _pref("mem-burger", "バーガーキングのマッシュルームワッパーがとても好き")
        selection = select_from([], NOW, set(), [burger])
        assert selection.kind == "D"
        assert selection.candidates[0].text == "バーガーキングのマッシュルームワッパーがとても好き"
        assert selection.keys_for(["mem-burger"]) == ["D:mem-burger"]

    def test_c_has_priority_over_d(self):
        song = _rec("mem-song", "甘木ジュリは歌の練習をしている", 1)
        assert select_from([song], NOW, set(), [_pref("mem-burger", "ワッパーが好き")]).kind == "C"

    @pytest.mark.parametrize("preference, context", [
        ("ヤモリなどの小動物が苦手", "ユーザーは怖がっている"),
        ("チェキの裏面メッセージは隠して投稿してほしい", "ユーザーはお願いしている"),
        ("AIとの会話には不満を感じる", "ユーザーは述べている"),
        ("アイドルを強く推している", "ユーザーは甘木ジュリの投稿を繰り返し閲覧・転載している"),
        ("フォロワーとの交流を大切にしている", "就寝前に挨拶する習慣がある"),
    ])
    def test_excluded_preferences(self, preference, context):
        assert select_from([], NOW, set(), [_pref("mem-x", preference, context)]) is None

    def test_used_key_is_skipped(self):
        assert select_from([], NOW, {"D:mem-burger"}, [_pref("mem-burger", "ワッパーが好き")]) is None

    def test_unreadable_record_is_skipped(self):
        assert select_from([], NOW, set(), [_rec("mem-list", "[1, 2]")]) is None


class TestPreferenceParts:
    def test_json_and_plain_text(self):
        assert preference_parts('{"context": "c", "preference": " p "}') == ("c", "p")
        assert preference_parts("生ハムご飯が好き") == ("", "生ハムご飯が好き")
        assert preference_parts('{"context": "c"}') is None

    def test_preference_text_for_react(self):
        assert preference_text('{"context": "c", "preference": "浴衣が好き"}') == "浴衣が好き"
        assert preference_text('{"context": "ユーザーは投稿を閲覧している", "preference": "推している"}') is None
        assert preference_text('{"context": "c", "preference": "よく寝るのが好き"}') is None

    def test_excluded_preference(self):
        assert is_excluded_preference_for_autonomous("c", "汁なし坦々麺が好き") is False
        assert is_excluded_preference_for_autonomous("家でヤモリを見た", "早く出ていってほしい") is True


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

    def test_select_lists_preferences_for_d(self):
        burger = _pref("mem-burger", "ワッパーが好き")

        def list_records(**kwargs):
            if kwargs["namespace"].endswith("/preferences/"):
                return {"memoryRecordSummaries": [
                    {"memoryRecordId": "mem-burger", "content": {"text": burger.text}, "createdAt": burger.created_at},
                ]}
            return {"memoryRecordSummaries": []}

        client = MagicMock()
        client.list_memory_records.side_effect = list_records
        selection = AutonomousSelector("mem-id", "juri_bigangel", client=client).select(NOW, set())
        assert selection.kind == "D"
        assert selection.candidates[0].text == "ワッパーが好き"


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

    def test_record_puts_status_and_run_key(self):
        from src.hokuhoku_imomaru_bot.services.post_history_store import history_key
        table = MagicMock()
        key = history_key(datetime(2026, 9, 28, 10, 7, tzinfo=JST))
        PostHistoryStore(table=table).record(HistoryEntry(posted_date=key, kind="C", text="", status="skipped"))
        item = table.put_item.call_args.kwargs["Item"]
        assert item["posted_date"] == "2026-09-28#10"
        assert item["status"] == "skipped"

    def test_load_recent_reads_run_keys_and_status(self):
        table = MagicMock()
        table.scan.return_value = {"Items": [
            {"posted_date": "2026-09-28#10", "kind": "C", "text": "", "status": "skipped"},
            {"posted_date": "2026-09-28#18", "kind": "D", "text": "t"},   # status なし = scheduled
            {"posted_date": "2026-09-13#21", "kind": "D", "text": "old"},  # 15 日前は読まない
        ]}
        store = PostHistoryStore(table=table)
        entries = store.load_recent(date(2026, 9, 28))
        assert [e.posted_date for e in entries] == ["2026-09-28#18", "2026-09-28#10"]
        assert [e.skipped for e in entries] == [False, True]
        assert len(store.on_day(entries, date(2026, 9, 28))) == 2

    def test_used_keys_window_by_kind(self):
        entries = [
            HistoryEntry(posted_date="2026-09-20#10", kind="C", text="t", dedupe_keys=["C:old"]),   # 8 日前
            HistoryEntry(posted_date="2026-09-20#13", kind="D", text="t", dedupe_keys=["D:old"]),   # 14 日以内
            HistoryEntry(posted_date="2026-09-21#10", kind="B", text="t", dedupe_keys=["B:week"]),  # 7 日前
        ]
        today = date(2026, 9, 28)
        assert PostHistoryStore.used_keys(entries, today) == {"D:old", "B:week"}
        assert PostHistoryStore.used_keys(entries) == {"C:old", "D:old", "B:week"}
