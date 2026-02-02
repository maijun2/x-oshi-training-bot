"""
XPCalculatorクラスのユニットテスト
"""
import pytest
from src.hokuhoku_imomaru_bot.services import XPCalculator, XPRates, ActivityType


class TestXPCalculator:
    """XPCalculatorのテスト"""

    def test_default_rates(self):
        """デフォルトのXPレートが正しいことを確認"""
        calc = XPCalculator()
        assert calc.rates.OSHI_POST == 5.0
        assert calc.rates.GROUP_POST == 2.0
        assert calc.rates.REPOST == 0.5
        assert calc.rates.LIKE == 0.1

    def test_calculate_xp_oshi_post(self):
        """推しの投稿検知のXP計算"""
        calc = XPCalculator()
        assert calc.calculate_xp(ActivityType.OSHI_POST) == 5.0
        assert calc.calculate_xp(ActivityType.OSHI_POST, 3) == 15.0

    def test_calculate_xp_group_post(self):
        """グループの投稿検知のXP計算"""
        calc = XPCalculator()
        assert calc.calculate_xp(ActivityType.GROUP_POST) == 2.0
        assert calc.calculate_xp(ActivityType.GROUP_POST, 5) == 10.0

    def test_calculate_xp_repost(self):
        """リポストのXP計算"""
        calc = XPCalculator()
        assert calc.calculate_xp(ActivityType.REPOST) == 0.5
        assert calc.calculate_xp(ActivityType.REPOST, 10) == 5.0

    def test_calculate_xp_like(self):
        """いいねのXP計算"""
        calc = XPCalculator()
        assert calc.calculate_xp(ActivityType.LIKE) == 0.1
        assert calc.calculate_xp(ActivityType.LIKE, 100) == pytest.approx(10.0)

    def test_calculate_xp_zero_count(self):
        """回数0の場合のXP計算"""
        calc = XPCalculator()
        assert calc.calculate_xp(ActivityType.OSHI_POST, 0) == 0.0

    def test_calculate_xp_negative_count_raises_error(self):
        """負の回数でエラーが発生することを確認"""
        calc = XPCalculator()
        with pytest.raises(ValueError):
            calc.calculate_xp(ActivityType.OSHI_POST, -1)

    def test_calculate_total_xp(self):
        """複数活動の合計XP計算"""
        calc = XPCalculator()
        activities = {
            ActivityType.OSHI_POST: 5,    # 5 * 5.0 = 25.0
            ActivityType.GROUP_POST: 5,   # 5 * 2.0 = 10.0
            ActivityType.REPOST: 10,      # 10 * 0.5 = 5.0
            ActivityType.LIKE: 80,        # 80 * 0.1 = 8.0
        }
        total = calc.calculate_total_xp(activities)
        assert total == pytest.approx(48.0)

    def test_calculate_xp_breakdown(self):
        """XP内訳の計算"""
        calc = XPCalculator()
        breakdown = calc.calculate_xp_breakdown(
            oshi_post_count=5,
            group_post_count=5,
            repost_count=10,
            like_count=80,
        )
        assert breakdown["oshi_post"] == 25.0
        assert breakdown["group_post"] == 10.0
        assert breakdown["repost"] == 5.0
        assert breakdown["like"] == pytest.approx(8.0)

    def test_custom_rates(self):
        """カスタムXPレートの使用"""
        custom_rates = XPRates(
            OSHI_POST=10.0,
            GROUP_POST=4.0,
            REPOST=1.0,
            LIKE=0.2,
        )
        calc = XPCalculator(rates=custom_rates)
        assert calc.calculate_xp(ActivityType.OSHI_POST) == 10.0
        assert calc.calculate_xp(ActivityType.GROUP_POST) == 4.0
