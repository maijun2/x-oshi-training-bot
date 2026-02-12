"""
DailyReporter AgentCore Runtime連携機能のユニットテスト

post_youtube_search, post_translation,
should_post_morning_content, should_post_translation,
_extract_analysis_text, _truncate_analysis を検証
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

from src.hokuhoku_imomaru_bot.services.daily_reporter import (
    DailyReporter,
    JST,
    MAX_TEXT_LENGTH,
    YOUTUBE_PREFIX,
    TRANSLATION_PREFIX,
    LOW_ACTIVITY_THRESHOLD,
)


@pytest.fixture
def mock_api_client():
    return Mock()


@pytest.fixture
def reporter(mock_api_client):
    return DailyReporter(api_client=mock_api_client)


# ========================================
# should_post_morning_content のテスト
# ========================================

class TestShouldPostMorningContent:
    """朝コンテンツ投稿判定のテスト"""

    def test_true_at_10am_with_low_activity(self, reporter):
        """10時台 & 推し投稿が閾値以下 → True"""
        # 10:30 JST = 1:30 UTC
        t = datetime(2024, 1, 15, 1, 30, 0, tzinfo=timezone.utc)
        assert reporter.should_post_morning_content(2, t) is True

    def test_false_at_9am(self, reporter):
        """9時台 → False"""
        # 9:30 JST = 0:30 UTC
        t = datetime(2024, 1, 15, 0, 30, 0, tzinfo=timezone.utc)
        assert reporter.should_post_morning_content(0, t) is False

    def test_false_at_11am(self, reporter):
        """11時台 → False"""
        # 11:00 JST = 2:00 UTC
        t = datetime(2024, 1, 15, 2, 0, 0, tzinfo=timezone.utc)
        assert reporter.should_post_morning_content(0, t) is False

    def test_false_with_high_activity(self, reporter):
        """推し投稿が閾値超 → False"""
        # 10:00 JST = 1:00 UTC
        t = datetime(2024, 1, 15, 1, 0, 0, tzinfo=timezone.utc)
        assert reporter.should_post_morning_content(4, t) is False

    def test_true_at_threshold_boundary(self, reporter):
        """推し投稿がちょうど閾値 → True"""
        t = datetime(2024, 1, 15, 1, 0, 0, tzinfo=timezone.utc)
        assert reporter.should_post_morning_content(LOW_ACTIVITY_THRESHOLD, t) is True

    def test_true_with_zero_activity(self, reporter):
        """推し投稿0件 → True"""
        t = datetime(2024, 1, 15, 1, 0, 0, tzinfo=timezone.utc)
        assert reporter.should_post_morning_content(0, t) is True


# ========================================
# should_post_translation のテスト
# ========================================

class TestShouldPostTranslation:
    """翻訳投稿判定のテスト"""

    def test_true_on_sunday(self, reporter):
        """日曜日 → True"""
        # 2024-01-14 は日曜日
        t = datetime(2024, 1, 14, 0, 0, 0, tzinfo=timezone.utc)
        assert reporter.should_post_translation(t) is True

    def test_false_on_monday(self, reporter):
        """月曜日 → False"""
        t = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        assert reporter.should_post_translation(t) is False

    def test_false_on_saturday(self, reporter):
        """土曜日 → False"""
        t = datetime(2024, 1, 13, 0, 0, 0, tzinfo=timezone.utc)
        assert reporter.should_post_translation(t) is False


# ========================================
# _extract_analysis_text のテスト
# ========================================

class TestExtractAnalysisText:
    """_extract_analysis_text静的メソッドのテスト"""

    def test_plain_text(self):
        """プレーンテキストをそのまま返す"""
        result = DailyReporter._extract_analysis_text("分析結果ｲﾓ🍠")
        assert result == "分析結果ｲﾓ🍠"

    def test_json_response_field(self):
        """JSON形式のresponseフィールドを抽出"""
        raw = '{"response": "分析結果ｲﾓ🍠"}'
        result = DailyReporter._extract_analysis_text(raw)
        assert "分析結果" in result

    def test_escaped_newlines(self):
        """エスケープされた改行を実際の改行に変換"""
        raw = "行1\\n行2\\n行3"
        result = DailyReporter._extract_analysis_text(raw)
        assert "\n" in result
        assert "行1" in result
        assert "行3" in result

    def test_removes_think_tags(self):
        """<think>タグを除去"""
        raw = "<think>考え中...</think>本文ｲﾓ🍠"
        result = DailyReporter._extract_analysis_text(raw)
        assert "考え中" not in result
        assert "本文ｲﾓ🍠" in result

    def test_think_only_fallback(self):
        """本文が空で<think>のみの場合、思考内容の最後の文をフォールバック"""
        raw = "<think>分析中。結果はポジティブ。ファンが喜んでいる</think>"
        result = DailyReporter._extract_analysis_text(raw)
        assert "ファンが喜んでいる" in result

    def test_removes_markdown_bold(self):
        """Markdown太字を除去"""
        raw = "**重要な**テキスト"
        result = DailyReporter._extract_analysis_text(raw)
        assert "**" not in result
        assert "重要な" in result

    def test_removes_markdown_headers(self):
        """Markdownヘッダーを除去"""
        raw = "## 見出し\n本文"
        result = DailyReporter._extract_analysis_text(raw)
        assert "##" not in result
        assert "見出し" in result

    def test_removes_tweet_ids(self):
        """ツイートID（15桁以上の数字列）を除去"""
        raw = "分析結果（1234567890123456）ｲﾓ🍠"
        result = DailyReporter._extract_analysis_text(raw)
        assert "1234567890123456" not in result
        assert "分析結果" in result

    def test_removes_horizontal_rules(self):
        """水平線（---）を除去"""
        raw = "セクション1\n---\nセクション2"
        result = DailyReporter._extract_analysis_text(raw)
        assert "---" not in result

    def test_removes_backtick_code(self):
        """バッククォートのコード記法を除去"""
        raw = "コマンド `test` を実行"
        result = DailyReporter._extract_analysis_text(raw)
        assert "`" not in result
        assert "test" in result

    def test_collapses_multiple_blank_lines(self):
        """連続する空行を1つに圧縮"""
        raw = "行1\n\n\n\n行2"
        result = DailyReporter._extract_analysis_text(raw)
        assert "\n\n\n" not in result

    def test_empty_string(self):
        """空文字列を処理"""
        result = DailyReporter._extract_analysis_text("")
        assert result == ""

    def test_unclosed_think_tag(self):
        """閉じられていない<think>タグを処理"""
        raw = "<think>考え中...本文ｲﾓ🍠"
        result = DailyReporter._extract_analysis_text(raw)
        # 閉じられていないthinkタグは全体が除去される
        assert isinstance(result, str)


# ========================================
# _truncate_analysis のテスト
# ========================================

class TestTruncateAnalysis:
    """_truncate_analysis静的メソッドのテスト"""

    def test_short_text_unchanged(self):
        """制限内のテキストはそのまま返す"""
        text = "短いテキスト"
        result = DailyReporter._truncate_analysis(text, 100)
        assert result == text

    def test_truncates_at_sentence_boundary(self):
        """文の区切りで切り詰める"""
        text = "最初の文。二番目の文。三番目の文。四番目の文。五番目の文。"
        result = DailyReporter._truncate_analysis(text, 20)
        assert len(result) <= 20
        assert result.endswith("。")

    def test_preserves_summary_line(self):
        """要約文を優先的に残す"""
        text = "詳細1\n詳細2\n全体として良い反応ｲﾓ🍠"
        result = DailyReporter._truncate_analysis(text, 30)
        assert "全体として" in result

    def test_exact_length_unchanged(self):
        """ちょうど制限長のテキストはそのまま"""
        text = "a" * 50
        result = DailyReporter._truncate_analysis(text, 50)
        assert result == text


# ========================================
# post_youtube_search のテスト
# ========================================

class TestPostYoutubeSearch:
    """post_youtube_search メソッドのテスト"""

    @patch("src.hokuhoku_imomaru_bot.services.daily_reporter.invoke_agent_runtime")
    def test_success(self, mock_invoke, reporter, mock_api_client):
        """正常系: YouTube新着を投稿"""
        mock_invoke.return_value = {
            "success": True,
            "response": "じゅりちゃんの新着動画を見つけたｲﾓ🍠\n📺 新曲MV\n🔗 https://youtu.be/abc123",
        }
        mock_api_client.post_tweet.return_value = {"data": {"id": "888"}}

        result = reporter.post_youtube_search(oshi_user_id="456")

        assert result is True
        mock_api_client.post_tweet.assert_called_once()
        tweet_text = mock_api_client.post_tweet.call_args.kwargs["text"]
        assert YOUTUBE_PREFIX in tweet_text

    @patch("src.hokuhoku_imomaru_bot.services.daily_reporter.invoke_agent_runtime")
    def test_no_new_videos(self, mock_invoke, reporter, mock_api_client):
        """新着なしの場合にFalseを返す"""
        mock_invoke.return_value = {
            "success": True,
            "response": "新着なし",
        }

        result = reporter.post_youtube_search(oshi_user_id="456")

        assert result is False
        mock_api_client.post_tweet.assert_not_called()

    @patch("src.hokuhoku_imomaru_bot.services.daily_reporter.invoke_agent_runtime")
    def test_agent_failure(self, mock_invoke, reporter, mock_api_client):
        """AgentCore Runtime失敗時にFalseを返す"""
        mock_invoke.return_value = {
            "success": False,
            "response": "",
            "error": "Timeout",
        }

        result = reporter.post_youtube_search(oshi_user_id="456")

        assert result is False

    @patch("src.hokuhoku_imomaru_bot.services.daily_reporter.invoke_agent_runtime")
    def test_exception_handling(self, mock_invoke, reporter, mock_api_client):
        """例外発生時にFalseを返す"""
        mock_invoke.side_effect = RuntimeError("Network error")

        result = reporter.post_youtube_search(oshi_user_id="456")

        assert result is False


# ========================================
# post_translation のテスト
# ========================================

class TestPostTranslation:
    """post_translation メソッドのテスト"""

    @patch("src.hokuhoku_imomaru_bot.services.daily_reporter.invoke_agent_runtime")
    def test_success(self, mock_invoke, reporter, mock_api_client):
        """正常系: 翻訳を投稿"""
        mock_invoke.return_value = {
            "success": True,
            "response": "今週の人気ポストを翻訳したｲﾓ🍠\n🌎 I had a great live!\nいいね50件の人気ポストｲﾓ～🍠",
        }
        mock_api_client.post_tweet.return_value = {"data": {"id": "777"}}

        result = reporter.post_translation(oshi_user_id="456")

        assert result is True
        tweet_text = mock_api_client.post_tweet.call_args.kwargs["text"]
        assert TRANSLATION_PREFIX in tweet_text

    @patch("src.hokuhoku_imomaru_bot.services.daily_reporter.invoke_agent_runtime")
    def test_empty_response(self, mock_invoke, reporter, mock_api_client):
        """空レスポンス時にFalseを返す"""
        mock_invoke.return_value = {
            "success": True,
            "response": "",
        }

        result = reporter.post_translation(oshi_user_id="456")

        assert result is False

    @patch("src.hokuhoku_imomaru_bot.services.daily_reporter.invoke_agent_runtime")
    def test_agent_failure(self, mock_invoke, reporter, mock_api_client):
        """AgentCore Runtime失敗時にFalseを返す"""
        mock_invoke.return_value = {
            "success": False,
            "response": "",
            "error": "Error",
        }

        result = reporter.post_translation(oshi_user_id="456")

        assert result is False

    @patch("src.hokuhoku_imomaru_bot.services.daily_reporter.invoke_agent_runtime")
    def test_exception_handling(self, mock_invoke, reporter, mock_api_client):
        """例外発生時にFalseを返す"""
        mock_invoke.side_effect = Exception("Unexpected")

        result = reporter.post_translation(oshi_user_id="456")

        assert result is False
