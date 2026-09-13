"""
OshiMemoryWriter のテスト（フェーズ3a-write: 推しの投稿を AgentCore Memory に書き込む）
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.hokuhoku_imomaru_bot.services import Tweet
from src.hokuhoku_imomaru_bot.services.daily_reporter import JST
from src.hokuhoku_imomaru_bot.services.oshi_memory_writer import (
    OshiMemoryWriter,
    build_event_text,
    parse_created_at,
    session_id_for,
)


def _tweet(**kwargs) -> Tweet:
    base = dict(id="2098792599578714321", text="おやすみ〜！明日はライブ！", author_id="oshi")
    base.update(kwargs)
    return Tweet(**base)


class TestHelpers:
    def test_parse_created_at_x_api_format(self):
        parsed = parse_created_at("2026-09-12T16:20:00.000Z")
        assert parsed == datetime(2026, 9, 12, 16, 20, tzinfo=timezone.utc)

    def test_parse_created_at_returns_none_for_missing_or_invalid(self):
        assert parse_created_at(None) is None
        assert parse_created_at("") is None
        assert parse_created_at("not a date") is None

    def test_session_id_uses_jst_date(self):
        # UTC 16:20 = JST 翌 01:20 → JST の日付でセッションを切る
        posted_at = datetime(2026, 9, 12, 16, 20, tzinfo=timezone.utc)
        assert session_id_for(posted_at) == "oshi-2026-09-13"

    def test_event_text_for_original_post(self):
        posted_at = datetime(2026, 9, 12, 16, 20, tzinfo=timezone.utc)
        text = build_event_text(_tweet(), "juri_bigangel", posted_at)
        assert text == "[推し @juri_bigangel の投稿 2026-09-13 01:20 JST]\nおやすみ〜！明日はライブ！"

    def test_event_text_for_quote_post(self):
        posted_at = datetime(2026, 9, 13, 3, 0, tzinfo=timezone.utc)
        text = build_event_text(_tweet(is_quote_tweet=True, text="これ最高"), "juri_bigangel", posted_at)
        assert text.startswith("[推し @juri_bigangel の引用ポストへのコメント 2026-09-13 12:00 JST]\n")
        assert text.endswith("これ最高")


class TestOshiMemoryWriter:
    def _writer(self, client=None) -> OshiMemoryWriter:
        client = client or MagicMock()
        client.create_event.return_value = {"event": {"eventId": "evt-1"}}
        return OshiMemoryWriter(memory_id="mem-123", actor_id="juri_bigangel", client=client)

    def test_requires_memory_id_and_actor_id(self):
        with pytest.raises(ValueError):
            OshiMemoryWriter(memory_id="", actor_id="juri_bigangel", client=MagicMock())
        with pytest.raises(ValueError):
            OshiMemoryWriter(memory_id="mem-123", actor_id="", client=MagicMock())

    def test_record_post_calls_create_event_with_expected_params(self):
        client = MagicMock()
        writer = self._writer(client)

        event_id = writer.record_post(_tweet(created_at="2026-09-12T16:20:00.000Z"))

        assert event_id == "evt-1"
        kwargs = client.create_event.call_args.kwargs
        assert kwargs["memoryId"] == "mem-123"
        assert kwargs["actorId"] == "juri_bigangel"
        assert kwargs["sessionId"] == "oshi-2026-09-13"
        assert kwargs["eventTimestamp"] == datetime(2026, 9, 12, 16, 20, tzinfo=timezone.utc)
        assert kwargs["clientToken"] == "oshi-2098792599578714321"
        assert kwargs["metadata"] == {
            "tweet_id": {"stringValue": "2098792599578714321"},
            "kind": {"stringValue": "original"},
        }
        assert len(kwargs["payload"]) == 1
        conversational = kwargs["payload"][0]["conversational"]
        assert conversational["role"] == "USER"
        assert conversational["content"]["text"].endswith("おやすみ〜！明日はライブ！")

    def test_record_post_marks_quote_posts(self):
        client = MagicMock()
        writer = self._writer(client)

        writer.record_post(_tweet(is_quote_tweet=True, created_at="2026-09-13T03:00:00.000Z"))

        kwargs = client.create_event.call_args.kwargs
        assert kwargs["metadata"]["kind"] == {"stringValue": "quote"}
        assert "引用ポストへのコメント" in kwargs["payload"][0]["conversational"]["content"]["text"]

    def test_record_post_falls_back_to_now_when_created_at_missing(self):
        client = MagicMock()
        writer = self._writer(client)
        before = datetime.now(timezone.utc)

        writer.record_post(_tweet(created_at=None))

        kwargs = client.create_event.call_args.kwargs
        assert before <= kwargs["eventTimestamp"] <= datetime.now(timezone.utc)
        assert kwargs["sessionId"] == f"oshi-{kwargs['eventTimestamp'].astimezone(JST).strftime('%Y-%m-%d')}"

    def test_record_post_propagates_client_errors(self):
        client = MagicMock()
        client.create_event.side_effect = RuntimeError("boom")
        writer = OshiMemoryWriter(memory_id="mem-123", actor_id="juri_bigangel", client=client)

        with pytest.raises(RuntimeError):
            writer.record_post(_tweet(created_at="2026-09-13T03:00:00.000Z"))
