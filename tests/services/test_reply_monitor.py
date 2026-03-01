"""
ReplyMonitorクラスのユニットテスト
"""
import logging
import pytest
from unittest.mock import MagicMock
from src.hokuhoku_imomaru_bot.services.reply_monitor import ReplyMonitor


BOT_USER_ID = "999"


def _make_mention(tweet_id, text, author_id, in_reply_to_user_id, ref_type="replied_to", ref_id=None):
    """テスト用メンションデータを生成"""
    mention = {
        "id": tweet_id,
        "text": text,
        "author_id": author_id,
        "created_at": "2026-01-15T10:00:00Z",
        "in_reply_to_user_id": in_reply_to_user_id,
    }
    if ref_id:
        mention["referenced_tweets"] = [{"type": ref_type, "id": ref_id}]
    return mention


def _make_includes(users):
    """テスト用includesデータを生成"""
    return {"users": [{"id": uid, "username": uname} for uid, uname in users]}


class TestReplyMonitorDetectReplies:
    """detect_repliesメソッドのテスト"""

    def test_detects_replies_to_bot(self):
        """ボット投稿へのリプライが正しく検出されること"""
        mock_client = MagicMock()
        mock_client.get_user_mentions.return_value = {
            "data": [
                _make_mention("111", "@bot リプライ", "222", BOT_USER_ID, ref_id="500"),
            ],
            "includes": _make_includes([("222", "test_user")]),
        }

        monitor = ReplyMonitor(api_client=mock_client, bot_user_id=BOT_USER_ID)
        replies = monitor.detect_replies(since_tweet_id="100")

        assert len(replies) == 1
        assert replies[0].id == "111"
        assert replies[0].author_id == "222"
        assert replies[0].author_username == "test_user"
        assert replies[0].in_reply_to_user_id == BOT_USER_ID

    def test_filters_out_non_bot_replies(self):
        """ボット以外へのリプライがフィルタリングされること"""
        mock_client = MagicMock()
        mock_client.get_user_mentions.return_value = {
            "data": [
                _make_mention("111", "@bot リプライ", "222", BOT_USER_ID, ref_id="500"),
                _make_mention("112", "@other メンション", "333", "888"),  # 別ユーザーへのリプライ
            ],
            "includes": _make_includes([("222", "user_a"), ("333", "user_b")]),
        }

        monitor = ReplyMonitor(api_client=mock_client, bot_user_id=BOT_USER_ID)
        replies = monitor.detect_replies()

        assert len(replies) == 1
        assert replies[0].id == "111"

    def test_returns_empty_when_no_mentions(self):
        """メンションがない場合に空リストを返すこと"""
        mock_client = MagicMock()
        mock_client.get_user_mentions.return_value = {"data": []}

        monitor = ReplyMonitor(api_client=mock_client, bot_user_id=BOT_USER_ID)
        replies = monitor.detect_replies()

        assert replies == []

    def test_returns_empty_when_no_data_key(self):
        """dataキーがない場合に空リストを返すこと"""
        mock_client = MagicMock()
        mock_client.get_user_mentions.return_value = {}

        monitor = ReplyMonitor(api_client=mock_client, bot_user_id=BOT_USER_ID)
        replies = monitor.detect_replies()

        assert replies == []

    def test_passes_since_id_to_api(self):
        """since_tweet_idがAPIに正しく渡されること"""
        mock_client = MagicMock()
        mock_client.get_user_mentions.return_value = {}

        monitor = ReplyMonitor(api_client=mock_client, bot_user_id=BOT_USER_ID)
        monitor.detect_replies(since_tweet_id="12345")

        mock_client.get_user_mentions.assert_called_once_with(
            user_id=BOT_USER_ID,
            since_id="12345",
            max_results=100,
        )

    def test_handles_api_error_gracefully(self):
        """APIエラー時に空リストを返すこと"""
        mock_client = MagicMock()
        mock_client.get_user_mentions.side_effect = Exception("API Error")

        monitor = ReplyMonitor(api_client=mock_client, bot_user_id=BOT_USER_ID)
        replies = monitor.detect_replies()

        assert replies == []

    def test_logs_detected_reply_count(self, caplog):
        """検出されたリプライ数がログに出力されること"""
        mock_client = MagicMock()
        mock_client.get_user_mentions.return_value = {
            "data": [
                _make_mention("111", "@bot リプライ1", "222", BOT_USER_ID, ref_id="500"),
                _make_mention("112", "@bot リプライ2", "333", BOT_USER_ID, ref_id="501"),
                _make_mention("113", "@other メンション", "444", "888"),
            ],
            "includes": _make_includes([("222", "a"), ("333", "b"), ("444", "c")]),
        }

        monitor = ReplyMonitor(api_client=mock_client, bot_user_id=BOT_USER_ID)
        with caplog.at_level(logging.INFO):
            replies = monitor.detect_replies()

        assert len(replies) == 2
        assert "2 replies out of 3 mentions" in caplog.text

    def test_multiple_replies_from_same_user(self):
        """同一ユーザーからの複数リプライが全て検出されること"""
        mock_client = MagicMock()
        mock_client.get_user_mentions.return_value = {
            "data": [
                _make_mention("111", "@bot リプライ1", "222", BOT_USER_ID, ref_id="500"),
                _make_mention("112", "@bot リプライ2", "222", BOT_USER_ID, ref_id="501"),
            ],
            "includes": _make_includes([("222", "same_user")]),
        }

        monitor = ReplyMonitor(api_client=mock_client, bot_user_id=BOT_USER_ID)
        replies = monitor.detect_replies()

        assert len(replies) == 2
        assert all(r.author_username == "same_user" for r in replies)
