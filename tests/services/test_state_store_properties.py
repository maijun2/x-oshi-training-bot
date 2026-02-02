"""
StateStoreクラスのプロパティベーステスト

Property 2: 状態の永続化ラウンドトリップ
Property 7: 浮動小数点XPの精度
"""
import pytest
import boto3
from moto import mock_aws
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from src.hokuhoku_imomaru_bot.services import StateStore
from src.hokuhoku_imomaru_bot.models import BotState


def create_dynamodb_tables(client):
    """DynamoDBテーブルを作成するヘルパー関数"""
    # BotStateテーブルを作成
    client.create_table(
        TableName="imomaru-bot-state",
        KeySchema=[{"AttributeName": "state_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "state_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


# DynamoDBの数値範囲制限（1E-130 ~ 1E+126）を考慮した現実的なXP範囲
# XPは0.1（いいね1回）から始まるため、0.0または0.1以上の値に制限
# 非常に小さな浮動小数点数（1E-130未満）はDynamoDBでサポートされない
xp_strategy = st.one_of(
    st.just(0.0),  # 初期値
    st.floats(min_value=0.1, max_value=1000000.0, allow_nan=False, allow_infinity=False)
)

# 日付文字列のストラテジー（YYYY-MM-DD形式）
date_strategy = st.one_of(
    st.none(),
    st.dates().map(lambda d: d.strftime("%Y-%m-%d"))
)


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    cumulative_xp=xp_strategy,
    current_level=st.integers(min_value=1, max_value=99),
    latest_tweet_id=st.one_of(st.none(), st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Nd', 'L')))),
    oshi_post_count=st.integers(min_value=0, max_value=100000),
    group_post_count=st.integers(min_value=0, max_value=100000),
    repost_count=st.integers(min_value=0, max_value=100000),
    like_count=st.integers(min_value=0, max_value=100000),
    daily_oshi_count=st.integers(min_value=0, max_value=1000),
    daily_group_count=st.integers(min_value=0, max_value=1000),
    daily_repost_count=st.integers(min_value=0, max_value=1000),
    daily_like_count=st.integers(min_value=0, max_value=1000),
    daily_xp=xp_strategy,
    last_daily_report_date=date_strategy,
)
def test_state_persistence_roundtrip(
    cumulative_xp,
    current_level,
    latest_tweet_id,
    oshi_post_count,
    group_post_count,
    repost_count,
    like_count,
    daily_oshi_count,
    daily_group_count,
    daily_repost_count,
    daily_like_count,
    daily_xp,
    last_daily_report_date,
):
    """
    Feature: hokuhoku-imomaru-bot, Property 2: 状態の永続化ラウンドトリップ
    
    *任意の*ボット状態（累積XP、現在レベル、最新Tweet ID、日次カウント）に対して、
    状態を保存してから読み込むと、元の状態と等しい状態が返されるべきである
    
    **Validates: Requirements 1.3, 3.5, 4.4, 7.2, 7.3, 12.6**
    """
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        create_dynamodb_tables(client)
        store = StateStore(client)
        
        # 元の状態を作成
        original_state = BotState(
            cumulative_xp=cumulative_xp,
            current_level=current_level,
            latest_tweet_id=latest_tweet_id,
            oshi_post_count=oshi_post_count,
            group_post_count=group_post_count,
            repost_count=repost_count,
            like_count=like_count,
            daily_oshi_count=daily_oshi_count,
            daily_group_count=daily_group_count,
            daily_repost_count=daily_repost_count,
            daily_like_count=daily_like_count,
            daily_xp=daily_xp,
            last_daily_report_date=last_daily_report_date,
        )
        
        # 状態を保存
        store.save_state(original_state)
        
        # 状態を読み込み
        loaded_state = store.load_state()
        
        # 検証（last_updated以外のフィールドが一致することを確認）
        assert loaded_state.cumulative_xp == pytest.approx(cumulative_xp, rel=1e-9)
        assert loaded_state.current_level == current_level
        assert loaded_state.latest_tweet_id == latest_tweet_id
        assert loaded_state.oshi_post_count == oshi_post_count
        assert loaded_state.group_post_count == group_post_count
        assert loaded_state.repost_count == repost_count
        assert loaded_state.like_count == like_count
        # 日次カウント
        assert loaded_state.daily_oshi_count == daily_oshi_count
        assert loaded_state.daily_group_count == daily_group_count
        assert loaded_state.daily_repost_count == daily_repost_count
        assert loaded_state.daily_like_count == daily_like_count
        assert loaded_state.daily_xp == pytest.approx(daily_xp, rel=1e-9)
        assert loaded_state.last_daily_report_date == last_daily_report_date


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(xp_value=xp_strategy)
def test_float_xp_precision(xp_value):
    """
    Feature: hokuhoku-imomaru-bot, Property 7: 浮動小数点XPの精度
    
    *任意の*浮動小数点XP値に対して、保存してから読み込むと、
    元の値と等しい値が返されるべきである（浮動小数点の精度内で）
    
    **Validates: Requirements 3.6**
    """
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        create_dynamodb_tables(client)
        store = StateStore(client)
        
        # XP値を持つ状態を作成
        original_state = BotState(cumulative_xp=xp_value)
        
        # 状態を保存
        store.save_state(original_state)
        
        # 状態を読み込み
        loaded_state = store.load_state()
        
        # 浮動小数点の精度内で一致することを確認
        assert loaded_state.cumulative_xp == pytest.approx(xp_value, rel=1e-9)


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(daily_xp_value=xp_strategy)
def test_float_daily_xp_precision(daily_xp_value):
    """
    Feature: hokuhoku-imomaru-bot, Property 7: 浮動小数点XPの精度（日次XP）
    
    *任意の*浮動小数点日次XP値に対して、保存してから読み込むと、
    元の値と等しい値が返されるべきである（浮動小数点の精度内で）
    
    **Validates: Requirements 3.6, 12.3**
    """
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        create_dynamodb_tables(client)
        store = StateStore(client)
        
        # 日次XP値を持つ状態を作成
        original_state = BotState(daily_xp=daily_xp_value)
        
        # 状態を保存
        store.save_state(original_state)
        
        # 状態を読み込み
        loaded_state = store.load_state()
        
        # 浮動小数点の精度内で一致することを確認
        assert loaded_state.daily_xp == pytest.approx(daily_xp_value, rel=1e-9)
