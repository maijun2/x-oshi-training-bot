"""
ReplyProcessorのプロパティテスト

Feature: group-quote-removal-and-reply-feature
Property 8: ボット投稿日時チェックとスキップ
Property 9: 処理済みリプライのスキップ
Property 10: 処理済みリプライの記録
Property 13: レート制限後の再処理
Validates: Requirements 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 10.4
"""
import time
import boto3
import pytest
from datetime import datetime, timezone, timedelta
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from moto import mock_aws
from unittest.mock import MagicMock
from src.hokuhoku_imomaru_bot.services.reply_processor import ReplyProcessor
from src.hokuhoku_imomaru_bot.models import Reply


TABLE_NAME = "imomaru-bot-processed-replies"

tweet_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Nd",)),
    min_size=1,
    max_size=20,
).filter(lambda x: x.isdigit())

user_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Nd",)),
    min_size=1,
    max_size=20,
).filter(lambda x: x.isdigit())

# 0〜90日の範囲でツイート経過日数を生成
tweet_age_days_st = st.integers(min_value=0, max_value=90)


def _create_table(dynamodb_client):
    """テスト用DynamoDBテーブルを作成"""
    dynamodb_client.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "tweet_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "tweet_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def _make_reply(reply_id="111", author_id="222", in_reply_to_tweet_id="500"):
    """テスト用Replyを生成"""
    return Reply(
        id=reply_id,
        text="@bot テストリプライ",
        author_id=author_id,
        author_username="test_user",
        created_at="2026-01-15T10:00:00Z",
        in_reply_to_tweet_id=in_reply_to_tweet_id,
        in_reply_to_user_id="999",
    )


def _mock_x_api_client(tweet_age_days=5, post_result_id="777"):
    """テスト用XAPIClientモックを生成"""
    mock = MagicMock()
    created_at = (datetime.now(timezone.utc) - timedelta(days=tweet_age_days)).isoformat()
    mock.get_tweet.return_value = {
        "id": "500",
        "text": "ボット投稿テスト",
        "created_at": created_at,
    }
    mock.post_tweet.return_value = {"data": {"id": post_result_id}}
    return mock


def _mock_ai_generator():
    """テスト用AIGeneratorモックを生成"""
    mock = MagicMock()
    mock.generate_reply_response.return_value = "テスト応答ｲﾓ🍠"
    return mock


# Feature: group-quote-removal-and-reply-feature
# Property 8: ボット投稿日時チェックとスキップ
# For any リプライに対して、システムはリプライ対象ボット投稿の日時をチェックし、
# 30日以上前の場合はそのリプライをスキップする
@settings(max_examples=100, deadline=None)
@given(tweet_age_days=tweet_age_days_st)
@mock_aws
def test_property_8_bot_tweet_age_check(tweet_age_days):
    """
    Property 8: ボット投稿日時チェックとスキップ

    任意のツイート経過日数に対して:
    - 30日未満: リプライが処理される (True)
    - 30日以上: リプライがスキップされる (False)
    """
    client = boto3.client("dynamodb", region_name="ap-northeast-1")
    _create_table(client)

    processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
    reply = _make_reply()
    mock_api = _mock_x_api_client(tweet_age_days=tweet_age_days)
    mock_ai = _mock_ai_generator()

    result = processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

    if tweet_age_days < 30:
        # 30日未満: 処理される
        assert result is True, f"Tweet age {tweet_age_days} days should be processed"
        mock_ai.generate_reply_response.assert_called_once()
        mock_api.post_tweet.assert_called_once()
    else:
        # 30日以上: スキップされる
        assert result is False, f"Tweet age {tweet_age_days} days should be skipped"
        mock_ai.generate_reply_response.assert_not_called()
        mock_api.post_tweet.assert_not_called()


# Feature: group-quote-removal-and-reply-feature
# Property 9: 処理済みリプライのスキップ
# For any リプライに対して、システムはProcessed_Replies_Tableでtweet_idを検索し、
# 既に存在する場合はそのリプライをスキップする
@settings(max_examples=100, deadline=None)
@given(
    reply_ids=st.lists(tweet_id_st, min_size=1, max_size=10, unique=True),
    pre_processed_count=st.integers(min_value=0, max_value=10),
)
@mock_aws
def test_property_9_processed_reply_skip(reply_ids, pre_processed_count):
    """
    Property 9: 処理済みリプライのスキップ

    任意のリプライIDリストに対して:
    - 処理済みテーブルに存在するリプライはスキップされる (False)
    - 存在しないリプライは処理される (True)
    """
    client = boto3.client("dynamodb", region_name="ap-northeast-1")
    _create_table(client)

    # 一部を処理済みとして登録
    actual_pre_processed = min(pre_processed_count, len(reply_ids))
    pre_processed_ids = set(reply_ids[:actual_pre_processed])
    for rid in pre_processed_ids:
        client.put_item(
            TableName=TABLE_NAME,
            Item={"tweet_id": {"S": rid}, "replied_at": {"S": "2026-01-14T10:00:00Z"}},
        )

    processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)

    for rid in reply_ids:
        reply = _make_reply(reply_id=rid)
        mock_api = _mock_x_api_client(tweet_age_days=5)
        mock_ai = _mock_ai_generator()

        result = processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        if rid in pre_processed_ids:
            assert result is False, f"Reply {rid} is pre-processed, should be skipped"
            mock_ai.generate_reply_response.assert_not_called()
        else:
            assert result is True, f"Reply {rid} is not processed, should succeed"


