"""
StateStoreクラスのユニットテスト

要件 7.1, 7.2, 7.3, 7.7, 4.1: 状態管理とDQ3経験値テーブルの読み込みを検証
"""
import pytest
import boto3
from moto import mock_aws
from src.hokuhoku_imomaru_bot.services import StateStore
from src.hokuhoku_imomaru_bot.services import TweetAlreadyProcessedError
from src.hokuhoku_imomaru_bot.models import BotState


@pytest.fixture
def dynamodb_client():
    """モックDynamoDBクライアントを作成"""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        
        # BotStateテーブルを作成
        client.create_table(
            TableName="imomaru-bot-state",
            KeySchema=[{"AttributeName": "state_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "state_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        
        # XPTableテーブルを作成
        client.create_table(
            TableName="imomaru-bot-xp-table",
            KeySchema=[{"AttributeName": "level", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "level", "AttributeType": "N"}],
            BillingMode="PAY_PER_REQUEST",
        )
        
        yield client


def test_load_state_returns_default_when_empty(dynamodb_client):
    """状態が存在しない場合、デフォルト値を返すことを確認"""
    store = StateStore(dynamodb_client)
    
    state = store.load_state()
    
    assert state.cumulative_xp == 0.0
    assert state.current_level == 1
    assert state.latest_tweet_id is None
    assert state.oshi_post_count == 0
    assert state.group_post_count == 0
    assert state.repost_count == 0
    assert state.like_count == 0
    # 日次カウント
    assert state.daily_oshi_count == 0
    assert state.daily_group_count == 0
    assert state.daily_repost_count == 0
    assert state.daily_like_count == 0
    assert state.daily_xp == 0.0
    assert state.last_daily_report_date is None


def test_save_and_load_state(dynamodb_client):
    """状態を保存して読み込めることを確認"""
    store = StateStore(dynamodb_client)
    
    # 状態を保存
    original_state = BotState(
        cumulative_xp=100.5,
        current_level=5,
        latest_tweet_id="12345",
        oshi_post_count=10,
        group_post_count=5,
        repost_count=20,
        like_count=100,
        daily_oshi_count=2,
        daily_group_count=1,
        daily_repost_count=5,
        daily_like_count=10,
        daily_xp=15.5,
        last_daily_report_date="2024-01-15",
    )
    store.save_state(original_state)
    
    # 状態を読み込み
    loaded_state = store.load_state()
    
    assert loaded_state.cumulative_xp == 100.5
    assert loaded_state.current_level == 5
    assert loaded_state.latest_tweet_id == "12345"
    assert loaded_state.oshi_post_count == 10
    assert loaded_state.group_post_count == 5
    assert loaded_state.repost_count == 20
    assert loaded_state.like_count == 100
    assert loaded_state.daily_oshi_count == 2
    assert loaded_state.daily_group_count == 1
    assert loaded_state.daily_repost_count == 5
    assert loaded_state.daily_like_count == 10
    assert loaded_state.daily_xp == 15.5
    assert loaded_state.last_daily_report_date == "2024-01-15"


def test_save_state_without_tweet_id(dynamodb_client):
    """latest_tweet_idがNoneの状態を保存できることを確認"""
    store = StateStore(dynamodb_client)
    
    state = BotState(
        cumulative_xp=50.0,
        current_level=3,
        latest_tweet_id=None,
    )
    result = store.save_state(state)
    
    assert result is True
    
    loaded_state = store.load_state()
    assert loaded_state.latest_tweet_id is None


def test_save_state_without_daily_report_date(dynamodb_client):
    """last_daily_report_dateがNoneの状態を保存できることを確認"""
    store = StateStore(dynamodb_client)
    
    state = BotState(
        cumulative_xp=50.0,
        current_level=3,
        last_daily_report_date=None,
    )
    result = store.save_state(state)
    
    assert result is True
    
    loaded_state = store.load_state()
    assert loaded_state.last_daily_report_date is None


def test_load_xp_table(dynamodb_client):
    """DQ3経験値テーブルを読み込めることを確認"""
    store = StateStore(dynamodb_client)
    
    # テストデータを投入
    test_data = [
        {"level": 1, "required_xp": 0},
        {"level": 2, "required_xp": 7},
        {"level": 3, "required_xp": 23},
        {"level": 4, "required_xp": 47},
        {"level": 5, "required_xp": 110},
    ]
    
    for item in test_data:
        dynamodb_client.put_item(
            TableName="imomaru-bot-xp-table",
            Item={
                "level": {"N": str(item["level"])},
                "required_xp": {"N": str(item["required_xp"])},
            },
        )
    
    # 経験値テーブルを読み込み
    xp_table = store.load_xp_table()
    
    assert len(xp_table) == 5
    assert xp_table[1] == 0
    assert xp_table[2] == 7
    assert xp_table[3] == 23
    assert xp_table[4] == 47
    assert xp_table[5] == 110


def test_load_xp_table_empty(dynamodb_client):
    """空の経験値テーブルを読み込めることを確認"""
    store = StateStore(dynamodb_client)
    
    xp_table = store.load_xp_table()
    
    assert len(xp_table) == 0


def test_save_state_updates_last_updated(dynamodb_client):
    """save_state()がlast_updatedを更新することを確認"""
    store = StateStore(dynamodb_client)
    
    state = BotState(
        cumulative_xp=10.0,
        current_level=2,
        last_updated="2020-01-01T00:00:00",
    )
    store.save_state(state)
    
    loaded_state = store.load_state()
    
    # last_updatedが更新されていることを確認（2020年ではない）
    assert not loaded_state.last_updated.startswith("2020")


def test_reset_daily_counts(dynamodb_client):
    """reset_daily_counts()が日次カウントをリセットすることを確認"""
    store = StateStore(dynamodb_client)
    
    state = BotState(
        cumulative_xp=100.0,
        current_level=5,
        daily_oshi_count=3,
        daily_group_count=2,
        daily_repost_count=10,
        daily_like_count=50,
        daily_xp=25.5,
    )
    
    # 日次カウントをリセット
    reset_state = store.reset_daily_counts(state)
    
    # 日次カウントがリセットされていることを確認
    assert reset_state.daily_oshi_count == 0
    assert reset_state.daily_group_count == 0
    assert reset_state.daily_repost_count == 0
    assert reset_state.daily_like_count == 0
    assert reset_state.daily_xp == 0.0
    
    # 累積カウントは変更されていないことを確認
    assert reset_state.cumulative_xp == 100.0
    assert reset_state.current_level == 5


def test_reset_daily_counts_saves_prev_oshi_count(dynamodb_client):
    """reset_daily_counts()がprev_daily_oshi_countに前日の値を保存することを確認"""
    store = StateStore(dynamodb_client)

    state = BotState(
        daily_oshi_count=7,
        daily_group_count=3,
        daily_repost_count=5,
        daily_like_count=10,
        daily_xp=20.0,
        prev_daily_oshi_count=0,
    )

    reset_state = store.reset_daily_counts(state)

    # 前日の推し投稿数が保存されている
    assert reset_state.prev_daily_oshi_count == 7
    # 当日カウントはリセット
    assert reset_state.daily_oshi_count == 0


def test_reset_daily_counts_resets_image_posted_flag(dynamodb_client):
    """reset_daily_counts()がdaily_image_postedフラグをリセットすることを確認"""
    store = StateStore(dynamodb_client)

    state = BotState(
        daily_image_posted=True,
        daily_oshi_count=1,
    )

    reset_state = store.reset_daily_counts(state)

    assert reset_state.daily_image_posted is False


def test_save_and_load_state_with_profile_update_month(dynamodb_client):
    """last_profile_update_monthを含む状態を保存・読み込みできることを確認"""
    store = StateStore(dynamodb_client)

    state = BotState(
        cumulative_xp=200.0,
        current_level=10,
        last_profile_update_month="2024-01",
    )
    store.save_state(state)

    loaded = store.load_state()
    assert loaded.last_profile_update_month == "2024-01"


def test_save_and_load_state_with_prev_daily_oshi_count(dynamodb_client):
    """prev_daily_oshi_countを含む状態を保存・読み込みできることを確認"""
    store = StateStore(dynamodb_client)

    state = BotState(
        cumulative_xp=50.0,
        current_level=3,
        prev_daily_oshi_count=5,
    )
    store.save_state(state)

    loaded = store.load_state()
    assert loaded.prev_daily_oshi_count == 5


@pytest.fixture
def dynamodb_client_with_all_tables():
    """全テーブルを含むモックDynamoDBクライアント"""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ap-northeast-1")

        # BotStateテーブル
        client.create_table(
            TableName="imomaru-bot-state",
            KeySchema=[{"AttributeName": "state_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "state_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # XPTableテーブル
        client.create_table(
            TableName="imomaru-bot-xp-table",
            KeySchema=[{"AttributeName": "level", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "level", "AttributeType": "N"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # ProcessedTweetsテーブル
        client.create_table(
            TableName="imomaru-bot-processed-tweets",
            KeySchema=[{"AttributeName": "tweet_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "tweet_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # EmotionImagesテーブル
        client.create_table(
            TableName="imomaru-bot-emotion-images",
            KeySchema=[{"AttributeName": "emotion_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "emotion_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        yield client


def test_get_emotion_image_filename_found(dynamodb_client_with_all_tables):
    """感情画像ファイル名を取得できることを確認"""
    client = dynamodb_client_with_all_tables
    store = StateStore(client)

    # テストデータ投入
    client.put_item(
        TableName="imomaru-bot-emotion-images",
        Item={
            "emotion_key": {"S": "joy"},
            "filename": {"S": "imomaru_joy.png"},
        },
    )

    result = store.get_emotion_image_filename("joy")
    assert result == "imomaru_joy.png"


def test_get_emotion_image_filename_not_found(dynamodb_client_with_all_tables):
    """存在しない感情キーでNoneを返すことを確認"""
    store = StateStore(dynamodb_client_with_all_tables)

    result = store.get_emotion_image_filename("nonexistent")
    assert result is None


def test_get_emotion_image_filename_error():
    """DynamoDBエラー時にNoneを返すことを確認"""
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.get_item.side_effect = Exception("DynamoDB error")

    store = StateStore(mock_client)
    result = store.get_emotion_image_filename("joy")
    assert result is None


def test_acquire_tweet_lock_success(dynamodb_client_with_all_tables):
    """ツイートロックを取得できることを確認"""
    store = StateStore(dynamodb_client_with_all_tables)

    result = store.acquire_tweet_lock("tweet_001", "quote_oshi")
    assert result is True


def test_acquire_tweet_lock_already_processed(dynamodb_client_with_all_tables):
    """既に処理済みのツイートでTweetAlreadyProcessedErrorが発生することを確認"""
    store = StateStore(dynamodb_client_with_all_tables)

    store.acquire_tweet_lock("tweet_002", "quote_oshi")

    with pytest.raises(TweetAlreadyProcessedError):
        store.acquire_tweet_lock("tweet_002", "quote_oshi")


def test_is_tweet_processed_true(dynamodb_client_with_all_tables):
    """処理済みツイートがTrueを返すことを確認"""
    store = StateStore(dynamodb_client_with_all_tables)

    store.acquire_tweet_lock("tweet_003", "quote_oshi")
    assert store.is_tweet_processed("tweet_003") is True


def test_is_tweet_processed_false(dynamodb_client_with_all_tables):
    """未処理ツイートがFalseを返すことを確認"""
    store = StateStore(dynamodb_client_with_all_tables)

    assert store.is_tweet_processed("tweet_999") is False


def test_is_tweet_processed_error():
    """DynamoDBエラー時にFalseを返すことを確認"""
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.get_item.side_effect = Exception("DynamoDB error")

    store = StateStore(mock_client)
    assert store.is_tweet_processed("tweet_001") is False


def test_load_state_raises_on_dynamodb_error():
    """load_stateがDynamoDBエラー時に例外を再送出することを確認"""
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.get_item.side_effect = Exception("DynamoDB connection error")

    store = StateStore(mock_client)

    with pytest.raises(Exception, match="DynamoDB connection error"):
        store.load_state()


def test_save_state_raises_on_dynamodb_error():
    """save_stateがDynamoDBエラー時に例外を再送出することを確認"""
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.put_item.side_effect = Exception("DynamoDB write error")

    store = StateStore(mock_client)
    state = BotState(cumulative_xp=10.0, current_level=2)

    with pytest.raises(Exception, match="DynamoDB write error"):
        store.save_state(state)


def test_load_xp_table_with_pagination():
    """load_xp_tableがページネーションを正しく処理することを確認"""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    # 1回目: LastEvaluatedKey付き（次ページあり）
    mock_client.scan.side_effect = [
        {
            "Items": [
                {"level": {"N": "1"}, "required_xp": {"N": "0"}},
                {"level": {"N": "2"}, "required_xp": {"N": "7"}},
            ],
            "LastEvaluatedKey": {"level": {"N": "2"}},
        },
        # 2回目: 最終ページ
        {
            "Items": [
                {"level": {"N": "3"}, "required_xp": {"N": "23"}},
            ],
        },
    ]

    store = StateStore(mock_client)
    xp_table = store.load_xp_table()

    assert len(xp_table) == 3
    assert xp_table[1] == 0
    assert xp_table[2] == 7
    assert xp_table[3] == 23
    assert mock_client.scan.call_count == 2


def test_acquire_tweet_lock_raises_on_other_client_error():
    """acquire_tweet_lockがConditionalCheckFailedException以外のClientErrorを再送出することを確認"""
    from unittest.mock import MagicMock
    from botocore.exceptions import ClientError

    mock_client = MagicMock()
    mock_client.put_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "Rate exceeded"}},
        "PutItem",
    )

    store = StateStore(mock_client)

    with pytest.raises(ClientError):
        store.acquire_tweet_lock("tweet_999", "quote_oshi")
