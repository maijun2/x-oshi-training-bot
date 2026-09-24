"""
AIGeneratorクラスのプロパティベーステスト

Property 5: テキストの140文字制限
（Property 4「プロンプトへの投稿内容の包含」は Haiku 直呼びのプロンプト用。2b-3 で直呼びを撤去し、
プロンプトは頭脳側 agent/brain.py が組み立てる）
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from src.hokuhoku_imomaru_bot.services.ai_generator import (
    AIGenerator,
    MAX_TEXT_LENGTH,
)
from src.hokuhoku_imomaru_bot.utils.brain_client import BrainClient


def create_generator(brain_client=None):
    """AIGeneratorインスタンスを作成"""
    return AIGenerator(brain_client=brain_client)


class TestTextTruncationProperty:
    """
    Property 5: テキストの140文字制限
    
    任意の生成されたテキストに対して、切り詰め処理後のテキストは140文字以内であるべきである
    
    **Validates: Requirements 2.4**
    """
    
    @settings(max_examples=100)
    @given(
        text=st.text(min_size=0, max_size=500),
    )
    def test_truncated_text_within_limit(self, text):
        """
        Feature: hokuhoku-imomaru-bot, Property 5: テキストの140文字制限
        
        任意のテキストに対して、切り詰め処理後のテキストは140文字以内であるべきである
        """
        generator = create_generator()
        
        truncated = generator.truncate_text(text)
        
        assert len(truncated) <= MAX_TEXT_LENGTH
    
    @settings(max_examples=100)
    @given(
        text=st.text(min_size=0, max_size=140),
    )
    def test_short_text_unchanged(self, text):
        """
        Feature: hokuhoku-imomaru-bot, Property 5: テキストの140文字制限
        
        140文字以内のテキストは変更されないべきである
        """
        generator = create_generator()
        
        truncated = generator.truncate_text(text)
        
        # 短いテキストはそのまま返される
        assert truncated == text
    
    @settings(max_examples=100)
    @given(
        base_text=st.text(min_size=150, max_size=500),
    )
    def test_long_text_preserves_hashtags(self, base_text):
        """
        Feature: hokuhoku-imomaru-bot, Property 5: テキストの140文字制限
        
        長いテキストを切り詰めてもハッシュタグは保持されるべきである
        """
        generator = create_generator()
        hashtags = "#さつまいもの民 #びっくえんじぇる"
        text_with_hashtags = base_text + " " + hashtags
        
        truncated = generator.truncate_text(text_with_hashtags)
        
        assert len(truncated) <= MAX_TEXT_LENGTH
        assert hashtags in truncated


class TestGenerateReactionProperty:
    """
    頭脳の提案を整形したあとの本文のプロパティテスト
    """

    NOW = datetime(2026, 9, 16, 4, 18, tzinfo=timezone.utc)

    @settings(max_examples=50)
    @given(
        post_content=st.text(min_size=1, max_size=280),
        post_type=st.sampled_from(["oshi", "group"]),
    )
    def test_reaction_text_within_limit(self, post_content, post_type):
        """
        Feature: hokuhoku-imomaru-bot, Property 5: テキストの140文字制限

        頭脳が長い本文を返しても、反応の本文は常に140文字以内であるべきである
        """
        brain = MagicMock(spec=BrainClient)
        brain.invoke_json.return_value = {
            "action": "post",
            "text": "あ" * 200 + "ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる",
            "emotion_key": "joy",
        }
        generator = create_generator(brain)

        reaction = generator.generate_reaction(
            post_content=post_content, posted_at=self.NOW, now=self.NOW, publish_at=None, post_type=post_type
        )

        assert len(reaction.text) <= MAX_TEXT_LENGTH
