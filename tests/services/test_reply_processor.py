"""
ReplyProcessorクラスのユニットテスト
"""
import logging
import time
import pytest
import boto3
from datetime import datetime, timezone, timedelta
from moto import mock_aws
from unittest.mock import MagicMock
from src.hokuhoku_imomaru_bot.services.reply_processor import ReplyProcessor
from src.hokuhoku_imomaru_bot.models import Reply


TABLE_NAME = "imomaru-bot-processed-replies"


def _create_table(dynamodb_client):
    """テスト用DynamoDBテーブルを作成"""
    dynamodb_client.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "tweet_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "tweet_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def _make_reply(reply_id="111", author_id="222", author_username="test_user",
                in_reply_to_tweet_id="500", in_reply_to_user_id="999"):
    """テスト用Replyを生成"""
    return Reply(
        id=reply_id,
        text="@bot テストリプライ",
        author_id=author_id,
        author_username=author_username,
        created_at="2026-01-15T10:00:00Z",
        in_reply_to_tweet_id=in_reply_to_tweet_id,
        in_reply_to_user_id=in_reply_to_user_id,
    )


def _mock_x_api_client(tweet_created_at=None, post_result_id="777"):
    """テスト用XAPIClientモックを生成"""
    mock = MagicMock()
    if tweet_created_at is None:
        # デフォルトは5日前（30日以内）
        tweet_created_at = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    mock.get_tweet.return_value = {
        "id": "500",
        "text": "ボット投稿テスト",
        "created_at": tweet_created_at,
    }
    mock.post_tweet.return_value = {"data": {"id": post_result_id}}
    return mock


def _mock_ai_generator(response_text="テスト応答ｲﾓ🍠"):
    """テスト用AIGeneratorモックを生成"""
    mock = MagicMock()
    mock.generate_reply_response.return_value = response_text
    return mock


class TestReplyProcessorProcessReply:
    """process_replyメソッドのテスト"""

    @mock_aws
    def test_successful_reply_processing(self):
        """リプライが正常に処理されること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        mock_api = _mock_x_api_client()
        mock_ai = _mock_ai_generator()

        result = processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        assert result is True
        mock_ai.generate_reply_response.assert_called_once()
        mock_api.post_tweet.assert_called_once()

    @mock_aws
    def test_reply_to_old_tweet_skipped(self):
        """30日以上前のツイートへのリプライがスキップされること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        # 60日前のツイート
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        mock_api = _mock_x_api_client(tweet_created_at=old_date)
        mock_ai = _mock_ai_generator()

        result = processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        assert result is False
        mock_ai.generate_reply_response.assert_not_called()
        mock_api.post_tweet.assert_not_called()

    @mock_aws
    def test_already_processed_reply_skipped(self):
        """処理済みリプライがスキップされること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)
        # 処理済みとして登録
        client.put_item(
            TableName=TABLE_NAME,
            Item={"tweet_id": {"S": "111"}, "replied_at": {"S": "2026-01-14T10:00:00Z"}},
        )

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        mock_api = _mock_x_api_client()
        mock_ai = _mock_ai_generator()

        result = processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        assert result is False
        mock_ai.generate_reply_response.assert_not_called()

    @mock_aws
    def test_processed_reply_recorded_in_dynamodb(self):
        """処理済みリプライがDynamoDBに記録されること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        mock_api = _mock_x_api_client()
        mock_ai = _mock_ai_generator()

        processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        # DynamoDBにレコードが作成されたことを確認
        response = client.get_item(
            TableName=TABLE_NAME,
            Key={"tweet_id": {"S": "111"}},
        )
        assert "Item" in response
        item = response["Item"]
        assert item["user_id"]["S"] == "222"
        assert item["bot_reply_id"]["S"] == "777"
        assert "ttl" in item

    @mock_aws
    def test_ttl_set_to_60_days(self):
        """TTLが現在時刻+60日に設定されること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        mock_api = _mock_x_api_client()
        mock_ai = _mock_ai_generator()

        before = int(time.time())
        processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)
        after = int(time.time())

        response = client.get_item(
            TableName=TABLE_NAME,
            Key={"tweet_id": {"S": "111"}},
        )
        ttl = int(response["Item"]["ttl"]["N"])
        expected_min = before + (60 * 24 * 60 * 60)
        expected_max = after + (60 * 24 * 60 * 60)
        assert expected_min <= ttl <= expected_max

    @mock_aws
    def test_post_tweet_failure_returns_false(self):
        """リプライ投稿失敗時にFalseを返すこと"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        mock_api = _mock_x_api_client()
        mock_api.post_tweet.side_effect = Exception("API Error")
        mock_ai = _mock_ai_generator()

        result = processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        assert result is False

    @mock_aws
    def test_post_tweet_failure_no_record_created(self):
        """リプライ投稿失敗時にDynamoDBレコードが作成されないこと"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        mock_api = _mock_x_api_client()
        mock_api.post_tweet.side_effect = Exception("API Error")
        mock_ai = _mock_ai_generator()

        processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        response = client.get_item(
            TableName=TABLE_NAME,
            Key={"tweet_id": {"S": "111"}},
        )
        assert "Item" not in response

    @mock_aws
    def test_get_tweet_failure_skips_reply(self):
        """ボット投稿取得失敗時にリプライがスキップされること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        mock_api = MagicMock()
        mock_api.get_tweet.side_effect = Exception("Tweet not found")
        mock_ai = _mock_ai_generator()

        result = processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        assert result is False
        mock_ai.generate_reply_response.assert_not_called()

    @mock_aws
    def test_ai_response_passed_to_post_tweet(self):
        """AI応答がpost_tweetに正しく渡されること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        mock_api = _mock_x_api_client()
        mock_ai = _mock_ai_generator(response_text="カスタム応答ｲﾓ🍠")

        processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        mock_api.post_tweet.assert_called_once_with(
            text="カスタム応答ｲﾓ🍠",
            reply_to_tweet_id="111",
        )

    @mock_aws
    def test_reply_to_tweet_within_30_days_processed(self):
        """30日以内のツイートへのリプライが処理されること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        recent_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        mock_api = _mock_x_api_client(tweet_created_at=recent_date)
        mock_ai = _mock_ai_generator()

        result = processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        assert result is True

    @mock_aws
    def test_success_log_output(self, caplog):
        """処理成功時にINFOログが出力されること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        mock_api = _mock_x_api_client()
        mock_ai = _mock_ai_generator()

        with caplog.at_level(logging.INFO):
            processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        assert "Reply processed successfully: 111 -> 777" in caplog.text

    @mock_aws
    def test_failure_log_output(self, caplog):
        """処理失敗時にERRORログが出力されること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
        reply = _make_reply()
        mock_api = _mock_x_api_client()
        mock_api.post_tweet.side_effect = Exception("Post failed")
        mock_ai = _mock_ai_generator()

        with caplog.at_level(logging.ERROR):
            processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        assert "Failed to process reply 111" in caplog.text
