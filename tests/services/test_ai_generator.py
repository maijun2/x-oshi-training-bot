"""
AIGeneratorクラスのユニットテスト

要件 2.1, 2.2, 2.3, 2.4, 2.6: AI応答生成を検証
"""
import json
import logging
import pytest
from unittest.mock import Mock, MagicMock
from io import BytesIO

from datetime import datetime, timezone

from src.hokuhoku_imomaru_bot.services.ai_generator import (
    AIGenerator,
    Reaction,
    format_jst,
    PROMPT_TEMPLATE,
    REPLY_PROMPT_TEMPLATE,
    MAX_TEXT_LENGTH,
    DEFAULT_RESPONSE_OSHI,
    DEFAULT_RESPONSE_GROUP,
    DEFAULT_REPLY_RESPONSE_TEMPLATE,
    HASHTAGS,
    format_post_text,
)


class TestFormatPostText:
    """format_post_text: 本文を 1 文 1 行にし、ハッシュタグを空行の後の最終行に置く"""

    def test_single_line_with_spaces_is_split_per_sentence(self):
        # 2026-09-15 に Buffer へ実際に送られた 1 行の本文
        text = "ジュリさん朝から大変ｲﾓ🍠💦 でもその可愛い天然さが推しポイントｲﾓ🍠✨ 今日も頑張ってねｲﾓ🍠🍠 #さつまいもの民 #びっくえんじぇる"

        assert format_post_text(text) == (
            "ジュリさん朝から大変ｲﾓ🍠💦\n"
            "でもその可愛い天然さが推しポイントｲﾓ🍠✨\n"
            "今日も頑張ってねｲﾓ🍠🍠\n"
            "\n"
            "#さつまいもの民 #びっくえんじぇる"
        )

    def test_single_line_without_spaces_is_split_per_sentence(self):
        # 文の間にスペースも絵文字もない実例（2026-09-14）
        text = "おはようございまｲﾓ🍠甘木ジュリさん、滝汗気をつけてねｲﾓ🍠ハードな撮影ファイトｲﾓ🍠だいすきｲﾓ🍠#さつまいもの民 #びっくえんじぇる"

        assert format_post_text(text) == (
            "おはようございまｲﾓ🍠\n"
            "甘木ジュリさん、滝汗気をつけてねｲﾓ🍠\n"
            "ハードな撮影ファイトｲﾓ🍠\n"
            "だいすきｲﾓ🍠\n"
            "\n"
            "#さつまいもの民 #びっくえんじぇる"
        )

    def test_trailing_emoji_stays_on_the_same_line(self):
        assert format_post_text("最高ｲﾓ🍠✨ #さつまいもの民 #びっくえんじぇる") == "最高ｲﾓ🍠✨\n\n#さつまいもの民 #びっくえんじぇる"

    def test_opening_bracket_starts_next_line(self):
        assert format_post_text("最高ｲﾓ🍠！「ライブ」楽しみｲﾓ🍠") == "最高ｲﾓ🍠！\n「ライブ」楽しみｲﾓ🍠\n\n#さつまいもの民 #びっくえんじぇる"

    def test_existing_line_breaks_are_kept_and_hashtags_moved_to_last_line(self):
        # モデルが指示どおり改行済み。ハッシュタグだけ同じ行にくっついている
        text = "嬉しいｲﾓ🍠✨ 本当にｲﾓ🍠\n最高ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる"

        assert format_post_text(text) == "嬉しいｲﾓ🍠✨ 本当にｲﾓ🍠\n最高ｲﾓ🍠\n\n#さつまいもの民 #びっくえんじぇる"

    def test_idempotent(self):
        text = "嬉しいｲﾓ🍠✨ 最高ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる"
        once = format_post_text(text)
        assert format_post_text(once) == once

    def test_extra_blank_lines_are_collapsed(self):
        assert format_post_text("嬉しいｲﾓ🍠\n\n\n\n#さつまいもの民 #びっくえんじぇる") == "嬉しいｲﾓ🍠\n\n#さつまいもの民 #びっくえんじぇる"

    def test_text_without_sentence_ending_only_gets_hashtags_separated(self):
        assert format_post_text("語尾なしの文 #さつまいもの民 #びっくえんじぇる") == "語尾なしの文\n\n#さつまいもの民 #びっくえんじぇる"

    def test_missing_hashtags_are_added(self):
        assert format_post_text("嬉しいｲﾓ🍠") == "嬉しいｲﾓ🍠\n\n#さつまいもの民 #びっくえんじぇる"

    def test_empty_text_returns_hashtags_only(self):
        assert format_post_text("") == HASHTAGS

    def test_fullwidth_imo_is_normalized_to_halfwidth(self):
        # 2026-09-18 10:07 回で頭脳が全角「イモ🍠」を返した（プロンプトは半角指定）。半角に揃え、文の分割も効かせる
        text = "ジュリさんおはようイモ🍠 徹夜で作業かな？イモ🍠✨ 無理しないでねイモ🍠 #さつまいもの民 #びっくえんじぇる"

        assert format_post_text(text) == (
            "ジュリさんおはようｲﾓ🍠\n"
            "徹夜で作業かな？ｲﾓ🍠✨\n"
            "無理しないでねｲﾓ🍠\n"
            "\n"
            "#さつまいもの民 #びっくえんじぇる"
        )

    def test_mixed_width_imo_is_idempotent(self):
        text = "嬉しいイモ🍠\n最高ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる"
        once = format_post_text(text)

        assert once == "嬉しいｲﾓ🍠\n最高ｲﾓ🍠\n\n#さつまいもの民 #びっくえんじぇる"
        assert format_post_text(once) == once


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
        
        assert result == format_post_text(DEFAULT_RESPONSE_OSHI)
        assert result == "じゅりちゃんの投稿を見つけたｲﾓ🍠✨\n\n#さつまいもの民 #びっくえんじぇる"
    
    def test_generate_response_fallback_on_error_group(self, generator, mock_bedrock_client):
        """エラー時にフォールバック応答（グループ）が返されることを確認"""
        mock_bedrock_client.invoke_model.side_effect = Exception("API Error")
        
        result = generator.generate_response("テスト投稿", "group")
        
        assert result == format_post_text(DEFAULT_RESPONSE_GROUP)
    
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


