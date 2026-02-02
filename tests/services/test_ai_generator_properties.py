"""
AIGeneratorクラスのプロパティベーステスト

Property 4: プロンプトへの投稿内容の包含
Property 5: テキストの140文字制限
"""
import json
import pytest
from unittest.mock import Mock, MagicMock
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.hokuhoku_imomaru_bot.services.ai_generator import (
    AIGenerator,
    MAX_TEXT_LENGTH,
)


def create_generator():
    """AIGeneratorインスタンスを作成"""
    return AIGenerator(bedrock_client=Mock())


class TestPromptContentProperty:
    """
    Property 4: プロンプトへの投稿内容の包含
    
    任意の投稿内容に対して、生成されたプロンプトはその投稿内容を含むべきである
    
    **Validates: Requirements 2.2**
    """
    
    @settings(max_examples=100)
    @given(
        post_content=st.text(min_size=1, max_size=280),
    )
    def test_prompt_contains_post_content(self, post_content):
        """
        Feature: hokuhoku-imomaru-bot, Property 4: プロンプトへの投稿内容の包含
        
        任意の投稿内容に対して、生成されたプロンプトはその投稿内容を含むべきである
        """
        generator = create_generator()
        
        prompt = generator.build_prompt(post_content)
        
        assert post_content in prompt
    
    @settings(max_examples=100)
    @given(
        post_content=st.text(min_size=1, max_size=280),
    )
    def test_prompt_contains_character_definition(self, post_content):
        """
        Feature: hokuhoku-imomaru-bot, Property 4: プロンプトへの投稿内容の包含
        
        任意の投稿内容に対して、プロンプトにはキャラクター定義が含まれるべきである
        """
        generator = create_generator()
        
        prompt = generator.build_prompt(post_content)
        
        # キャラクター定義が含まれていることを確認
        assert "ほくほくいも丸くん🍠" in prompt
        assert "天木じゅりさん" in prompt
        assert "◯◯ｲﾓ🍠" in prompt


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


class TestGenerateResponseProperty:
    """
    生成されたレスポンスのプロパティテスト
    """
    
    @settings(max_examples=50)
    @given(
        post_content=st.text(min_size=1, max_size=280),
        post_type=st.sampled_from(["oshi", "group"]),
    )
    def test_generated_response_within_limit(self, post_content, post_type):
        """
        Feature: hokuhoku-imomaru-bot, Property 5: テキストの140文字制限
        
        生成されたレスポンスは常に140文字以内であるべきである
        """
        mock_bedrock_client = Mock()
        
        # 長いレスポンスを返すモック
        long_response = "あ" * 200 + "ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる"
        mock_response = {"content": [{"text": long_response}]}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(mock_response).encode()
        mock_bedrock_client.invoke_model.return_value = {"body": mock_body}
        
        generator = AIGenerator(bedrock_client=mock_bedrock_client)
        
        result = generator.generate_response(post_content, post_type)
        
        assert len(result) <= MAX_TEXT_LENGTH
    
    @settings(max_examples=50)
    @given(
        post_content=st.text(min_size=1, max_size=280),
        post_type=st.sampled_from(["oshi", "group"]),
    )
    def test_fallback_response_within_limit(self, post_content, post_type):
        """
        Feature: hokuhoku-imomaru-bot, Property 5: テキストの140文字制限
        
        フォールバックレスポンスは常に140文字以内であるべきである
        """
        mock_bedrock_client = Mock()
        mock_bedrock_client.invoke_model.side_effect = Exception("API Error")
        
        generator = AIGenerator(bedrock_client=mock_bedrock_client)
        
        result = generator.generate_response(post_content, post_type)
        
        assert len(result) <= MAX_TEXT_LENGTH
