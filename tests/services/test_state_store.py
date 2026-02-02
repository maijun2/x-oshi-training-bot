"""
StateStoreクラスのユニットテスト

要件 7.1, 7.2, 7.3, 7.7, 4.1: 状態管理とDQ3経験値テーブルの読み込みを検証
"""
import pytest
import boto3
from moto import mock_aws
from src.hokuhoku_imomaru_bot.services import StateStore
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
