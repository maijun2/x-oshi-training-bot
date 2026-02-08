"""
DailyReporterクラスのユニットテスト

要件 12.1, 12.2, 12.3, 12.4, 12.5: 日報投稿機能を検証
"""
import pytest
from unittest.mock import Mock
from datetime import datetime, timezone, timedelta

from src.hokuhoku_imomaru_bot.services.daily_reporter import (
    DailyReporter,
    DAILY_REPORT_TEMPLATE,
    JST,
    DAILY_REPORT_HOUR,
)
from src.hokuhoku_imomaru_bot.models.bot_state import BotState


def create_test_state(
    daily_oshi_count: int = 5,
    daily_group_count: int = 3,
    daily_repost_count: int = 10,
    daily_like_count: int = 20,
    daily_xp: float = 50.0,
    current_level: int = 10,
    last_daily_report_date: str = None,
) -> BotState:
    """テスト用のBotStateを作成"""
    return BotState(
        cumulative_xp=1000.0,
        current_level=current_level,
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
        last_daily_report_date=last_daily_report_date,
    )


class TestDailyReporter:
    """DailyReporterクラスのテスト"""
    
    @pytest.fixture
    def mock_api_client(self):
        """モックAPIクライアント"""
        return Mock()
    
    @pytest.fixture
    def reporter(self, mock_api_client):
        """DailyReporterインスタンス"""
        return DailyReporter(api_client=mock_api_client)
    
    # should_post_daily_report()のテスト
    def test_should_post_at_21_00_jst(self, reporter):
        """21:00 JSTで日報投稿すべきと判定されることを確認"""
        state = create_test_state(last_daily_report_date=None)
        # 21:00 JST = 12:00 UTC
        current_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        
        result = reporter.should_post_daily_report(state, current_time)
        
        assert result is True
    
    def test_should_post_at_23_00_jst(self, reporter):
        """23:00 JSTで日報投稿すべきと判定されることを確認"""
        state = create_test_state(last_daily_report_date=None)
        # 23:00 JST = 14:00 UTC
        current_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        result = reporter.should_post_daily_report(state, current_time)
        
        assert result is True
    
    def test_should_not_post_before_21_00_jst(self, reporter):
        """21:00 JST前は日報投稿すべきでないと判定されることを確認"""
        state = create_test_state(last_daily_report_date=None)
        # 20:59 JST = 11:59 UTC
        current_time = datetime(2024, 1, 15, 11, 59, 0, tzinfo=timezone.utc)
        
        result = reporter.should_post_daily_report(state, current_time)
        
        assert result is False
    
    def test_should_not_post_if_already_posted_today(self, reporter):
        """今日既に投稿済みの場合は日報投稿すべきでないと判定されることを確認"""
        state = create_test_state(last_daily_report_date="2024-01-15")
        # 21:00 JST = 12:00 UTC
        current_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        
        result = reporter.should_post_daily_report(state, current_time)
        
        assert result is False
    
    def test_should_post_if_posted_yesterday(self, reporter):
        """昨日投稿済みの場合は日報投稿すべきと判定されることを確認"""
        state = create_test_state(last_daily_report_date="2024-01-14")
        # 21:00 JST on 2024-01-15 = 12:00 UTC
        current_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        
        result = reporter.should_post_daily_report(state, current_time)
        
        assert result is True
    
    # generate_daily_report()のテスト
    def test_generate_daily_report_contains_counts(self, reporter):
        """日報テキストに各カウントが含まれることを確認"""
        state = create_test_state(
            daily_oshi_count=5,
            daily_group_count=3,
            daily_repost_count=10,
            daily_like_count=20,
        )
        
        text = reporter.generate_daily_report(state, 500)
        
        assert "5回" in text  # oshi
        assert "3回" in text  # group
        assert "10回" in text  # repost
        assert "20回" in text  # like
    
    def test_generate_daily_report_contains_xp(self, reporter):
        """日報テキストに獲得XPが含まれることを確認"""
        state = create_test_state(daily_xp=50.5)
        
        text = reporter.generate_daily_report(state, 500)
        
        assert "50.5 XP" in text
    
    def test_generate_daily_report_contains_level(self, reporter):
        """日報テキストに現在レベルが含まれることを確認"""
        state = create_test_state(current_level=15)
        
        text = reporter.generate_daily_report(state, 500)
        
        assert "Lv.15" in text
    
    def test_generate_daily_report_contains_next_level_xp(self, reporter):
        """日報テキストに次のレベルまでのXPが含まれることを確認"""
        state = create_test_state()
        
        text = reporter.generate_daily_report(state, 750)
        
        assert "750 XP" in text
    
    def test_generate_daily_report_contains_imo_suffix(self, reporter):
        """日報テキストに「ｲﾓ🍠」が含まれることを確認"""
        state = create_test_state()
        
        text = reporter.generate_daily_report(state, 500)
        
        assert "ｲﾓ🍠" in text
    
    def test_generate_daily_report_contains_hashtags(self, reporter):
        """日報テキストにハッシュタグが含まれることを確認"""
        state = create_test_state()
        
        text = reporter.generate_daily_report(state, 500)
        
        assert "#さつまいもの民" in text
        assert "#びっくえんじぇる" in text

    
    # post_daily_report()のテスト
    def test_post_daily_report_success(self, reporter, mock_api_client):
        """日報投稿が成功した場合にツイートIDを返すことを確認"""
        mock_api_client.post_tweet.return_value = {"data": {"id": "123456789"}}
        state = create_test_state()
        
        result = reporter.post_daily_report(state, 500)
        
        assert result == "123456789"
        mock_api_client.post_tweet.assert_called_once()
    
    def test_post_daily_report_failure(self, reporter, mock_api_client):
        """日報投稿が失敗した場合にNoneを返すことを確認"""
        mock_api_client.post_tweet.return_value = {}
        state = create_test_state()
        
        result = reporter.post_daily_report(state, 500)
        
        assert result is None
    
    def test_post_daily_report_exception(self, reporter, mock_api_client):
        """日報投稿で例外が発生した場合にNoneを返すことを確認"""
        mock_api_client.post_tweet.side_effect = Exception("API Error")
        state = create_test_state()
        
        result = reporter.post_daily_report(state, 500)
        
        assert result is None
    
    # get_today_date_jst()のテスト
    def test_get_today_date_jst(self, reporter):
        """JSTの今日の日付が正しく取得されることを確認"""
        # 2024-01-15 12:00 UTC = 2024-01-15 21:00 JST
        current_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        
        result = reporter.get_today_date_jst(current_time)
        
        assert result == "2024-01-15"
    
    def test_get_today_date_jst_date_change(self, reporter):
        """日付変更線をまたぐ場合のJST日付が正しいことを確認"""
        # 2024-01-15 14:59 UTC = 2024-01-15 23:59 JST
        current_time = datetime(2024, 1, 15, 14, 59, 0, tzinfo=timezone.utc)
        result = reporter.get_today_date_jst(current_time)
        assert result == "2024-01-15"
        
        # 2024-01-15 15:00 UTC = 2024-01-16 00:00 JST
        current_time = datetime(2024, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
        result = reporter.get_today_date_jst(current_time)
        assert result == "2024-01-16"
    
    # エッジケースのテスト
    def test_generate_daily_report_with_zero_counts(self, reporter):
        """カウントが0の場合でも日報が生成されることを確認"""
        state = create_test_state(
            daily_oshi_count=0,
            daily_group_count=0,
            daily_repost_count=0,
            daily_like_count=0,
            daily_xp=0.0,
        )
        
        text = reporter.generate_daily_report(state, 500)
        
        assert "0回" in text
        assert "0.0 XP" in text
    
    def test_generate_daily_report_with_large_counts(self, reporter):
        """大きなカウントでも日報が生成されることを確認"""
        state = create_test_state(
            daily_oshi_count=1000,
            daily_group_count=500,
            daily_repost_count=10000,
            daily_like_count=50000,
            daily_xp=99999.9,
        )
        
        text = reporter.generate_daily_report(state, 1000000)
        
        assert "1000回" in text
        assert "99999.9 XP" in text
