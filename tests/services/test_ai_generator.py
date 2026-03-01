"""
AIGeneratorクラスのユニットテスト

要件 2.1, 2.2, 2.3, 2.4, 2.6: AI応答生成を検証
"""
import json
import pytest
from unittest.mock import Mock, MagicMock
from io import BytesIO

from src.hokuhoku_imomaru_bot.services.ai_generator import (
    AIGenerator,
    PROMPT_TEMPLATE,
    REPLY_PROMPT_TEMPLATE,
    MAX_TEXT_LENGTH,
    DEFAULT_RESPONSE_OSHI,
    DEFAULT_RESPONSE_GROUP,
    DEFAULT_REPLY_RESPONSE_TEMPLATE,
)


class TestAIGenerator:
    """AIGeneratorクラスのテスト"""
    
    @pytest.fixture
    def mock_bedrock_client(self):
        """モックBedrockクライアント"""
        return Mock()
    
    @pytest.fixture
    def generator(self, mock_bedrock_client):
        """AIGeneratorインスタンス"""
        return AIGenerator(bedrock_client=mock_bedrock_client)
    
    def test_build_prompt_includes_post_content(self, generator):
        """プロンプトに投稿内容が含まれることを確認"""
        post_content = "今日のライブ最高でした！"
        
        prompt = generator.build_prompt(post_content)
        
        assert post_content in prompt
    
    def test_build_prompt_includes_character_definition(self, generator):
        """プロンプトにキャラクター定義が含まれることを確認"""
        prompt = generator.build_prompt("テスト投稿")
        
        assert "ほくほくいも丸くん🍠" in prompt
        assert "甘木ジュリさん" in prompt
        assert "@juri_bigangel" in prompt
        assert "◯◯ｲﾓ🍠" in prompt
    
    def test_build_prompt_includes_constraints(self, generator):
        """プロンプトに制約が含まれることを確認"""
        prompt = generator.build_prompt("テスト投稿")
        
        assert "140文字以内" in prompt
        assert "#さつまいもの民 #びっくえんじぇる" in prompt
        assert "絵文字" in prompt
    
    def test_truncate_text_short_text(self, generator):
        """短いテキストはそのまま返されることを確認"""
        short_text = "短いテキストｲﾓ🍠 #さつまいもの民 #びっくえんじぇる"
        
        result = generator.truncate_text(short_text)
        
        assert result == short_text
    
    def test_truncate_text_long_text(self, generator):
        """長いテキストが140文字以内に切り詰められることを確認"""
        long_text = "あ" * 200 + " #さつまいもの民 #びっくえんじぇる"
        
        result = generator.truncate_text(long_text)
        
        assert len(result) <= MAX_TEXT_LENGTH
        assert "#さつまいもの民 #びっくえんじぇる" in result
    
    def test_truncate_text_exactly_140_chars(self, generator):
        """ちょうど140文字のテキストはそのまま返されることを確認"""
        # ハッシュタグ込みで140文字のテキストを作成
        hashtags = "#さつまいもの民 #びっくえんじぇる"
        content_len = MAX_TEXT_LENGTH - len(hashtags) - 1
        text = "あ" * content_len + " " + hashtags
        
        result = generator.truncate_text(text)
        
        assert len(result) <= MAX_TEXT_LENGTH
    
    def test_generate_response_success(self, generator, mock_bedrock_client):
        """正常にレスポンスが生成されることを確認"""
        # モックレスポンスを設定
        mock_response = {
            "content": [{"text": "じゅりちゃん最高ｲﾓ🍠✨ #さつまいもの民 #びっくえんじぇる"}]
        }
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(mock_response).encode()
        mock_bedrock_client.invoke_model.return_value = {"body": mock_body}
        
        result = generator.generate_response("今日のライブ最高！", "oshi")
        
        assert "ｲﾓ🍠" in result or "#さつまいもの民" in result
        mock_bedrock_client.invoke_model.assert_called_once()
    
    def test_generate_response_truncates_long_response(self, generator, mock_bedrock_client):
        """長いレスポンスが切り詰められることを確認"""
        # 長いモックレスポンスを設定
        long_response = "あ" * 200 + "ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる"
        mock_response = {"content": [{"text": long_response}]}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(mock_response).encode()
        mock_bedrock_client.invoke_model.return_value = {"body": mock_body}
        
        result = generator.generate_response("テスト投稿", "oshi")
        
        assert len(result) <= MAX_TEXT_LENGTH
    
    def test_generate_response_fallback_on_error_oshi(self, generator, mock_bedrock_client):
        """エラー時にフォールバック応答（推し）が返されることを確認"""
        mock_bedrock_client.invoke_model.side_effect = Exception("API Error")
        
        result = generator.generate_response("テスト投稿", "oshi")
        
        assert result == DEFAULT_RESPONSE_OSHI
    
    def test_generate_response_fallback_on_error_group(self, generator, mock_bedrock_client):
        """エラー時にフォールバック応答（グループ）が返されることを確認"""
        mock_bedrock_client.invoke_model.side_effect = Exception("API Error")
        
        result = generator.generate_response("テスト投稿", "group")
        
        assert result == DEFAULT_RESPONSE_GROUP
    
    def test_generate_response_uses_correct_model(self, generator, mock_bedrock_client):
        """正しいモデルIDが使用されることを確認"""
        mock_response = {"content": [{"text": "テストｲﾓ🍠"}]}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(mock_response).encode()
        mock_bedrock_client.invoke_model.return_value = {"body": mock_body}
        
        generator.generate_response("テスト", "oshi")
        
        call_args = mock_bedrock_client.invoke_model.call_args
        assert call_args.kwargs["modelId"] == AIGenerator.DEFAULT_MODEL_ID
    
    def test_generate_response_request_body_format(self, generator, mock_bedrock_client):
        """リクエストボディが正しい形式であることを確認"""
        mock_response = {"content": [{"text": "テストｲﾓ🍠"}]}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(mock_response).encode()
        mock_bedrock_client.invoke_model.return_value = {"body": mock_body}
        
        generator.generate_response("テスト投稿", "oshi")
        
        call_args = mock_bedrock_client.invoke_model.call_args
        request_body = json.loads(call_args.kwargs["body"])
        
        assert "anthropic_version" in request_body
        assert "max_tokens" in request_body
        assert "temperature" in request_body
        assert "messages" in request_body
        assert request_body["messages"][0]["role"] == "user"
    
    def test_custom_model_parameters(self, mock_bedrock_client):
        """カスタムモデルパラメータが使用されることを確認"""
        custom_generator = AIGenerator(
            bedrock_client=mock_bedrock_client,
            model_id="custom-model",
            max_tokens=100,
            temperature=0.5,
        )
        
        assert custom_generator.model_id == "custom-model"
        assert custom_generator.max_tokens == 100
        assert custom_generator.temperature == 0.5
    
    def test_fallback_response_within_limit(self):
        """フォールバック応答が140文字以内であることを確認"""
        assert len(DEFAULT_RESPONSE_OSHI) <= MAX_TEXT_LENGTH
        assert len(DEFAULT_RESPONSE_GROUP) <= MAX_TEXT_LENGTH
    
    def test_fallback_response_contains_hashtags(self):
        """フォールバック応答にハッシュタグが含まれることを確認"""
        assert "#さつまいもの民" in DEFAULT_RESPONSE_OSHI
        assert "#びっくえんじぇる" in DEFAULT_RESPONSE_OSHI
        assert "#さつまいもの民" in DEFAULT_RESPONSE_GROUP
        assert "#びっくえんじぇる" in DEFAULT_RESPONSE_GROUP


