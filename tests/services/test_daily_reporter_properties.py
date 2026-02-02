"""
DailyReporterクラスのプロパティベーステスト

Property 11: 日報投稿の内容
Property 12: 日次カウントのリセット
"""
import pytest
from unittest.mock import Mock
from hypothesis import given, settings
from hypothesis import strategies as st

from src.hokuhoku_imomaru_bot.services.daily_reporter import DailyReporter
from src.hokuhoku_imomaru_bot.services.state_store import StateStore
from src.hokuhoku_imomaru_bot.models.bot_state import BotState


def create_reporter():
    """テスト用のDailyReporterインスタンスを作成"""
    mock_api_client = Mock()
    return DailyReporter(api_client=mock_api_client)


def create_test_state(
    daily_oshi_count: int = 0,
    daily_group_count: int = 0,
    daily_repost_count: int = 0,
    daily_like_count: int = 0,
    daily_xp: float = 0.0,
    current_level: int = 1,
) -> BotState:
    """テスト用のBotStateを作成"""
    return BotState(
        cumulative_xp=0.0,
        current_level=current_level,
        latest_tweet_id=None,
        last_updated="2024-01-01T00:00:00Z",
        oshi_post_count=0,
        group_post_count=0,
        repost_count=0,
        like_count=0,
        daily_oshi_count=daily_oshi_count,
        daily_group_count=daily_group_count,
        daily_repost_count=daily_repost_count,
        daily_like_count=daily_like_count,
        daily_xp=daily_xp,
        last_daily_report_date=None,
    )


class TestDailyReporterProperties:
    """DailyReporterのプロパティベーステスト"""
    
    # Property 11: 日報投稿の内容
    @settings(max_examples=100)
    @given(
        daily_oshi_count=st.integers(min_value=0, max_value=1000),
        daily_group_count=st.integers(min_value=0, max_value=1000),
        daily_repost_count=st.integers(min_value=0, max_value=10000),
        daily_like_count=st.integers(min_value=0, max_value=100000),
        daily_xp=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        current_level=st.integers(min_value=1, max_value=99),
        next_level_xp=st.integers(min_value=0, max_value=1000000),
    )
    def test_daily_report_contains_counts_property(
        self,
        daily_oshi_count,
        daily_group_count,
        daily_repost_count,
        daily_like_count,
        daily_xp,
        current_level,
        next_level_xp,
    ):
        """
        **Validates: Requirements 12.2, 12.3, 12.4, 12.5**
        
        Property 11: 日報投稿の内容
        
        任意の日報投稿に対して、今日の各活動タイプの回数が含まれるべきである
        """
        reporter = create_reporter()
        state = create_test_state(
            daily_oshi_count=daily_oshi_count,
            daily_group_count=daily_group_count,
            daily_repost_count=daily_repost_count,
            daily_like_count=daily_like_count,
            daily_xp=daily_xp,
            current_level=current_level,
        )
        
        text = reporter.generate_daily_report(state, next_level_xp)
        
        # 各活動タイプの回数が含まれていることを確認
        assert f"{daily_oshi_count}回" in text
        assert f"{daily_group_count}回" in text
        assert f"{daily_repost_count}回" in text
        assert f"{daily_like_count}回" in text
    
    @settings(max_examples=100)
    @given(
        daily_xp=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        current_level=st.integers(min_value=1, max_value=99),
        next_level_xp=st.integers(min_value=0, max_value=1000000),
    )
    def test_daily_report_contains_xp_property(
        self,
        daily_xp,
        current_level,
        next_level_xp,
    ):
        """
        **Validates: Requirements 12.2, 12.3, 12.4, 12.5**
        
        Property 11: 日報投稿の内容
        
        任意の日報投稿に対して、今日の獲得XPが含まれるべきである
        """
        reporter = create_reporter()
        state = create_test_state(
            daily_xp=daily_xp,
            current_level=current_level,
        )
        
        text = reporter.generate_daily_report(state, next_level_xp)
        
        # 獲得XPが含まれていることを確認（小数点1桁）
        assert f"{daily_xp:.1f} XP" in text
    
    @settings(max_examples=100)
    @given(
        current_level=st.integers(min_value=1, max_value=99),
        next_level_xp=st.integers(min_value=0, max_value=1000000),
    )
    def test_daily_report_contains_level_property(
        self,
        current_level,
        next_level_xp,
    ):
        """
        **Validates: Requirements 12.2, 12.3, 12.4, 12.5**
        
        Property 11: 日報投稿の内容
        
        任意の日報投稿に対して、現在のレベルと次のレベルまでの必要XPが含まれるべきである
        """
        reporter = create_reporter()
        state = create_test_state(current_level=current_level)
        
        text = reporter.generate_daily_report(state, next_level_xp)
        
        # レベルと次のレベルまでのXPが含まれていることを確認
        assert f"Lv.{current_level}" in text
        assert f"{next_level_xp} XP" in text
    
    @settings(max_examples=100)
    @given(
        current_level=st.integers(min_value=1, max_value=99),
        next_level_xp=st.integers(min_value=0, max_value=1000000),
    )
    def test_daily_report_contains_imo_suffix_property(
        self,
        current_level,
        next_level_xp,
    ):
        """
        **Validates: Requirements 12.2, 12.3, 12.4, 12.5**
        
        Property 11: 日報投稿の内容
        
        任意の日報投稿に対して、語尾「◯◯ｲﾓ🍠」が含まれるべきである
        """
        reporter = create_reporter()
        state = create_test_state(current_level=current_level)
        
        text = reporter.generate_daily_report(state, next_level_xp)
        
        assert "ｲﾓ🍠" in text
    
    @settings(max_examples=100)
    @given(
        current_level=st.integers(min_value=1, max_value=99),
        next_level_xp=st.integers(min_value=0, max_value=1000000),
    )
    def test_daily_report_contains_hashtags_property(
        self,
        current_level,
        next_level_xp,
    ):
        """
        **Validates: Requirements 12.2, 12.3, 12.4, 12.5**
        
        Property 11: 日報投稿の内容
        
        任意の日報投稿に対して、ハッシュタグ「#さつまいもの民 #びっくえんじぇる」が含まれるべきである
        """
        reporter = create_reporter()
        state = create_test_state(current_level=current_level)
        
        text = reporter.generate_daily_report(state, next_level_xp)
        
        assert "#さつまいもの民" in text
        assert "#びっくえんじぇる" in text