# Feature: group-quote-removal-and-reply-feature
# Property 10: 処理済みリプライの記録
# For any リプライに応答した後、システムはtweet_idをProcessed_Replies_Tableに記録し、
# ttl属性を現在時刻+60日に設定する
@settings(max_examples=100, deadline=None)
@given(
    reply_id=tweet_id_st,
    author_id=user_id_st,
    bot_reply_id=tweet_id_st,
)
@mock_aws
def test_property_10_processed_reply_record(reply_id, author_id, bot_reply_id):
    """
    Property 10: 処理済みリプライの記録

    任意のリプライ処理成功後:
    - tweet_idがProcessed_Replies_Tableに記録される
    - ttl属性が現在時刻+60日（±数秒の誤差許容）に設定される
    - user_idとbot_reply_idが正しく記録される
    """
    client = boto3.client("dynamodb", region_name="ap-northeast-1")
    _create_table(client)

    processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)
    reply = _make_reply(reply_id=reply_id, author_id=author_id)
    mock_api = _mock_x_api_client(tweet_age_days=5, post_result_id=bot_reply_id)
    mock_ai = _mock_ai_generator()

    before = int(time.time())
    result = processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)
    after = int(time.time())

    assert result is True

    # DynamoDBレコードを検証
    response = client.get_item(
        TableName=TABLE_NAME,
        Key={"tweet_id": {"S": reply_id}},
    )
    assert "Item" in response
    item = response["Item"]

    # user_idとbot_reply_idが正しく記録される
    assert item["user_id"]["S"] == author_id
    assert item["bot_reply_id"]["S"] == bot_reply_id

    # TTLが現在時刻+60日（±数秒の誤差許容）
    ttl = int(item["ttl"]["N"])
    expected_min = before + (60 * 24 * 60 * 60)
    expected_max = after + (60 * 24 * 60 * 60)
    assert expected_min <= ttl <= expected_max, (
        f"TTL {ttl} should be between {expected_min} and {expected_max}"
    )


# Feature: group-quote-removal-and-reply-feature
# Property 13: レート制限後の再処理
# For any X APIのレート制限に達した後の次回実行時に、
# システムはレート制限に達していないリプライを再度処理する
@settings(max_examples=100, deadline=None)
@given(
    reply_ids=st.lists(tweet_id_st, min_size=2, max_size=8, unique=True),
    rate_limit_index=st.integers(min_value=0),
)
@mock_aws
def test_property_13_rate_limit_retry(reply_ids, rate_limit_index):
    """
    Property 13: レート制限後の再処理

    任意のリプライリストに対してレート制限が発生した場合:
    - レート制限前に処理されたリプライはProcessed_Replies_Tableに記録される
    - レート制限後の未処理リプライは次回実行時に再処理可能
    - 再処理時、処理済みリプライはスキップされ、未処理リプライのみ処理される
    """
    client = boto3.client("dynamodb", region_name="ap-northeast-1")
    _create_table(client)

    # レート制限が発生するインデックスを調整
    limit_idx = rate_limit_index % len(reply_ids)
    # 少なくとも1つは成功、1つは失敗するようにする
    if limit_idx == 0:
        limit_idx = 1
    if limit_idx >= len(reply_ids):
        limit_idx = len(reply_ids) - 1

    processor = ReplyProcessor(dynamodb_client=client, processed_replies_table_name=TABLE_NAME)

    # 1回目の実行: limit_idx番目でレート制限発生
    processed_ids = set()
    for i, rid in enumerate(reply_ids):
        reply = _make_reply(reply_id=rid)
        mock_api = _mock_x_api_client(tweet_age_days=5, post_result_id=f"bot_{rid}")

        if i >= limit_idx:
            # レート制限をシミュレート
            mock_api.get_tweet.side_effect = Exception("Rate limit exceeded")

        mock_ai = _mock_ai_generator()
        result = processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        if i < limit_idx:
            assert result is True
            processed_ids.add(rid)
        else:
            assert result is False

    # 2回目の実行: 全リプライを再処理
    for rid in reply_ids:
        reply = _make_reply(reply_id=rid)
        mock_api = _mock_x_api_client(tweet_age_days=5, post_result_id=f"bot2_{rid}")
        mock_ai = _mock_ai_generator()

        result = processor.process_reply(reply, ai_generator=mock_ai, x_api_client=mock_api)

        if rid in processed_ids:
            # 処理済みリプライはスキップされる
            assert result is False, f"Reply {rid} was already processed, should be skipped"
        else:
            # 未処理リプライは処理される
            assert result is True, f"Reply {rid} was not processed, should succeed on retry"
