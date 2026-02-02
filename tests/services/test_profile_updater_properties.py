"""
ProfileUpdaterクラスのプロパティベーステスト

Property 9: プロフィール名の生成
Property 10: レベルアップ投稿の内容
"""
import pytest
from unittest.mock import Mock
from hypothesis import given, settings
from hypothesis import strategies as st

from src.hokuhoku_imomaru_bot.services.profile_updater import ProfileUpdater


def create_updater():
    """テスト用のProfileUpdaterインスタンスを作成"""
    mock_api_client = Mock()
    return ProfileUpdater(api_client=mock_api_client)


class TestProfileUpdaterProperties:
    """ProfileUpdaterのプロパティベーステスト"""
    
    # Property 9: プロフィール名の生成
    @settings(max_examples=100)
    @given(level=st.integers(min_value=1, max_value=99))
    def test_profile_name_format_property(self, level):
        """
        **Validates: Requirements 6.2, 6.3**
        
        Property 9: プロフィール名の生成
        
        任意のレベルに対して、生成されるプロフィール名は
        「ほくほくいも丸くん🍠Lv.{level}」の形式であるべきである
        """
        updater = create_updater()
        name = updater.generate_profile_name(level)
        
        # 正しいフォーマットであることを確認
        expected = f"ほくほくいも丸くん🍠Lv.{level}"
        assert name == expected
    
    @settings(max_examples=100)
    @given(level=st.integers(min_value=1, max_value=99))
    def test_profile_name_contains_level_property(self, level):
        """
        **Validates: Requirements 6.2, 6.3**
        
        任意のレベルに対して、プロフィール名にはそのレベル番号が含まれるべきである
        """
        updater = create_updater()
        name = updater.generate_profile_name(level)
        
        assert str(level) in name
    
    @settings(max_examples=100)
    @given(level=st.integers(min_value=1, max_value=99))
    def test_profile_name_contains_emoji_property(self, level):
        """
        **Validates: Requirements 6.2, 6.3**
        
        任意のレベルに対して、プロフィール名には🍠絵文字が含まれるべきである
        """
        updater = create_updater()
        name = updater.generate_profile_name(level)
        
        assert "🍠" in name
    
    @settings(max_examples=100)
    @given(level=st.integers(min_value=1, max_value=99))
    def test_profile_name_starts_with_character_name_property(self, level):
        """
        **Validates: Requirements 6.2, 6.3**
        
        任意のレベルに対して、プロフィール名は「ほくほくいも丸くん」で始まるべきである
        """
        updater = create_updater()
        name = updater.generate_profile_name(level)
        
        assert name.startswith("ほくほくいも丸くん")
    
    # Property 10: レベルアップ投稿の内容
    @settings(max_examples=100)
    @given(
        level=st.integers(min_value=2, max_value=99),
        oshi_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        group_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        like_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        repost_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        next_level_xp=st.integers(min_value=0, max_value=1000000),
    )
    def test_level_up_text_contains_level_property(
        self, level, oshi_xp, group_xp, like_xp, repost_xp, next_level_xp
    ):
        """
        **Validates: Requirements 6.4, 6.5**
        
        Property 10: レベルアップ投稿の内容
        
        任意のレベルアップ投稿に対して、新しいレベルが含まれるべきである
        """
        updater = create_updater()
        xp_breakdown = {
            "oshi_post": oshi_xp,
            "group_post": group_xp,
            "like": like_xp,
            "repost": repost_xp,
        }
        text = updater.generate_level_up_text(level, xp_breakdown, next_level_xp)
        
        assert str(level) in text
    
    @settings(max_examples=100)
    @given(
        level=st.integers(min_value=2, max_value=99),
        oshi_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        group_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        like_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        repost_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        next_level_xp=st.integers(min_value=0, max_value=1000000),
    )
    def test_level_up_text_contains_imo_suffix_property(
        self, level, oshi_xp, group_xp, like_xp, repost_xp, next_level_xp
    ):
        """
        **Validates: Requirements 6.4, 6.5**
        
        Property 10: レベルアップ投稿の内容
        
        任意のレベルアップ投稿に対して、語尾「◯◯ｲﾓ🍠」が含まれるべきである
        """
        updater = create_updater()
        xp_breakdown = {
            "oshi_post": oshi_xp,
            "group_post": group_xp,
            "like": like_xp,
            "repost": repost_xp,
        }
        text = updater.generate_level_up_text(level, xp_breakdown, next_level_xp)
        
        assert "ｲﾓ🍠" in text
    
    @settings(max_examples=100)
    @given(
        level=st.integers(min_value=2, max_value=99),
        oshi_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        group_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        like_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        repost_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        next_level_xp=st.integers(min_value=0, max_value=1000000),
    )
    def test_level_up_text_contains_hashtags_property(
        self, level, oshi_xp, group_xp, like_xp, repost_xp, next_level_xp
    ):
        """
        **Validates: Requirements 6.4, 6.5**
        
        Property 10: レベルアップ投稿の内容
        
        任意のレベルアップ投稿に対して、ハッシュタグ「#さつまいもの民 #びっくえんじぇる」が含まれるべきである
        """
        updater = create_updater()
        xp_breakdown = {
            "oshi_post": oshi_xp,
            "group_post": group_xp,
            "like": like_xp,
            "repost": repost_xp,
        }
        text = updater.generate_level_up_text(level, xp_breakdown, next_level_xp)
        
        assert "#さつまいもの民" in text
        assert "#びっくえんじぇる" in text
    
    @settings(max_examples=100)
    @given(
        level=st.integers(min_value=2, max_value=99),
        oshi_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        group_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        like_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        repost_xp=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        next_level_xp=st.integers(min_value=0, max_value=1000000),
    )
    def test_level_up_text_contains_next_level_xp_property(
        self, level, oshi_xp, group_xp, like_xp, repost_xp, next_level_xp
    ):
        """
        **Validates: Requirements 6.4, 6.5**
        
        Property 10: レベルアップ投稿の内容
        
        任意のレベルアップ投稿に対して、次のレベルまでの必要XPが含まれるべきである
        """
        updater = create_updater()
        xp_breakdown = {
            "oshi_post": oshi_xp,
            "group_post": group_xp,
            "like": like_xp,
            "repost": repost_xp,
        }
        text = updater.generate_level_up_text(level, xp_breakdown, next_level_xp)
        
        assert str(next_level_xp) in text
    
    @settings(max_examples=100)
    @given(
        level=st.integers(min_value=2, max_value=99),
        oshi_xp=st.floats(min_value=0.1, max_value=10000.0, allow_nan=False, allow_infinity=False),
        group_xp=st.floats(min_value=0.1, max_value=10000.0, allow_nan=False, allow_infinity=False),
        like_xp=st.floats(min_value=0.1, max_value=10000.0, allow_nan=False, allow_infinity=False),
        repost_xp=st.floats(min_value=0.1, max_value=10000.0, allow_nan=False, allow_infinity=False),
        next_level_xp=st.integers(min_value=0, max_value=1000000),
    )
    def test_level_up_text_contains_xp_breakdown_property(
        self, level, oshi_xp, group_xp, like_xp, repost_xp, next_level_xp
    ):
        """
        **Validates: Requirements 6.4, 6.5**
        
        Property 10: レベルアップ投稿の内容
        
        任意のレベルアップ投稿に対して、XP内訳（推しの投稿、グループの投稿、いいね、リポスト）が含まれるべきである
        """
        updater = create_updater()
        xp_breakdown = {
            "oshi_post": oshi_xp,
            "group_post": group_xp,
            "like": like_xp,
            "repost": repost_xp,
        }
        text = updater.generate_level_up_text(level, xp_breakdown, next_level_xp)
        
        # XP内訳が含まれていることを確認
        assert "じゅりちゃんの投稿" in text
        assert "グループの投稿" in text
        assert "みんなからのいいね" in text
        assert "みんなのリポスト" in text
        assert "XP" in text
