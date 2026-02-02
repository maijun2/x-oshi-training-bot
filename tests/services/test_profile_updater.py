"""
ProfileUpdaterクラスのユニットテスト

要件 6.1, 6.2, 6.3, 6.4, 6.5, 6.7: プロフィール更新とレベルアップ投稿を検証
"""
import pytest
from unittest.mock import Mock, MagicMock
from io import BytesIO

from src.hokuhoku_imomaru_bot.services.profile_updater import (
    ProfileUpdater,
    PROFILE_NAME_TEMPLATE,
    LEVEL_UP_TEMPLATE,
)


class TestProfileUpdater:
    """ProfileUpdaterクラスのテスト"""
    
    @pytest.fixture
    def mock_api_client(self):
        """モックAPIクライアント"""
        return Mock()
    
    @pytest.fixture
    def updater(self, mock_api_client):
        """ProfileUpdaterインスタンス"""
        return ProfileUpdater(api_client=mock_api_client)
    
    # プロフィール名生成のテスト
    def test_generate_profile_name_level_1(self, updater):
        """レベル1のプロフィール名が正しく生成されることを確認"""
        name = updater.generate_profile_name(1)
        assert name == "ほくほくいも丸くん🍠Lv.1"
    
    def test_generate_profile_name_level_50(self, updater):
        """レベル50のプロフィール名が正しく生成されることを確認"""
        name = updater.generate_profile_name(50)
        assert name == "ほくほくいも丸くん🍠Lv.50"
    
    def test_generate_profile_name_level_99(self, updater):
        """レベル99のプロフィール名が正しく生成されることを確認"""
        name = updater.generate_profile_name(99)
        assert name == "ほくほくいも丸くん🍠Lv.99"
    
    def test_generate_profile_name_contains_emoji(self, updater):
        """プロフィール名に🍠絵文字が含まれることを確認"""
        name = updater.generate_profile_name(10)
        assert "🍠" in name
    
    def test_generate_profile_name_format(self, updater):
        """プロフィール名が正しいフォーマットであることを確認"""
        for level in [1, 10, 50, 99]:
            name = updater.generate_profile_name(level)
            expected = f"ほくほくいも丸くん🍠Lv.{level}"
            assert name == expected
    
    # プロフィール画像更新のテスト
    def test_update_profile_image_success(self, updater, mock_api_client):
        """プロフィール画像更新が成功することを確認"""
        mock_api_client.update_profile_image.return_value = True
        image_data = BytesIO(b"fake image data")
        
        result = updater.update_profile_image(image_data)
        
        assert result is True
        mock_api_client.update_profile_image.assert_called_once()
    
    def test_update_profile_image_failure(self, updater, mock_api_client):
        """プロフィール画像更新が失敗した場合にFalseを返すことを確認"""
        mock_api_client.update_profile_image.return_value = False
        image_data = BytesIO(b"fake image data")
        
        result = updater.update_profile_image(image_data)
        
        assert result is False
    
    def test_update_profile_image_exception(self, updater, mock_api_client):
        """プロフィール画像更新で例外が発生した場合にFalseを返すことを確認"""
        mock_api_client.update_profile_image.side_effect = Exception("API Error")
        image_data = BytesIO(b"fake image data")
        
        result = updater.update_profile_image(image_data)
        
        assert result is False
    
    # プロフィール名更新のテスト
    def test_update_profile_name_success(self, updater, mock_api_client):
        """プロフィール名更新が成功することを確認"""
        mock_api_client.update_profile.return_value = True
        
        result = updater.update_profile_name(10)
        
        assert result is True
        mock_api_client.update_profile.assert_called_once_with(
            name="ほくほくいも丸くん🍠Lv.10"
        )
    
    def test_update_profile_name_failure(self, updater, mock_api_client):
        """プロフィール名更新が失敗した場合にFalseを返すことを確認"""
        mock_api_client.update_profile.return_value = False
        
        result = updater.update_profile_name(10)
        
        assert result is False
    
    def test_update_profile_name_exception(self, updater, mock_api_client):
        """プロフィール名更新で例外が発生した場合にFalseを返すことを確認"""
        mock_api_client.update_profile.side_effect = Exception("API Error")
        
        result = updater.update_profile_name(10)
        
        assert result is False

    
    # レベルアップテキスト生成のテスト
    def test_generate_level_up_text_contains_level(self, updater):
        """レベルアップテキストにレベルが含まれることを確認"""
        xp_breakdown = {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
        text = updater.generate_level_up_text(12, xp_breakdown, 700)
        
        assert "12" in text
    
    def test_generate_level_up_text_contains_xp_breakdown(self, updater):
        """レベルアップテキストにXP内訳が含まれることを確認"""
        xp_breakdown = {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
        text = updater.generate_level_up_text(12, xp_breakdown, 700)
        
        assert "25.0 XP" in text  # oshi_post
        assert "10.0 XP" in text  # group_post
        assert "8.0 XP" in text   # like
        assert "5.0 XP" in text   # repost
    
    def test_generate_level_up_text_contains_next_level_xp(self, updater):
        """レベルアップテキストに次のレベルまでのXPが含まれることを確認"""
        xp_breakdown = {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
        text = updater.generate_level_up_text(12, xp_breakdown, 700)
        
        assert "700 XP" in text
    
    def test_generate_level_up_text_contains_imo_suffix(self, updater):
        """レベルアップテキストに「ｲﾓ🍠」が含まれることを確認"""
        xp_breakdown = {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
        text = updater.generate_level_up_text(12, xp_breakdown, 700)
        
        assert "ｲﾓ🍠" in text
    
    def test_generate_level_up_text_contains_hashtags(self, updater):
        """レベルアップテキストにハッシュタグが含まれることを確認"""
        xp_breakdown = {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
        text = updater.generate_level_up_text(12, xp_breakdown, 700)
        
        assert "#さつまいもの民" in text
        assert "#びっくえんじぇる" in text
    
    def test_generate_level_up_text_with_zero_xp(self, updater):
        """XPが0の場合でもテキストが生成されることを確認"""
        xp_breakdown = {"oshi_post": 0.0, "group_post": 0.0, "like": 0.0, "repost": 0.0}
        text = updater.generate_level_up_text(2, xp_breakdown, 100)
        
        assert "0.0 XP" in text
        assert "2" in text
    
    def test_generate_level_up_text_with_missing_keys(self, updater):
        """XP内訳にキーが欠けている場合でもテキストが生成されることを確認"""
        xp_breakdown = {"oshi_post": 25.0}  # 他のキーが欠けている
        text = updater.generate_level_up_text(12, xp_breakdown, 700)
        
        assert "25.0 XP" in text
        assert "0.0 XP" in text  # 欠けているキーは0.0として扱われる
    
    # レベルアップ投稿のテスト
    def test_post_level_up_announcement_success(self, updater, mock_api_client):
        """レベルアップ投稿が成功することを確認"""
        mock_api_client.post_tweet.return_value = True
        xp_breakdown = {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
        
        result = updater.post_level_up_announcement(12, xp_breakdown, 700)
        
        assert result is True
        mock_api_client.post_tweet.assert_called_once()
    
    def test_post_level_up_announcement_failure(self, updater, mock_api_client):
        """レベルアップ投稿が失敗した場合にFalseを返すことを確認"""
        mock_api_client.post_tweet.return_value = False
        xp_breakdown = {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
        
        result = updater.post_level_up_announcement(12, xp_breakdown, 700)
        
        assert result is False
    
    def test_post_level_up_announcement_exception(self, updater, mock_api_client):
        """レベルアップ投稿で例外が発生した場合にFalseを返すことを確認"""
        mock_api_client.post_tweet.side_effect = Exception("API Error")
        xp_breakdown = {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
        
        result = updater.post_level_up_announcement(12, xp_breakdown, 700)
        
        assert result is False
    
    # 一括更新のテスト
    def test_update_profile_on_level_up_all_success(self, updater, mock_api_client):
        """一括更新がすべて成功することを確認"""
        mock_api_client.update_profile_image.return_value = True
        mock_api_client.update_profile.return_value = True
        mock_api_client.post_tweet.return_value = True
        
        image_data = BytesIO(b"fake image data")
        xp_breakdown = {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
        
        results = updater.update_profile_on_level_up(12, image_data, xp_breakdown, 700)
        
        assert results["image"] is True
        assert results["name"] is True
        assert results["announcement"] is True
    
    def test_update_profile_on_level_up_partial_failure(self, updater, mock_api_client):
        """一括更新で一部が失敗した場合の結果を確認"""
        mock_api_client.update_profile_image.return_value = True
        mock_api_client.update_profile.return_value = False  # 名前更新失敗
        mock_api_client.post_tweet.return_value = True
        
        image_data = BytesIO(b"fake image data")
        xp_breakdown = {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
        
        results = updater.update_profile_on_level_up(12, image_data, xp_breakdown, 700)
        
        assert results["image"] is True
        assert results["name"] is False
        assert results["announcement"] is True
    
    def test_update_profile_on_level_up_no_image(self, updater, mock_api_client):
        """画像データがNoneの場合に画像更新がスキップされることを確認"""
        mock_api_client.update_profile.return_value = True
        mock_api_client.post_tweet.return_value = True
        
        xp_breakdown = {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
        
        results = updater.update_profile_on_level_up(12, None, xp_breakdown, 700)
        
        assert results["image"] is True  # スキップは成功扱い
        assert results["name"] is True
        assert results["announcement"] is True
        mock_api_client.update_profile_image.assert_not_called()
