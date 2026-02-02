"""
BotStateデータクラスのユニットテスト

要件 7.2: ボットの状態を正しく管理できることを検証
"""
import pytest
from src.hokuhoku_imomaru_bot.models import BotState


def test_bot_state_default_values():
    """デフォルト値でBotStateが作成されることを確認"""
    state = BotState()
    
    assert state.cumulative_xp == 0.0
    assert state.current_level == 1
    assert state.latest_tweet_id is None
    # 累積カウント
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


def test_bot_state_custom_values():
    """カスタム値でBotStateが作成されることを確認"""
    state = BotState(
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
        last_daily_report_date="2024-01-01",
    )
    
    assert state.cumulative_xp == 100.5
    assert state.current_level == 5
    assert state.latest_tweet_id == "12345"
    assert state.oshi_post_count == 10
    assert state.group_post_count == 5
    assert state.repost_count == 20
    assert state.like_count == 100
    assert state.daily_oshi_count == 2
    assert state.daily_group_count == 1
    assert state.daily_repost_count == 5
    assert state.daily_like_count == 10
    assert state.daily_xp == 15.5
    assert state.last_daily_report_date == "2024-01-01"


def test_bot_state_to_dict():
    """to_dict()が正しい辞書を返すことを確認"""
    state = BotState(
        cumulative_xp=50.0,
        current_level=3,
        latest_tweet_id="67890",
        oshi_post_count=5,
        group_post_count=3,
        repost_count=10,
        like_count=50,
        daily_oshi_count=1,
        daily_group_count=1,
        daily_repost_count=2,
        daily_like_count=5,
        daily_xp=10.0,
        last_daily_report_date="2024-01-15",
    )
    
    result = state.to_dict()
    
    assert result["state_id"] == "current"
    assert result["cumulative_xp"] == 50.0
    assert result["current_level"] == 3
    assert result["latest_tweet_id"] == "67890"
    assert result["oshi_post_count"] == 5
    assert result["group_post_count"] == 3
    assert result["repost_count"] == 10
    assert result["like_count"] == 50
    assert result["daily_oshi_count"] == 1
    assert result["daily_group_count"] == 1
    assert result["daily_repost_count"] == 2
    assert result["daily_like_count"] == 5
    assert result["daily_xp"] == 10.0
    assert result["last_daily_report_date"] == "2024-01-15"


def test_bot_state_from_dict():
    """from_dict()が正しくBotStateを生成することを確認"""
    data = {
        "cumulative_xp": 75.5,
        "current_level": 7,
        "latest_tweet_id": "11111",
        "last_updated": "2024-01-01T00:00:00",
        "oshi_post_count": 8,
        "group_post_count": 4,
        "repost_count": 15,
        "like_count": 80,
        "daily_oshi_count": 2,
        "daily_group_count": 1,
        "daily_repost_count": 3,
        "daily_like_count": 10,
        "daily_xp": 12.5,
        "last_daily_report_date": "2024-01-01",
    }
    
    state = BotState.from_dict(data)
    
    assert state.cumulative_xp == 75.5
    assert state.current_level == 7
    assert state.latest_tweet_id == "11111"
    assert state.last_updated == "2024-01-01T00:00:00"
    assert state.oshi_post_count == 8
    assert state.group_post_count == 4
    assert state.repost_count == 15
    assert state.like_count == 80
    assert state.daily_oshi_count == 2
    assert state.daily_group_count == 1
    assert state.daily_repost_count == 3
    assert state.daily_like_count == 10
    assert state.daily_xp == 12.5
    assert state.last_daily_report_date == "2024-01-01"


def test_bot_state_get_xp_breakdown():
    """get_xp_breakdown()が正しいXP内訳を返すことを確認"""
    state = BotState(
        oshi_post_count=5,   # 5 * 5.0 = 25.0
        group_post_count=3,  # 3 * 2.0 = 6.0
        repost_count=10,     # 10 * 0.5 = 5.0
        like_count=80,       # 80 * 0.1 = 8.0
    )
    
    breakdown = state.get_xp_breakdown()
    
    assert breakdown["oshi_post"] == 25.0
    assert breakdown["group_post"] == 6.0
    assert breakdown["repost"] == 5.0
    assert breakdown["like"] == 8.0


def test_bot_state_get_daily_xp_breakdown():
    """get_daily_xp_breakdown()が正しい日次XP内訳を返すことを確認"""
    state = BotState(
        daily_oshi_count=2,   # 2 * 5.0 = 10.0
        daily_group_count=1,  # 1 * 2.0 = 2.0
        daily_repost_count=4, # 4 * 0.5 = 2.0
        daily_like_count=20,  # 20 * 0.1 = 2.0
    )
    
    breakdown = state.get_daily_xp_breakdown()
    
    assert breakdown["oshi_post"] == 10.0
    assert breakdown["group_post"] == 2.0
    assert breakdown["repost"] == 2.0
    assert breakdown["like"] == 2.0
