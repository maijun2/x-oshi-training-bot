"""
LevelManagerクラスのユニットテスト
"""
import pytest
from src.hokuhoku_imomaru_bot.services import LevelManager


# テスト用の簡易経験値テーブル
SIMPLE_XP_TABLE = {
    1: 0,
    2: 14,
    3: 31,
    4: 51,
    5: 76,
}


class TestLevelManager:
    """LevelManagerのテスト"""

    def test_init_with_empty_table_raises_error(self):
        """空のテーブルでエラーが発生することを確認"""
        with pytest.raises(ValueError):
            LevelManager({})

    def test_max_level(self):
        """最大レベルが正しく設定されることを確認"""
        manager = LevelManager(SIMPLE_XP_TABLE)
        assert manager.max_level == 5

    def test_get_required_xp(self):
        """必要経験値の取得"""
        manager = LevelManager(SIMPLE_XP_TABLE)
        assert manager.get_required_xp(1) == 0
        assert manager.get_required_xp(2) == 14
        assert manager.get_required_xp(5) == 76
        assert manager.get_required_xp(99) is None

    def test_get_xp_to_next_level(self):
        """次のレベルまでの経験値計算"""
        manager = LevelManager(SIMPLE_XP_TABLE)
        # レベル1、XP 0 → レベル2まで14必要
        assert manager.get_xp_to_next_level(1, 0) == 14
        # レベル1、XP 10 → レベル2まで4必要
        assert manager.get_xp_to_next_level(1, 10) == 4
        # レベル4、XP 51 → レベル5まで25必要
        assert manager.get_xp_to_next_level(4, 51) == 25

    def test_get_xp_to_next_level_at_max(self):
        """最大レベルでの次レベル経験値"""
        manager = LevelManager(SIMPLE_XP_TABLE)
        assert manager.get_xp_to_next_level(5, 100) is None

    def test_calculate_level(self):
        """累積経験値からレベル計算"""
        manager = LevelManager(SIMPLE_XP_TABLE)
        assert manager.calculate_level(0) == 1
        assert manager.calculate_level(13) == 1
        assert manager.calculate_level(14) == 2
        assert manager.calculate_level(30) == 2
        assert manager.calculate_level(31) == 3
        assert manager.calculate_level(76) == 5
        assert manager.calculate_level(1000) == 5

    def test_check_level_up_no_change(self):
        """レベルアップなしの判定"""
        manager = LevelManager(SIMPLE_XP_TABLE)
        leveled_up, new_level = manager.check_level_up(1, 10)
        assert leveled_up is False
        assert new_level == 1

    def test_check_level_up_single_level(self):
        """1レベルアップの判定"""
        manager = LevelManager(SIMPLE_XP_TABLE)
        leveled_up, new_level = manager.check_level_up(1, 14)
        assert leveled_up is True
        assert new_level == 2

    def test_check_level_up_multiple_levels(self):
        """複数レベルアップの判定"""
        manager = LevelManager(SIMPLE_XP_TABLE)
        leveled_up, new_level = manager.check_level_up(1, 51)
        assert leveled_up is True
        assert new_level == 4

    def test_check_level_up_at_max(self):
        """最大レベルでのレベルアップ判定"""
        manager = LevelManager(SIMPLE_XP_TABLE)
        leveled_up, new_level = manager.check_level_up(5, 1000)
        assert leveled_up is False
        assert new_level == 5

    def test_get_level_progress(self):
        """レベル進捗情報の取得"""
        manager = LevelManager(SIMPLE_XP_TABLE)
        progress = manager.get_level_progress(2, 20)
        
        assert progress["current_level"] == 2
        assert progress["cumulative_xp"] == 20
        assert progress["current_level_xp"] == 14
        assert progress["next_level_xp"] == 31
        assert progress["xp_to_next_level"] == 11
        assert progress["is_max_level"] is False
        # 進捗率: (20-14)/(31-14) = 6/17 ≈ 35.3%
        assert progress["progress_percent"] == pytest.approx(35.29, rel=0.01)

    def test_get_level_progress_at_max(self):
        """最大レベルでの進捗情報"""
        manager = LevelManager(SIMPLE_XP_TABLE)
        progress = manager.get_level_progress(5, 100)
        
        assert progress["is_max_level"] is True
        assert progress["xp_to_next_level"] is None
        assert progress["progress_percent"] == 100.0