class TestDailyCountResetProperties:
    """日次カウントリセットのプロパティベーステスト"""
    
    # Property 12: 日次カウントのリセット
    @settings(max_examples=100)
    @given(
        daily_oshi_count=st.integers(min_value=0, max_value=1000),
        daily_group_count=st.integers(min_value=0, max_value=1000),
        daily_repost_count=st.integers(min_value=0, max_value=10000),
        daily_like_count=st.integers(min_value=0, max_value=100000),
        daily_xp=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    )
    def test_reset_daily_counts_property(
        self,
        daily_oshi_count,
        daily_group_count,
        daily_repost_count,
        daily_like_count,
        daily_xp,
    ):
        """
        **Validates: Requirements 12.6, 7.7**
        
        Property 12: 日次カウントのリセット
        
        任意の日報投稿後に対して、日次活動カウント
        （daily_oshi_count, daily_group_count, daily_repost_count, daily_like_count, daily_xp）
        はすべて0にリセットされるべきである
        """
        # 日次カウントを持つ状態を作成
        state = BotState(
            cumulative_xp=1000.0,
            current_level=10,
            latest_tweet_id="123456",
            last_updated="2024-01-01T12:00:00Z",
            oshi_post_count=100,
            group_post_count=50,
            repost_count=200,
            like_count=500,
            daily_oshi_count=daily_oshi_count,
            daily_group_count=daily_group_count,
            daily_repost_count=daily_repost_count,
            daily_like_count=daily_like_count,
            daily_xp=daily_xp,
            last_daily_report_date=None,
        )
        
        # StateStoreのreset_daily_counts()を使用してリセット
        mock_dynamodb = Mock()
        store = StateStore(dynamodb_client=mock_dynamodb, state_table_name="test-table")
        reset_state = store.reset_daily_counts(state)
        
        # すべての日次カウントが0にリセットされていることを確認
        assert reset_state.daily_oshi_count == 0
        assert reset_state.daily_group_count == 0
        assert reset_state.daily_repost_count == 0
        assert reset_state.daily_like_count == 0
        assert reset_state.daily_xp == 0.0
    
    @settings(max_examples=100)
    @given(
        cumulative_xp=st.floats(min_value=0.0, max_value=1000000.0, allow_nan=False, allow_infinity=False),
        current_level=st.integers(min_value=1, max_value=99),
        oshi_post_count=st.integers(min_value=0, max_value=10000),
        group_post_count=st.integers(min_value=0, max_value=10000),
        repost_count=st.integers(min_value=0, max_value=100000),
        like_count=st.integers(min_value=0, max_value=1000000),
    )
    def test_reset_preserves_cumulative_counts_property(
        self,
        cumulative_xp,
        current_level,
        oshi_post_count,
        group_post_count,
        repost_count,
        like_count,
    ):
        """
        **Validates: Requirements 12.6, 7.7**
        
        Property 12: 日次カウントのリセット
        
        日次カウントのリセット後も、累積カウントは保持されるべきである
        """
        state = BotState(
            cumulative_xp=cumulative_xp,
            current_level=current_level,
            latest_tweet_id="123456",
            last_updated="2024-01-01T12:00:00Z",
            oshi_post_count=oshi_post_count,
            group_post_count=group_post_count,
            repost_count=repost_count,
            like_count=like_count,
            daily_oshi_count=10,
            daily_group_count=5,
            daily_repost_count=20,
            daily_like_count=50,
            daily_xp=100.0,
            last_daily_report_date=None,
        )
        
        mock_dynamodb = Mock()
        store = StateStore(dynamodb_client=mock_dynamodb, state_table_name="test-table")
        reset_state = store.reset_daily_counts(state)
        
        # 累積カウントが保持されていることを確認
        assert reset_state.cumulative_xp == cumulative_xp
        assert reset_state.current_level == current_level
        assert reset_state.oshi_post_count == oshi_post_count
        assert reset_state.group_post_count == group_post_count
        assert reset_state.repost_count == repost_count
        assert reset_state.like_count == like_count