class TestBrainIntegration:
    """頭脳（BrainClient）経由の生成と、失敗時の Bedrock 直呼びフォールバック"""

    def _bedrock(self, text: str):
        client = Mock()
        client.invoke_model.return_value = {
            "body": MagicMock(read=lambda: json.dumps({"content": [{"text": text}]}).encode("utf-8"))
        }
        return client

    def _brain(self, text=None, error=None, reaction=None):
        from src.hokuhoku_imomaru_bot.utils.brain_client import BrainClient, BrainError

        brain = MagicMock(spec=BrainClient)
        if error is not None:
            brain.invoke.side_effect = BrainError(error)
            brain.invoke_json.side_effect = BrainError(error)
        else:
            brain.invoke.return_value = text
            brain.invoke_json.return_value = reaction
        return brain

    POSTED_AT = datetime(2026, 9, 15, 16, 42, tzinfo=timezone.utc)   # 09-16 01:42 JST
    NOW = datetime(2026, 9, 16, 4, 18, tzinfo=timezone.utc)          # 09-16 13:18 JST
    PUBLISH_AT = datetime(2026, 9, 16, 5, 15, tzinfo=timezone.utc)   # 09-16 14:15 JST

    def _react(self, generator, **kwargs):
        params = dict(post_content="投稿", posted_at=self.POSTED_AT, now=self.NOW, publish_at=self.PUBLISH_AT)
        params.update(kwargs)
        return generator.generate_reaction(**params)

    def test_format_jst(self):
        assert format_jst(self.NOW) == "2026-09-16(水) 13:18 JST"

    def test_generate_reaction_uses_brain_and_skips_bedrock(self):
        bedrock = self._bedrock("Haiku の応答")
        brain = self._brain(reaction={
            "action": "post",
            "text": "頭脳の応答ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる",
            "emotion_key": "JOY",
            "reason": "嬉しい報告",
        })
        generator = AIGenerator(bedrock_client=bedrock, brain_client=brain)

        reaction = self._react(generator, post_type="oshi")

        # 頭脳の出力も整形（ハッシュタグは空行の後の最終行）、感情キーは検証・小文字化される
        assert reaction == Reaction(
            action="post",
            text="頭脳の応答ｲﾓ🍠\n\n#さつまいもの民 #びっくえんじぇる",
            emotion_key="joy",
            reason="嬉しい報告",
            source="brain",
        )
        brain.invoke_json.assert_called_once_with("react", {
            "post_content": "投稿",
            "post_type": "oshi",
            "posted_at": "2026-09-16(水) 01:42 JST",
            "now": "2026-09-16(水) 13:18 JST",
            "publish_at": "2026-09-16(水) 14:15 JST",
        })
        bedrock.invoke_model.assert_not_called()

    def test_generate_reaction_without_publish_time(self):
        brain = self._brain(reaction={"action": "post", "text": "x", "emotion_key": "none"})
        generator = AIGenerator(bedrock_client=Mock(), brain_client=brain)
        reaction = self._react(generator, publish_at=None)
        assert brain.invoke_json.call_args.args[1]["publish_at"] == "不明（数時間後）"
        assert reaction.emotion_key is None

    def test_generate_reaction_skip(self):
        bedrock = Mock()
        brain = self._brain(reaction={"action": "skip", "text": "", "emotion_key": "none", "reason": "URL のみ"})
        generator = AIGenerator(bedrock_client=bedrock, brain_client=brain)

        reaction = self._react(generator)

        assert reaction.action == "skip"
        assert reaction.text == ""
        assert reaction.emotion_key is None
        assert reaction.reason == "URL のみ"
        bedrock.invoke_model.assert_not_called()

    def test_generate_reaction_truncates_and_keeps_line_breaks_within_limit(self):
        # 改行込みで 140 字に収める（Property 5）。文の途中で切れても改行で終わらない
        text = "\n".join(["あ" * 30 + "ｲﾓ🍠"] * 6) + " #さつまいもの民 #びっくえんじぇる"
        brain = self._brain(reaction={"action": "post", "text": text, "emotion_key": "joy"})
        generator = AIGenerator(bedrock_client=Mock(), brain_client=brain)

        result = self._react(generator).text

        assert len(result) <= 140
        assert result.endswith("\n\n#さつまいもの民 #びっくえんじぇる")
        assert "...\n\n#" in result
        assert "\n...\n" not in result

    def test_generate_reaction_unknown_emotion_key_is_none(self):
        brain = self._brain(reaction={"action": "post", "text": "x", "emotion_key": "banana"})
        generator = AIGenerator(bedrock_client=Mock(), brain_client=brain)
        assert self._react(generator).emotion_key is None

    def test_generate_reaction_falls_back_to_bedrock_on_brain_error(self, caplog):
        bedrock = self._bedrock("Haiku の応答ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる")
        brain = self._brain(error="invoke failed")
        generator = AIGenerator(bedrock_client=bedrock, brain_client=brain)

        with caplog.at_level(logging.ERROR):
            reaction = self._react(generator, post_type="oshi", classify=False)

        assert reaction.action == "post"
        assert reaction.source == "bedrock"
        assert reaction.text == "Haiku の応答ｲﾓ🍠\n\n#さつまいもの民 #びっくえんじぇる"
        assert reaction.emotion_key is None
        bedrock.invoke_model.assert_called_once()
        # アラームを鳴らすため ERROR で記録される
        assert any(r.levelno == logging.ERROR and "Brain failed" in r.getMessage() for r in caplog.records)

    def test_generate_reaction_fallback_classifies_when_requested(self):
        bedrock = Mock()
        bodies = iter(["Haiku の応答ｲﾓ🍠", "cheer"])
        bedrock.invoke_model.side_effect = lambda **kw: {
            "body": MagicMock(read=lambda: json.dumps({"content": [{"text": next(bodies)}]}).encode("utf-8"))
        }
        generator = AIGenerator(bedrock_client=bedrock, brain_client=self._brain(error="down"))

        reaction = self._react(generator, classify=True)

        assert reaction.emotion_key == "cheer"
        assert bedrock.invoke_model.call_count == 2

    def test_generate_reaction_post_without_text_falls_back(self):
        bedrock = self._bedrock("Haiku の応答")
        brain = self._brain(reaction={"action": "post", "text": "   ", "emotion_key": "joy"})
        generator = AIGenerator(bedrock_client=bedrock, brain_client=brain)
        reaction = self._react(generator, classify=False)
        assert reaction.source == "bedrock"
        bedrock.invoke_model.assert_called_once()

    def test_generate_reaction_without_brain_uses_bedrock(self):
        bedrock = self._bedrock("Haiku の応答")
        generator = AIGenerator(bedrock_client=bedrock)
        reaction = self._react(generator, classify=False)
        assert reaction.source == "bedrock"
        bedrock.invoke_model.assert_called_once()

    def test_generate_response_never_calls_brain(self):
        """generate_response / classify_emotion は Haiku 直呼び専用（Runtime にタスクが無い）"""
        bedrock = self._bedrock("cheer")
        brain = self._brain(text="頭脳")
        generator = AIGenerator(bedrock_client=bedrock, brain_client=brain)
        generator.generate_response("投稿")
        generator.classify_emotion("応援")
        brain.invoke.assert_not_called()
        brain.invoke_json.assert_not_called()
        assert bedrock.invoke_model.call_count == 2

    def test_reply_response_uses_brain(self):
        bedrock = Mock()
        brain = self._brain("fan_taroさんありがとうｲﾓ🍠 #さつまいもの民 #びっくえんじぇる")
        generator = AIGenerator(bedrock_client=bedrock, brain_client=brain)

        result = generator.generate_reply_response(
            reply_text="かわいい", reply_username="fan_taro", bot_tweet_text="元投稿"
        )

        assert result.startswith("fan_taroさん")
        brain.invoke.assert_called_once_with(
            "reply_response",
            {"reply_text": "かわいい", "reply_username": "fan_taro", "bot_tweet_text": "元投稿"},
        )
        bedrock.invoke_model.assert_not_called()

    def test_reply_response_falls_back_on_brain_error(self):
        bedrock = self._bedrock("Haiku のリプライ")
        generator = AIGenerator(bedrock_client=bedrock, brain_client=self._brain(error="down"))
        assert generator.generate_reply_response("a", "u", "b") == "Haiku のリプライ"
        bedrock.invoke_model.assert_called_once()
