"""
BufferScheduler のユニットテスト

キャップ判定（実行ごと／日次の 2 段）・本文組み立て・感情画像 URL 添付・状態更新を検証する。
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.hokuhoku_imomaru_bot.clients.buffer_client import BufferClient, BufferPost, BufferAPIError
from src.hokuhoku_imomaru_bot.models.bot_state import BotState
from src.hokuhoku_imomaru_bot.services.buffer_scheduler import (
    BufferScheduler,
    DEFAULT_SLOT_TIMES_JST,
    EMOTION_IMAGE_ALT_TEXT,
    parse_slot_times,
)
from src.hokuhoku_imomaru_bot.services.daily_reporter import JST
from src.hokuhoku_imomaru_bot.services.state_store import StateStore


DUE_AT = datetime(2026, 9, 13, 23, 21, tzinfo=timezone.utc)


@pytest.fixture
def buffer_client():
    client = MagicMock(spec=BufferClient)
    client.add_to_queue.return_value = BufferPost(id="p1", due_at=DUE_AT, asset_urls=[])
    return client


@pytest.fixture
def state_store():
    store = MagicMock(spec=StateStore)
    store.get_emotion_image_filename.return_value = "cheer.png"
    return store


PUBLIC_BASE = "https://imomaru-bot-public-assets-123.s3.ap-northeast-1.amazonaws.com"


@pytest.fixture
def scheduler(buffer_client, state_store):
    return BufferScheduler(
        buffer_client=buffer_client,
        state_store=state_store,
        public_image_base_url=PUBLIC_BASE + "/",  # 末尾スラッシュは正規化される
        oshi_username="juri_bigangel",
        daily_cap=3,
        run_cap=3,  # 既存テストは日次キャップの挙動を見るので実行キャップは日次と同じにしておく
    )


def _make_scheduler(buffer_client, state_store, *, run_cap, daily_cap):
    return BufferScheduler(
        buffer_client=buffer_client,
        state_store=state_store,
        public_image_base_url=PUBLIC_BASE,
        oshi_username="juri_bigangel",
        daily_cap=daily_cap,
        run_cap=run_cap,
    )


class TestNextSlotAt:
    """頭脳に渡す「公開予定時刻」＝現在時刻より後の最初の Buffer 枠（JST）"""

    @pytest.mark.parametrize("now_utc, expected_jst", [
        # 実測: 13:18 JST 検知 → 14:15 枠、23:58 JST 検知 → 翌 02:00 枠、10:07 JST 検知 → 11:15 枠
        (datetime(2026, 9, 16, 4, 18, tzinfo=timezone.utc), datetime(2026, 9, 16, 14, 15, tzinfo=JST)),
        (datetime(2026, 9, 15, 14, 58, tzinfo=timezone.utc), datetime(2026, 9, 16, 2, 0, tzinfo=JST)),
        (datetime(2026, 9, 16, 1, 7, tzinfo=timezone.utc), datetime(2026, 9, 16, 11, 15, tzinfo=JST)),
        # 枠の時刻ちょうどは「過ぎた」扱いで次の枠
        (datetime(2026, 9, 16, 14, 15, tzinfo=JST), datetime(2026, 9, 16, 15, 15, tzinfo=JST)),
        # 日付の境界（JST 00:30 → 当日 02:00、02:00 ちょうど → 当日 08:00）
        (datetime(2026, 9, 16, 0, 30, tzinfo=JST), datetime(2026, 9, 16, 2, 0, tzinfo=JST)),
        (datetime(2026, 9, 16, 2, 0, tzinfo=JST), datetime(2026, 9, 16, 8, 0, tzinfo=JST)),
        # 夜の実行（21:00 ＋ 5 分ウィンドウ）→ 当日 22:00 枠。22:00 ちょうどは翌 02:00
        (datetime(2026, 9, 19, 21, 5, tzinfo=JST), datetime(2026, 9, 19, 22, 0, tzinfo=JST)),
        (datetime(2026, 9, 19, 22, 0, tzinfo=JST), datetime(2026, 9, 20, 2, 0, tzinfo=JST)),
    ])
    def test_default_slots(self, scheduler, now_utc, expected_jst):
        assert scheduler.next_slot_at(now_utc) == expected_jst

    def test_custom_slots_from_env_style_string(self, buffer_client, state_store):
        scheduler = BufferScheduler(
            buffer_client=buffer_client, state_store=state_store,
            public_image_base_url=PUBLIC_BASE, oshi_username="juri_bigangel",
            slot_times_jst="21:00, 09:30".split(","),  # 順不同・空白あり
        )
        assert scheduler.next_slot_at(datetime(2026, 9, 16, 10, 0, tzinfo=JST)) == datetime(2026, 9, 16, 21, 0, tzinfo=JST)
        assert scheduler.next_slot_at(datetime(2026, 9, 16, 22, 0, tzinfo=JST)) == datetime(2026, 9, 17, 9, 30, tzinfo=JST)

    def test_no_slots_returns_none(self, buffer_client, state_store):
        scheduler = BufferScheduler(
            buffer_client=buffer_client, state_store=state_store,
            public_image_base_url=PUBLIC_BASE, oshi_username="juri_bigangel",
            slot_times_jst=[],
        )
        assert scheduler.next_slot_at(datetime.now(timezone.utc)) is None

    def test_parse_slot_times_ignores_invalid(self):
        slots = parse_slot_times("08:00,bogus,,25:99,11:15")
        assert [f"{t:%H:%M}" for t in slots] == ["08:00", "11:15"]
        assert len(parse_slot_times(",".join(DEFAULT_SLOT_TIMES_JST))) == 9


class TestNextSlotAtAfterScheduling:
    """同じ実行の 2 件目以降は、投入済みの予約時刻（実スロット）より後の枠を公開予定として渡す"""

    def _schedule(self, scheduler, buffer_client, due_at):
        buffer_client.add_to_queue.return_value = BufferPost(id="p", due_at=due_at, asset_urls=[])
        assert scheduler.schedule_quote(BotState(), tweet_id="1", draft_text="t") is not None

    @pytest.mark.parametrize("now_jst, due_jst, expected_jst", [
        # 23:58 回: 1 件目 → 02:03（実スロット）、2 件目は 08:00 と伝える
        (datetime(2026, 9, 25, 23, 58, tzinfo=JST), datetime(2026, 9, 26, 2, 3, tzinfo=JST),
         datetime(2026, 9, 26, 8, 0, tzinfo=JST)),
        # 実スロットが名目より早い（名目 15:15 → 実 15:03）でも同じ名目枠を返さない
        (datetime(2026, 9, 26, 13, 23, tzinfo=JST), datetime(2026, 9, 26, 15, 3, tzinfo=JST),
         datetime(2026, 9, 26, 19, 15, tzinfo=JST)),
        # 21:00 回: 1 件目 → 22:04、2 件目は翌 02:00
        (datetime(2026, 9, 25, 21, 1, tzinfo=JST), datetime(2026, 9, 25, 22, 4, tzinfo=JST),
         datetime(2026, 9, 26, 2, 0, tzinfo=JST)),
        # 10:07 回: 1 件目 → 11:12（名目より早い）、2 件目は 12:15
        (datetime(2026, 9, 25, 10, 7, tzinfo=JST), datetime(2026, 9, 25, 11, 12, tzinfo=JST),
         datetime(2026, 9, 25, 12, 15, tzinfo=JST)),
    ])
    def test_second_post_gets_following_slot(self, buffer_client, state_store, now_jst, due_jst, expected_jst):
        scheduler = _make_scheduler(buffer_client, state_store, run_cap=2, daily_cap=7)
        assert scheduler.next_slot_at(now_jst) < expected_jst
        self._schedule(scheduler, buffer_client, due_jst)
        assert scheduler.next_slot_at(now_jst) == expected_jst

    def test_missing_due_at_falls_back_to_estimated_slot(self, buffer_client, state_store):
        scheduler = _make_scheduler(buffer_client, state_store, run_cap=2, daily_cap=7)
        now = datetime.now(timezone.utc)
        first = scheduler.next_slot_at(now)
        self._schedule(scheduler, buffer_client, None)
        assert scheduler.next_slot_at(now) > first

    def test_run_cap_2_schedules_two_then_email_only(self, buffer_client, state_store):
        scheduler = _make_scheduler(buffer_client, state_store, run_cap=2, daily_cap=7)
        state = BotState()
        assert scheduler.schedule_quote(state, tweet_id="1", draft_text="a") is not None
        assert scheduler.schedule_quote(state, tweet_id="2", draft_text="b") is not None
        assert scheduler.schedule_quote(state, tweet_id="3", draft_text="c") is None
        assert state.daily_buffer_count == 2
        assert buffer_client.add_to_queue.call_count == 2


class TestCapAndGates:
    def test_can_schedule_until_cap(self, scheduler):
        assert scheduler.can_schedule(BotState(daily_buffer_count=0)) is True
        assert scheduler.can_schedule(BotState(daily_buffer_count=2)) is True
        assert scheduler.can_schedule(BotState(daily_buffer_count=3)) is False

    def test_can_attach_image_requires_slot_and_flag(self, scheduler):
        assert scheduler.can_attach_image(BotState()) is True
        assert scheduler.can_attach_image(BotState(daily_image_posted=True)) is False
        assert scheduler.can_attach_image(BotState(daily_buffer_count=3)) is False

    def test_cap_reached_returns_none_without_api_call(self, scheduler, buffer_client):
        state = BotState(daily_buffer_count=3)

        result = scheduler.schedule_quote(state, tweet_id="1", draft_text="t", emotion_key="cheer")

        assert result is None
        buffer_client.add_to_queue.assert_not_called()
        assert state.daily_buffer_count == 3


class TestRunCap:
    """実行ごとキャップ（主キャップ）。日次カウントが空でも 1 回の実行では run_cap 件までしか投入しない"""

    def test_second_post_in_same_run_is_rejected(self, buffer_client, state_store):
        scheduler = _make_scheduler(buffer_client, state_store, run_cap=1, daily_cap=7)
        state = BotState(daily_buffer_count=0)

        first = scheduler.schedule_quote(state, tweet_id="1", draft_text="a")
        second = scheduler.schedule_quote(state, tweet_id="2", draft_text="b")

        assert first is not None
        assert second is None
        assert buffer_client.add_to_queue.call_count == 1
        assert state.daily_buffer_count == 1
        assert scheduler.can_schedule(state) is False

    def test_run_count_is_per_instance(self, buffer_client, state_store):
        """Lambda invocation ごとに新しいインスタンスが作られるので、次の実行では再び投入できる"""
        state = BotState(daily_buffer_count=0)
        run1 = _make_scheduler(buffer_client, state_store, run_cap=1, daily_cap=7)
        run1.schedule_quote(state, tweet_id="1", draft_text="a")

        run2 = _make_scheduler(buffer_client, state_store, run_cap=1, daily_cap=7)

        assert run2.can_schedule(state) is True
        assert run2.schedule_quote(state, tweet_id="2", draft_text="b") is not None
        assert state.daily_buffer_count == 2

    def test_daily_cap_still_applies_as_safety_valve(self, buffer_client, state_store):
        scheduler = _make_scheduler(buffer_client, state_store, run_cap=1, daily_cap=7)
        state = BotState(daily_buffer_count=7)

        assert scheduler.can_schedule(state) is False
        assert scheduler.schedule_quote(state, tweet_id="1", draft_text="a") is None
        buffer_client.add_to_queue.assert_not_called()

    def test_can_attach_image_follows_run_cap(self, buffer_client, state_store):
        scheduler = _make_scheduler(buffer_client, state_store, run_cap=1, daily_cap=7)
        state = BotState()
        assert scheduler.can_attach_image(state) is True

        scheduler.schedule_quote(state, tweet_id="1", draft_text="a")

        assert scheduler.can_attach_image(state) is False

    def test_api_failure_does_not_consume_run_cap(self, buffer_client, state_store):
        scheduler = _make_scheduler(buffer_client, state_store, run_cap=1, daily_cap=7)
        buffer_client.add_to_queue.side_effect = [BufferAPIError("boom"), BufferPost(id="p2", due_at=DUE_AT, asset_urls=[])]
        state = BotState()

        with pytest.raises(BufferAPIError):
            scheduler.schedule_quote(state, tweet_id="1", draft_text="a")

        assert scheduler.can_schedule(state) is True
        assert scheduler.schedule_quote(state, tweet_id="2", draft_text="b") is not None


class TestScheduleQuote:
    def test_text_is_draft_plus_blank_line_plus_url(self, scheduler, buffer_client):
        state = BotState()

        result = scheduler.schedule_quote(state, tweet_id="123", draft_text="嬉しいｲﾓ🍠")

        assert result.post_id == "p1"
        assert result.due_at == DUE_AT
        assert result.image_attached is False
        buffer_client.add_to_queue.assert_called_once_with(
            text="嬉しいｲﾓ🍠\n\nhttps://x.com/juri_bigangel/status/123",
            image_url=None,
            alt_text=None,
        )
        assert state.daily_buffer_count == 1
        assert state.daily_image_posted is False

    def test_image_attached_sets_flag(self, scheduler, buffer_client, state_store):
        buffer_client.add_to_queue.return_value = BufferPost(
            id="p1", due_at=DUE_AT, asset_urls=[PUBLIC_BASE + "/emotions/cheer.png"]
        )
        state = BotState()

        result = scheduler.schedule_quote(state, tweet_id="123", draft_text="t", emotion_key="cheer")

        assert result.image_attached is True
        assert state.daily_image_posted is True
        assert state.daily_buffer_count == 1
        state_store.get_emotion_image_filename.assert_called_once_with("cheer")
        buffer_client.add_to_queue.assert_called_once_with(
            text="t\n\nhttps://x.com/juri_bigangel/status/123",
            image_url=PUBLIC_BASE + "/emotions/cheer.png",  # 署名なしの公開 URL
            alt_text=EMOTION_IMAGE_ALT_TEXT,
        )

    def test_image_url_is_percent_encoded(self, scheduler, state_store):
        state_store.get_emotion_image_filename.return_value = "いも丸 cheer.png"
        assert scheduler.build_emotion_image_url("cheer") == (
            PUBLIC_BASE + "/emotions/%E3%81%84%E3%82%82%E4%B8%B8%20cheer.png"
        )

    def test_image_not_attached_when_already_posted_today(self, scheduler, buffer_client, state_store):
        state = BotState(daily_image_posted=True)

        scheduler.schedule_quote(state, tweet_id="1", draft_text="t", emotion_key="cheer")

        state_store.get_emotion_image_filename.assert_not_called()
        assert buffer_client.add_to_queue.call_args.kwargs["image_url"] is None

    def test_image_lookup_failure_falls_back_to_no_image(self, scheduler, buffer_client, state_store):
        state_store.get_emotion_image_filename.side_effect = Exception("dynamodb down")
        state = BotState()

        result = scheduler.schedule_quote(state, tweet_id="1", draft_text="t", emotion_key="cheer")

        assert result is not None
        assert result.image_attached is False
        assert buffer_client.add_to_queue.call_args.kwargs["image_url"] is None
        assert state.daily_image_posted is False
        assert state.daily_buffer_count == 1

    def test_unknown_emotion_key_posts_without_image(self, scheduler, buffer_client, state_store):
        state_store.get_emotion_image_filename.return_value = None

        scheduler.schedule_quote(BotState(), tweet_id="1", draft_text="t", emotion_key="unknown")

        assert buffer_client.add_to_queue.call_args.kwargs["image_url"] is None

    def test_buffer_accepts_but_drops_asset_keeps_flag_false(self, scheduler, buffer_client):
        """URL を渡したのに assets が空で返ったら画像は添付されていない扱い（翌回に再挑戦できる）"""
        buffer_client.add_to_queue.return_value = BufferPost(id="p1", due_at=DUE_AT, asset_urls=[])
        state = BotState()

        result = scheduler.schedule_quote(state, tweet_id="1", draft_text="t", emotion_key="cheer")

        assert result.image_attached is False
        assert state.daily_image_posted is False

    def test_api_failure_propagates_and_state_unchanged(self, scheduler, buffer_client):
        buffer_client.add_to_queue.side_effect = BufferAPIError("LimitReachedError")
        state = BotState()

        with pytest.raises(BufferAPIError):
            scheduler.schedule_quote(state, tweet_id="1", draft_text="t", emotion_key="cheer")

        assert state.daily_buffer_count == 0
        assert state.daily_image_posted is False
