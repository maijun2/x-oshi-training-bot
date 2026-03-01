"""
Replyデータクラスのユニットテスト

Task 5.2: Replyデータクラスのユニットテスト
Validates: Requirements 3.4, 3.5
"""
from src.hokuhoku_imomaru_bot.models.reply import Reply


class TestReplyFromApiResponse:
    """Reply.from_api_responseメソッドのテスト"""

    def test_basic_reply(self):
        """基本的なリプライデータからReplyが正しく生成されること"""
        data = {
            "id": "111",
            "text": "リプライ本文",
            "author_id": "222",
            "created_at": "2025-01-15T10:00:00Z",
            "in_reply_to_user_id": "333",
            "referenced_tweets": [
                {"type": "replied_to", "id": "444"}
            ],
        }
        includes = {
            "users": [
                {"id": "222", "username": "test_user"}
            ]
        }

        reply = Reply.from_api_response(data, includes)

        assert reply.id == "111"
        assert reply.text == "リプライ本文"
        assert reply.author_id == "222"
        assert reply.author_username == "test_user"
        assert reply.created_at == "2025-01-15T10:00:00Z"
        assert reply.in_reply_to_tweet_id == "444"
        assert reply.in_reply_to_user_id == "333"

    def test_without_includes(self):
        """includesなしでもReplyが生成されること（usernameは空文字）"""
        data = {
            "id": "111",
            "text": "リプライ",
            "author_id": "222",
            "created_at": "2025-01-15T10:00:00Z",
            "in_reply_to_user_id": "333",
            "referenced_tweets": [
                {"type": "replied_to", "id": "444"}
            ],
        }

        reply = Reply.from_api_response(data)

        assert reply.author_username == ""
        assert reply.in_reply_to_tweet_id == "444"

    def test_with_none_includes(self):
        """includes=Noneでも正常に動作すること"""
        data = {
            "id": "111",
            "text": "テスト",
            "author_id": "222",
            "created_at": "",
            "in_reply_to_user_id": "333",
            "referenced_tweets": [{"type": "replied_to", "id": "444"}],
        }

        reply = Reply.from_api_response(data, None)
        assert reply.author_username == ""

    def test_no_referenced_tweets(self):
        """referenced_tweetsがない場合、in_reply_to_tweet_idは空文字"""
        data = {
            "id": "111",
            "text": "テスト",
            "author_id": "222",
            "created_at": "",
            "in_reply_to_user_id": "333",
        }

        reply = Reply.from_api_response(data)
        assert reply.in_reply_to_tweet_id == ""

    def test_multiple_referenced_tweets(self):
        """複数のreferenced_tweetsからreplied_toのみ取得すること"""
        data = {
            "id": "111",
            "text": "テスト",
            "author_id": "222",
            "created_at": "",
            "in_reply_to_user_id": "333",
            "referenced_tweets": [
                {"type": "quoted", "id": "555"},
                {"type": "replied_to", "id": "444"},
            ],
        }

        reply = Reply.from_api_response(data)
        assert reply.in_reply_to_tweet_id == "444"

    def test_includes_with_multiple_users(self):
        """複数ユーザーのincludesから正しいユーザー名を取得すること"""
        data = {
            "id": "111",
            "text": "テスト",
            "author_id": "222",
            "created_at": "",
            "in_reply_to_user_id": "333",
            "referenced_tweets": [{"type": "replied_to", "id": "444"}],
        }
        includes = {
            "users": [
                {"id": "999", "username": "other_user"},
                {"id": "222", "username": "correct_user"},
                {"id": "888", "username": "another_user"},
            ]
        }

        reply = Reply.from_api_response(data, includes)
        assert reply.author_username == "correct_user"

    def test_missing_fields_default_to_empty(self):
        """フィールドが欠落している場合、空文字がデフォルトになること"""
        data = {}

        reply = Reply.from_api_response(data)

        assert reply.id == ""
        assert reply.text == ""
        assert reply.author_id == ""
        assert reply.author_username == ""
        assert reply.created_at == ""
        assert reply.in_reply_to_tweet_id == ""
        assert reply.in_reply_to_user_id == ""
