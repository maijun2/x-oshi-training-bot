"""
BufferScheduler のユニットテスト

キャップ判定・本文組み立て・感情画像の presigned URL 添付・状態更新を検証する。
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.hokuhoku_imomaru_bot.clients.buffer_client import BufferClient, BufferPost, BufferAPIError
from src.hokuhoku_imomaru_bot.models.bot_state import BotState
from src.hokuhoku_imomaru_bot.services.buffer_scheduler import (
    BufferScheduler,
    EMOTION_IMAGE_ALT_TEXT,
)
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


@pytest.fixture
def s3_client():
    s3 = MagicMock()
    s3.generate_presigned_url.return_value = "https://s3.example/emotions/cheer.png?X-Amz-Signature=abc"
    return s3


@pytest.fixture
def scheduler(buffer_client, state_store, s3_client):
    return BufferScheduler(
        buffer_client=buffer_client,
        state_store=state_store,
        s3_client=s3_client,
        bucket_name="assets",
        oshi_username="juri_bigangel",
        daily_cap=3,
        image_url_ttl_seconds=3600,
    )


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

    def test_image_attached_sets_flag(self, scheduler, buffer_client, s3_client, state_store):
        buffer_client.add_to_queue.return_value = BufferPost(
            id="p1", due_at=DUE_AT, asset_urls=["https://buffer.example/img.png"]
        )
        state = BotState()

        result = scheduler.schedule_quote(state, tweet_id="123", draft_text="t", emotion_key="cheer")

        assert result.image_attached is True
        assert state.daily_image_posted is True
        assert state.daily_buffer_count == 1
        state_store.get_emotion_image_filename.assert_called_once_with("cheer")
        s3_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "assets", "Key": "emotions/cheer.png"},
            ExpiresIn=3600,
        )
        buffer_client.add_to_queue.assert_called_once_with(
            text="t\n\nhttps://x.com/juri_bigangel/status/123",
            image_url="https://s3.example/emotions/cheer.png?X-Amz-Signature=abc",
            alt_text=EMOTION_IMAGE_ALT_TEXT,
        )

    def test_image_not_attached_when_already_posted_today(self, scheduler, buffer_client, s3_client):
        state = BotState(daily_image_posted=True)

        scheduler.schedule_quote(state, tweet_id="1", draft_text="t", emotion_key="cheer")

        s3_client.generate_presigned_url.assert_not_called()
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

    def test_unknown_emotion_key_posts_without_image(self, scheduler, buffer_client, state_store, s3_client):
        state_store.get_emotion_image_filename.return_value = None

        scheduler.schedule_quote(BotState(), tweet_id="1", draft_text="t", emotion_key="unknown")

        s3_client.generate_presigned_url.assert_not_called()
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