class TestAIGeneratorReplyResponse:
    """generate_reply_responseメソッドのテスト"""

    @pytest.fixture
    def mock_bedrock_client(self):
        """モックBedrockクライアント"""
        return Mock()

    @pytest.fixture
    def generator(self, mock_bedrock_client):
        """AIGeneratorインスタンス"""
        return AIGenerator(bedrock_client=mock_bedrock_client)

    def _mock_bedrock_response(self, mock_bedrock_client, text):
        """Bedrockモックレスポンスを設定"""
        mock_response = {"content": [{"text": text}]}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(mock_response).encode()
        mock_bedrock_client.invoke_model.return_value = {"body": mock_body}

    def test_reply_response_success(self, generator, mock_bedrock_client):
        """リプライ応答が正常に生成されること"""
        self._mock_bedrock_response(
            mock_bedrock_client,
            "ありがとうｲﾓ🍠✨ #さつまいもの民 #びっくえんじぇる",
        )

        result = generator.generate_reply_response(
            reply_text="いも丸くんかわいい！",
            reply_username="test_user",
            bot_tweet_text="今日も推し活ｲﾓ🍠",
        )

        assert "ｲﾓ🍠" in result or "#さつまいもの民" in result
        mock_bedrock_client.invoke_model.assert_called_once()

    def test_reply_prompt_uses_reply_template(self, generator, mock_bedrock_client):
        """リプライ専用プロンプトテンプレートが使用されること"""
        self._mock_bedrock_response(mock_bedrock_client, "テストｲﾓ🍠")

        generator.generate_reply_response(
            reply_text="テストリプライ",
            reply_username="user123",
            bot_tweet_text="ボット投稿",
        )

        call_args = mock_bedrock_client.invoke_model.call_args
        request_body = json.loads(call_args.kwargs["body"])
        prompt = request_body["messages"][0]["content"]

        # REPLY_PROMPT_TEMPLATEの特徴的な文言が含まれること
        assert "リプライを受け取りました" in prompt
        assert "親しみを込めて応答すること" in prompt

    def test_reply_prompt_contains_context(self, generator, mock_bedrock_client):
        """プロンプトにリプライ元ツイート、ボット投稿、ユーザー名が含まれること"""
        self._mock_bedrock_response(mock_bedrock_client, "テストｲﾓ🍠")

        generator.generate_reply_response(
            reply_text="最高のツイートですね！",
            reply_username="imomaru_fan",
            bot_tweet_text="甘木ジュリちゃん最高ｲﾓ🍠",
        )

        call_args = mock_bedrock_client.invoke_model.call_args
        request_body = json.loads(call_args.kwargs["body"])
        prompt = request_body["messages"][0]["content"]

        assert "最高のツイートですね！" in prompt
        assert "imomaru_fan" in prompt
        assert "甘木ジュリちゃん最高ｲﾓ🍠" in prompt

    def test_reply_response_truncated_when_long(self, generator, mock_bedrock_client):
        """長いリプライ応答が140文字以内に切り詰められること"""
        long_response = "あ" * 200 + "ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる"
        self._mock_bedrock_response(mock_bedrock_client, long_response)

        result = generator.generate_reply_response(
            reply_text="テスト",
            reply_username="user",
            bot_tweet_text="テスト",
        )

        assert len(result) <= MAX_TEXT_LENGTH

    def test_reply_response_fallback_on_error(self, generator, mock_bedrock_client):
        """Bedrock API失敗時にフォールバック応答が返されること"""
        mock_bedrock_client.invoke_model.side_effect = Exception("Bedrock Error")

        result = generator.generate_reply_response(
            reply_text="テスト",
            reply_username="test_user",
            bot_tweet_text="テスト",
        )

        expected = DEFAULT_REPLY_RESPONSE_TEMPLATE.format(username="test_user")
        assert result == expected

    def test_reply_fallback_contains_username(self, generator, mock_bedrock_client):
        """フォールバック応答にユーザー名が含まれること"""
        mock_bedrock_client.invoke_model.side_effect = Exception("Error")

        result = generator.generate_reply_response(
            reply_text="テスト",
            reply_username="my_username",
            bot_tweet_text="テスト",
        )

        assert "@my_username" in result

    def test_reply_fallback_contains_hashtags(self, generator, mock_bedrock_client):
        """フォールバック応答にハッシュタグが含まれること"""
        mock_bedrock_client.invoke_model.side_effect = Exception("Error")

        result = generator.generate_reply_response(
            reply_text="テスト",
            reply_username="user",
            bot_tweet_text="テスト",
        )

        assert "#さつまいもの民" in result
        assert "#びっくえんじぇる" in result

    def test_reply_fallback_within_limit(self):
        """フォールバック応答テンプレートが140文字以内であること"""
        # 長めのユーザー名でも140文字以内
        result = DEFAULT_REPLY_RESPONSE_TEMPLATE.format(username="a" * 15)
        assert len(result) <= MAX_TEXT_LENGTH

    def test_reply_error_logs_warning(self, generator, mock_bedrock_client, caplog):
        """Bedrock API失敗時にWARNINGログが出力されること"""
        import logging
        mock_bedrock_client.invoke_model.side_effect = Exception("Bedrock timeout")

        with caplog.at_level(logging.WARNING):
            generator.generate_reply_response(
                reply_text="テスト",
                reply_username="user",
                bot_tweet_text="テスト",
            )

        assert "Failed to generate reply response" in caplog.text
