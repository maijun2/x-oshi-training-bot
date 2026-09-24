"""
AIGeneratorクラスのユニットテスト

要件 2.1, 2.2, 2.3, 2.4, 2.6: AI応答生成を検証
"""
import logging
import pytest
from unittest.mock import MagicMock

from datetime import datetime, timezone

from src.hokuhoku_imomaru_bot.services.ai_generator import (
    AIGenerator,
    Reaction,
    format_jst,
    BRAIN_FAILED_REASON,
    MAX_TEXT_LENGTH,
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

    @pytest.mark.parametrize("broken", ["ｲﾐ🍠", "イミ🍠", "ｲモ🍠", "イﾓ🍠"])
    def test_broken_imo_suffix_is_normalized(self, broken):
        # 2026-09-23 に「19:15が待ち遠しいｲﾐ🍠」が公開された
        text = f"待ち遠しい{broken}\n最高ｲﾓ🍠✨ #さつまいもの民 #びっくえんじぇる"
        once = format_post_text(text)

        assert once == "待ち遠しいｲﾓ🍠\n最高ｲﾓ🍠✨\n\n#さつまいもの民 #びっくえんじぇる"
        assert format_post_text(once) == once

    def test_broken_imo_in_single_line_is_split_after_normalizing(self):
        assert format_post_text("楽しみｲﾐ🍠 大好きｲﾓ🍠") == (
            "楽しみｲﾓ🍠\n大好きｲﾓ🍠\n\n#さつまいもの民 #びっくえんじぇる"
        )

    def test_doubled_sweet_potato_is_kept(self):
        # 「ｲﾓ🍠🍠」は強調として許容（数は変えない）
        assert format_post_text("大好きｲﾓ🍠🍠").startswith("大好きｲﾓ🍠🍠\n")


class TestAIGenerator:
    """AIGeneratorクラスのテスト"""
    
    @pytest.fixture
    def generator(self):
        """AIGeneratorインスタンス（truncate_text は頭脳を使わない）"""
        return AIGenerator(brain_client=None)
    
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

    def test_reply_fallback_within_limit(self):
        """頭脳失敗時のリプライ固定文が140文字以内であること"""
        # 長めのユーザー名でも140文字以内
        result = DEFAULT_REPLY_RESPONSE_TEMPLATE.format(username="a" * 15)
        assert len(result) <= MAX_TEXT_LENGTH


class TestBrainIntegration:
    """頭脳（BrainClient）経由の生成と、頭脳が未設定・失敗したときの挙動（2b-3 以降は skip／固定文）"""

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

    def test_generate_reaction_uses_brain(self):
        brain = self._brain(reaction={
            "action": "post",
            "text": "頭脳の応答ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる",
            "emotion_key": "JOY",
            "reason": "嬉しい報告",
        })
        generator = AIGenerator(brain_client=brain)

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

    def test_generate_reaction_without_publish_time(self):
        brain = self._brain(reaction={"action": "post", "text": "x", "emotion_key": "none"})
        generator = AIGenerator(brain_client=brain)
        reaction = self._react(generator, publish_at=None)
        assert brain.invoke_json.call_args.args[1]["publish_at"] == "不明（数時間後）"
        assert reaction.emotion_key is None

    def test_generate_reaction_skip(self):
        brain = self._brain(reaction={"action": "skip", "text": "", "emotion_key": "none", "reason": "URL のみ"})
        generator = AIGenerator(brain_client=brain)

        reaction = self._react(generator)

        assert reaction.action == "skip"
        assert reaction.text == ""
        assert reaction.emotion_key is None
        assert reaction.reason == "URL のみ"
        assert reaction.source == "brain"

    def test_generate_reaction_truncates_and_keeps_line_breaks_within_limit(self):
        # 改行込みで 140 字に収める（Property 5）。文の途中で切れても改行で終わらない
        text = "\n".join(["あ" * 30 + "ｲﾓ🍠"] * 6) + " #さつまいもの民 #びっくえんじぇる"
        brain = self._brain(reaction={"action": "post", "text": text, "emotion_key": "joy"})
        generator = AIGenerator(brain_client=brain)

        result = self._react(generator).text

        assert len(result) <= 140
        assert result.endswith("\n\n#さつまいもの民 #びっくえんじぇる")
        assert "...\n\n#" in result
        assert "\n...\n" not in result

    def test_generate_reaction_logs_error_when_memory_recall_failed(self, caplog):
        brain = self._brain(reaction={"action": "post", "text": "x", "emotion_key": "joy", "memory_count": -1})
        generator = AIGenerator(brain_client=brain)

        with caplog.at_level(logging.ERROR):
            reaction = self._react(generator)

        # 記憶は補助なので反応はそのまま使い、アラーム用に ERROR を残す
        assert reaction.action == "post" and reaction.source == "brain"
        assert any(r.levelno == logging.ERROR and "memory recall failed" in r.getMessage() for r in caplog.records)

    def test_generate_reaction_with_memories_logs_no_error(self, caplog):
        brain = self._brain(reaction={"action": "post", "text": "x", "emotion_key": "joy", "memory_count": 3})
        with caplog.at_level(logging.ERROR):
            self._react(AIGenerator(brain_client=brain))
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]

    def test_generate_reaction_unknown_emotion_key_is_none(self):
        brain = self._brain(reaction={"action": "post", "text": "x", "emotion_key": "banana"})
        generator = AIGenerator(brain_client=brain)
        assert self._react(generator).emotion_key is None

    def _assert_brain_failed_skip(self, reaction):
        assert reaction == Reaction(
            action="skip", text="", emotion_key=None, reason=BRAIN_FAILED_REASON, source="error"
        )

    def test_generate_reaction_skips_on_brain_error(self, caplog):
        generator = AIGenerator(brain_client=self._brain(error="invoke failed"))

        with caplog.at_level(logging.ERROR):
            reaction = self._react(generator, post_type="oshi")

        self._assert_brain_failed_skip(reaction)
        # アラームを鳴らすため ERROR で記録される
        assert any(r.levelno == logging.ERROR and "Brain failed" in r.getMessage() for r in caplog.records)

    def test_generate_reaction_post_without_text_skips(self, caplog):
        brain = self._brain(reaction={"action": "post", "text": "   ", "emotion_key": "joy"})
        generator = AIGenerator(brain_client=brain)

        with caplog.at_level(logging.ERROR):
            reaction = self._react(generator)

        self._assert_brain_failed_skip(reaction)
        assert any(r.levelno == logging.ERROR and "without text" in r.getMessage() for r in caplog.records)

    def test_generate_reaction_without_brain_skips(self, caplog):
        generator = AIGenerator(brain_client=None)

        with caplog.at_level(logging.ERROR):
            reaction = self._react(generator)

        self._assert_brain_failed_skip(reaction)
        assert any(r.levelno == logging.ERROR and "Brain not configured" in r.getMessage() for r in caplog.records)

    def test_reply_response_uses_brain(self):
        brain = self._brain("fan_taroさんありがとうｲﾓ🍠 #さつまいもの民 #びっくえんじぇる")
        generator = AIGenerator(brain_client=brain)

        result = generator.generate_reply_response(
            reply_text="かわいい", reply_username="fan_taro", bot_tweet_text="元投稿"
        )

        # リプライも反応と同じ整形（改行・ハッシュタグ最終行・語尾の正規化）を通す
        assert result == "fan_taroさんありがとうｲﾓ🍠\n\n#さつまいもの民 #びっくえんじぇる"
        brain.invoke.assert_called_once_with(
            "reply_response",
            {"reply_text": "かわいい", "reply_username": "fan_taro", "bot_tweet_text": "元投稿"},
        )

    def test_reply_response_returns_template_on_brain_error(self, caplog):
        generator = AIGenerator(brain_client=self._brain(error="down"))

        with caplog.at_level(logging.ERROR):
            result = generator.generate_reply_response("a", "my_username", "b")

        assert result == DEFAULT_REPLY_RESPONSE_TEMPLATE.format(username="my_username")
        assert "@my_username" in result
        assert "#さつまいもの民" in result and "#びっくえんじぇる" in result
        assert any(r.levelno == logging.ERROR and "Brain failed" in r.getMessage() for r in caplog.records)

    def test_reply_response_without_brain_returns_template(self):
        generator = AIGenerator(brain_client=None)
        assert generator.generate_reply_response("a", "u", "b") == DEFAULT_REPLY_RESPONSE_TEMPLATE.format(username="u")
