"""
BufferClient のユニットテスト

requests をモックし、GraphQL リクエストの組み立てとレスポンス解釈を検証する。
"""
import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.hokuhoku_imomaru_bot.clients.buffer_client import (
    BufferClient,
    BufferAPIError,
    BUFFER_API_URL,
)


SECRET = {"access_token": "tok-secret-value", "channel_id": "chan-1", "organization_id": "org-1"}


def _make_client():
    secrets_client = MagicMock()
    secrets_client.get_secret_value.return_value = {"SecretString": json.dumps(SECRET)}
    return BufferClient(secrets_client=secrets_client, secret_name="imomaru-bot/buffer-api")


def _response(status=200, body=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body or {}
    resp.text = json.dumps(body or {})
    return resp


def _success_body(post_id="p1", due_at="2026-09-13T23:21:00.000Z", assets=None):
    return {
        "data": {
            "createPost": {
                "__typename": "PostActionSuccess",
                "post": {"id": post_id, "dueAt": due_at, "assets": assets or []},
            }
        }
    }


class TestAddToQueue:
    @patch("src.hokuhoku_imomaru_bot.clients.buffer_client.requests.post")
    def test_success_without_image(self, mock_post):
        mock_post.return_value = _response(body=_success_body())
        client = _make_client()

        post = client.add_to_queue(text="本文\n\nhttps://x.com/a/status/1")

        assert post.id == "p1"
        assert post.due_at == datetime(2026, 9, 13, 23, 21, tzinfo=timezone.utc)
        assert post.asset_urls == []

        # リクエストの組み立て
        _, kwargs = mock_post.call_args
        assert mock_post.call_args.args[0] == BUFFER_API_URL
        assert kwargs["headers"]["Authorization"] == "Bearer tok-secret-value"
        assert kwargs["headers"]["Content-Type"] == "application/json"
        assert kwargs["timeout"] == 30
        post_input = kwargs["json"]["variables"]["input"]
        assert post_input["channelId"] == "chan-1"
        assert post_input["text"] == "本文\n\nhttps://x.com/a/status/1"
        assert post_input["mode"] == "addToQueue"
        assert post_input["schedulingType"] == "automatic"
        # スキーマ上 non-null の項目は空でも明示する
        assert post_input["assets"] == []
        assert post_input["tagIds"] == []
        assert post_input["needsApproval"] is False

    @patch("src.hokuhoku_imomaru_bot.clients.buffer_client.requests.post")
    def test_success_with_image(self, mock_post):
        mock_post.return_value = _response(
            body=_success_body(assets=[{"source": "https://buffer.example/img.png", "mimeType": "image/png"}])
        )
        client = _make_client()

        post = client.add_to_queue(
            text="本文", image_url="https://s3.example/emotions/cheer.png?sig=1", alt_text="スタンプ"
        )

        assert post.asset_urls == ["https://buffer.example/img.png"]
        post_input = mock_post.call_args.kwargs["json"]["variables"]["input"]
        assert post_input["assets"] == [
            {
                "image": {
                    "url": "https://s3.example/emotions/cheer.png?sig=1",
                    "metadata": {"altText": "スタンプ", "userTags": []},
                }
            }
        ]

    @patch("src.hokuhoku_imomaru_bot.clients.buffer_client.requests.post")
    def test_limit_reached_error_raises(self, mock_post):
        """無料枠上限などのエラー payload は BufferAPIError"""
        mock_post.return_value = _response(
            body={"data": {"createPost": {"__typename": "LimitReachedError", "message": "queue full"}}}
        )
        client = _make_client()

        with pytest.raises(BufferAPIError) as exc:
            client.add_to_queue(text="本文")
        assert "LimitReachedError" in str(exc.value)
        assert "queue full" in str(exc.value)

    @patch("src.hokuhoku_imomaru_bot.clients.buffer_client.requests.post")
    def test_graphql_errors_raise(self, mock_post):
        mock_post.return_value = _response(body={"errors": [{"message": "Not authorized"}]})
        client = _make_client()

        with pytest.raises(BufferAPIError) as exc:
            client.add_to_queue(text="本文")
        assert "Not authorized" in str(exc.value)

    @patch("src.hokuhoku_imomaru_bot.clients.buffer_client.requests.post")
    def test_http_error_raises(self, mock_post):
        mock_post.return_value = _response(status=500, body={"message": "boom"})
        client = _make_client()

        with pytest.raises(BufferAPIError) as exc:
            client.add_to_queue(text="本文")
        assert "HTTP 500" in str(exc.value)

    @patch("src.hokuhoku_imomaru_bot.clients.buffer_client.requests.post")
    def test_unparseable_due_at_is_none(self, mock_post):
        mock_post.return_value = _response(body=_success_body(due_at="not-a-date"))
        client = _make_client()

        post = client.add_to_queue(text="本文")
        assert post.due_at is None


class TestDeletePost:
    @patch("src.hokuhoku_imomaru_bot.clients.buffer_client.requests.post")
    def test_success(self, mock_post):
        mock_post.return_value = _response(
            body={"data": {"deletePost": {"__typename": "DeletePostSuccess", "id": "p1"}}}
        )
        assert _make_client().delete_post("p1") is True
        assert mock_post.call_args.kwargs["json"]["variables"] == {"input": {"id": "p1"}}

    @patch("src.hokuhoku_imomaru_bot.clients.buffer_client.requests.post")
    def test_error_returns_false(self, mock_post):
        mock_post.return_value = _response(
            body={"data": {"deletePost": {"__typename": "VoidMutationError", "message": "nope"}}}
        )
        assert _make_client().delete_post("p1") is False


class TestCredentials:
    def test_credentials_cached(self):
        client = _make_client()
        assert client.channel_id == "chan-1"
        assert client.channel_id == "chan-1"
        client._secrets_client.get_secret_value.assert_called_once_with(SecretId="imomaru-bot/buffer-api")

    def test_load_failure_logs_without_token(self, caplog):
        secrets_client = MagicMock()
        secrets_client.get_secret_value.side_effect = Exception("denied tok-secret-value")
        client = BufferClient(secrets_client=secrets_client, secret_name="s")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(Exception):
                client.channel_id
        assert "tok-secret-value" not in caplog.text

    @patch("src.hokuhoku_imomaru_bot.clients.buffer_client.requests.post")
    def test_token_not_logged_on_success(self, mock_post, caplog):
        mock_post.return_value = _response(body=_success_body())
        with caplog.at_level(logging.INFO):
            _make_client().add_to_queue(text="本文")
        assert "tok-secret-value" not in caplog.text
