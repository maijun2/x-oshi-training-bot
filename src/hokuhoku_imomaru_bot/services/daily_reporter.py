"""
DailyReporterクラス

日報投稿の生成と送信を行います。
"""
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from ..models.bot_state import BotState
from ..utils.agentcore_runtime import invoke_agent_runtime

logger = logging.getLogger(__name__)

# 日本標準時（JST）
JST = timezone(timedelta(hours=9))

# 日報投稿のテンプレート
DAILY_REPORT_TEMPLATE = """今日の活動報告ｲﾓ🍠
じゅりちゃんの投稿：{daily_oshi_count}回
グループの投稿：{daily_group_count}回
みんなからのいいね：{daily_like_count}回
みんなのリポスト：{daily_repost_count}回
今日の獲得XP：{daily_xp:.1f} XP
現在Lv.{current_level} → 次まで{next_level_xp} XP
#さつまいもの民 #びっくえんじぇる"""

# 日報投稿時刻（21:00 JST以降）
DAILY_REPORT_HOUR = 21

# ポスト分析スレッドの設定
POST_ANALYSIS_PREFIX = "🔍 今日のポスト分析ｲﾓ🍠\n"
MAX_TEXT_LENGTH = 140

# 朝コンテンツの設定
YOUTUBE_PREFIX = "🎬 YouTube新着ｲﾓ🍠\n"
TRANSLATION_PREFIX = "🌎 English Reportｲﾓ🍠\n"

# 推し投稿が少ない日の閾値（この件数以下なら朝コンテンツを投稿）
LOW_ACTIVITY_THRESHOLD = 3


class DailyReporter:
    """
    日報投稿の生成と送信を行うクラス
    
    Attributes:
        api_client: XAPIClientインスタンス
    """
    
    def __init__(self, api_client):
        """
        DailyReporterを初期化
        
        Args:
            api_client: XAPIClientインスタンス
        """
        self.api_client = api_client
    
    def should_post_daily_report(
        self,
        state: BotState,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """
        日報投稿を行うべきかを判定
        
        Args:
            state: 現在のボット状態
            current_time: 現在時刻（Noneの場合は現在時刻を使用）
        
        Returns:
            日報投稿を行うべきかどうか
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        
        # JSTに変換
        jst_time = current_time.astimezone(JST)
        today = jst_time.strftime("%Y-%m-%d")
        
        # 21:00 JST以降で、今日まだ日報を投稿していない場合
        return (
            jst_time.hour >= DAILY_REPORT_HOUR and
            state.last_daily_report_date != today
        )
    
    def post_daily_report(
        self,
        state: BotState,
        next_level_xp: int,
    ) -> Optional[str]:
        """
        日報投稿を送信

        Args:
            state: 現在のボット状態
            next_level_xp: 次のレベルまでに必要なXP

        Returns:
            投稿成功時はツイートID、失敗時はNone
        """
        try:
            text = self.generate_daily_report(state, next_level_xp)

            # X API v2で投稿
            result = self.api_client.post_tweet(text)

            if result:
                tweet_id = result.get("data", {}).get("id")
                logger.info(f"Daily report posted successfully: {tweet_id}")
                return tweet_id
            else:
                logger.warning("Daily report post returned empty result")
                return None

        except Exception as e:
            logger.error(f"Failed to post daily report: {e}")
            return None

    
    def generate_daily_report(
        self,
        state: BotState,
        next_level_xp: int,
    ) -> str:
        """
        日報投稿のテキストを生成
        
        Args:
            state: 現在のボット状態
            next_level_xp: 次のレベルまでに必要なXP
        
        Returns:
            日報投稿テキスト
        """
        return DAILY_REPORT_TEMPLATE.format(
            daily_oshi_count=state.daily_oshi_count,
            daily_group_count=state.daily_group_count,
            daily_like_count=state.daily_like_count,
            daily_repost_count=state.daily_repost_count,
            daily_xp=state.daily_xp,
            current_level=state.current_level,
            next_level_xp=next_level_xp,
        )
    
    def get_today_date_jst(
        self,
        current_time: Optional[datetime] = None,
    ) -> str:
        """
        現在のJST日付を取得
        
        Args:
            current_time: 現在時刻（Noneの場合は現在時刻を使用）
        
        Returns:
            YYYY-MM-DD形式の日付文字列
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        
        jst_time = current_time.astimezone(JST)
        return jst_time.strftime("%Y-%m-%d")

    def post_analysis_thread(
        self,
        reply_to_tweet_id: str,
        oshi_user_id: str,
        latest_tweet_id: str = "0",
    ) -> bool:
        """
        日報投稿にスレッドとしてポスト分析結果を投稿する

        AgentCore Runtime でエゴサ分析を実行し、結果を日報のリプライとして投稿する。

        Args:
            reply_to_tweet_id: リプライ先の日報ツイートID
            oshi_user_id: 推しのXアカウントユーザーID
            latest_tweet_id: 分析対象の起点ツイートID

        Returns:
            投稿成功の可否
        """
        try:
            # AgentCore Runtime でエゴサ分析を実行
            prompt = (
                f"ユーザーID {oshi_user_id} の最新ポストへのリプライを分析して、"
                f"ファンの反応をポジティブな内容を中心に要約・報告してください。"
                f"\n\n出力フォーマットの指定: "
                f"あなたは「ほくほくいも丸くん🍠」というキャラクターです。"
                f"語尾は必ず「◯◯ｲﾓ🍠」の形式にしてください（例：「嬉しいｲﾓ🍠」「すごいｲﾓ🍠」）。"
                f"回答は短い日本語プレーンテキストで、改行区切りで見やすく出力してください。"
                f"Markdown記法（#や**や-）は使わないでください。"
                f"以下のフォーマット例に従ってください:\n"
                f"リプライ○件を分析したｲﾓ🍠\n"
                f"💜 ファンの反応：（一言まとめ）\n"
                f"✨ 注目：（特に盛り上がった話題）\n"
                f"（数値情報）ｲﾓ～🍠"
            )
            context = {
                "source": "imomaru-bot-handler",
                "request_type": "ego_search",
                "user_id": oshi_user_id,
                "latest_post_id": latest_tweet_id,
            }

            ego_result = invoke_agent_runtime(
                prompt=prompt,
                context=context,
                timeout=120,
            )

            if not ego_result["success"]:
                logger.error(f"AgentCore Runtime failed: {ego_result['error']}")
                return False

            # レスポンスからテキストを抽出・整形
            body = self._extract_analysis_text(ego_result["response"])
            if not body:
                logger.warning("AgentCore Runtime returned empty response")
                return False

            # 140文字制限に合わせて切り詰め
            max_body_len = MAX_TEXT_LENGTH - len(POST_ANALYSIS_PREFIX)
            body = self._truncate_analysis(body, max_body_len)

            tweet_text = f"{POST_ANALYSIS_PREFIX}{body}"

            # スレッドとしてリプライ投稿
            result = self.api_client.post_tweet(
                text=tweet_text,
                reply_to_tweet_id=reply_to_tweet_id,
            )

            if result:
                new_id = result.get("data", {}).get("id")
                logger.info(f"Post analysis thread posted: {new_id}")
                return True
            else:
                logger.warning("Post analysis thread returned empty result")
                return False

        except Exception as e:
            logger.error(f"Failed to post analysis thread: {e}")
            return False

    @staticmethod
    def _extract_analysis_text(raw: str) -> str:
        """
        AgentCore Runtime のレスポンスから投稿用テキストを抽出する
        """
        text = raw

        # JSON文字列の場合、responseフィールドを抽出
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "response" in parsed:
                text = parsed["response"]
        except (json.JSONDecodeError, TypeError):
            pass

        # エスケープされた改行を実際の改行に
        text = text.replace("\\n", "\n")

        # <think> タグの中身を保持（フォールバック用）
        think_content = ""
        think_match = re.search(r"<think>(.*?)(?:</think>|$)", text, flags=re.DOTALL)
        if think_match:
            think_content = think_match.group(1)

        # <think> タグを除去
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)

        # JSON の残骸を除去
        cleaned = re.sub(r'^[\s,"]+\s*"?\w+"?\s*:.*', "", cleaned, flags=re.DOTALL)
        cleaned = cleaned.strip()

        # 思考過程のみで本文が空の場合、思考内容の最後の文をフォールバック
        if not cleaned and think_content:
            sentences = [s.strip() for s in re.split(r"[。\n]", think_content) if s.strip()]
            if sentences:
                cleaned = sentences[-1]

        # Markdown記法を除去
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"---+", "", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

        # 連続する空行を1つに
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        # ツイートID（15桁以上の数字列）を除去
        cleaned = re.sub(r"[（(]\d{15,}[）)]", "", cleaned)
        cleaned = re.sub(r"\d{15,}", "", cleaned)

        return cleaned.strip()

    @staticmethod
    def _truncate_analysis(text: str, max_len: int) -> str:
        """
        分析テキストを文字数制限に合わせて切り詰める

        末尾の要約文を優先的に残す。
        """
        if len(text) <= max_len:
            return text

        # 末尾の要約文を探す
        summary_markers = ["全体として", "まとめると", "総じて", "結論として", "全体的に"]
        summary = ""
        for marker in summary_markers:
            pos = text.rfind(marker)
            if pos >= 0:
                summary = text[pos:]
                break

        if summary and len(summary) + 10 < max_len:
            first_line_end = text.find("\n")
            if first_line_end > 0 and first_line_end + len(summary) + 1 <= max_len:
                return text[:first_line_end] + "\n" + summary
            return summary

        # 文の区切りで切り詰め
        truncated = text[:max_len]
        for sep in ["。", "！", "✨", "💜", "🎀", "\n"]:
            pos = truncated.rfind(sep)
            if pos > max_len // 2:
                return truncated[:pos + len(sep)]

        return truncated

    def should_post_morning_content(
        self,
        prev_daily_oshi_count: int,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """
        朝のコンテンツ（YouTube/翻訳）を投稿すべきか判定

        前日の推し投稿が少ない日（閾値以下）の朝9時台に投稿する。

        Args:
            prev_daily_oshi_count: 前日の推し投稿数
            current_time: 現在時刻

        Returns:
            投稿すべきかどうか
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        jst_time = current_time.astimezone(JST)

        # 朝9時台（9:00〜9:59）のみ
        if jst_time.hour != 9:
            return False

        return prev_daily_oshi_count <= LOW_ACTIVITY_THRESHOLD

    def should_post_translation(
        self,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """
        翻訳投稿を行うべきか判定（日曜のみ）

        Args:
            current_time: 現在時刻

        Returns:
            翻訳投稿を行うべきかどうか
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        jst_time = current_time.astimezone(JST)
        return jst_time.weekday() == 6  # 日曜日

    def post_youtube_search(
        self,
        oshi_user_id: str,
    ) -> bool:
        """
        YouTube新着検索結果を単独ポストとして投稿する

        AgentCore Runtime でYouTube検索を実行し、新着があれば投稿する。

        Args:
            oshi_user_id: 推しのXアカウントユーザーID

        Returns:
            投稿成功の可否（新着なしの場合もFalse）
        """
        try:
            prompt = (
                f"「甘木ジュリ」または「びっくえんじぇる」の最新YouTube動画を1件検索してください。"
                f"\n\n出力フォーマットの指定: "
                f"あなたは「ほくほくいも丸くん🍠」というキャラクターです。"
                f"語尾は必ず「◯◯ｲﾓ🍠」の形式にしてください。"
                f"回答は短い日本語プレーンテキストで改行区切りで出力してください。"
                f"Markdown記法は使わないでください。"
                f"YouTube動画のURL（https://youtu.be/動画ID の短縮形式）を必ず含めてください。"
                f"動画が見つからない場合は「新着なし」とだけ返してください。"
                f"以下のフォーマット例に従ってください:\n"
                f"じゅりちゃんの新着動画を見つけたｲﾓ🍠\n"
                f"📺 （動画タイトル）\n"
                f"🔗 （YouTube URL）\n"
                f"（再生数や投稿日の情報）ｲﾓ～🍠"
            )
            context = {
                "source": "imomaru-bot-handler",
                "request_type": "youtube_search",
                "user_id": oshi_user_id,
            }

            yt_result = invoke_agent_runtime(
                prompt=prompt,
                context=context,
                timeout=120,
            )

            if not yt_result["success"]:
                logger.error(f"AgentCore Runtime YouTube search failed: {yt_result['error']}")
                return False

            body = self._extract_analysis_text(yt_result["response"])
            if not body or "新着なし" in body:
                logger.info("No new YouTube videos found")
                return False

            max_body_len = MAX_TEXT_LENGTH - len(YOUTUBE_PREFIX)
            body = self._truncate_analysis(body, max_body_len)
            tweet_text = f"{YOUTUBE_PREFIX}{body}"

            result = self.api_client.post_tweet(text=tweet_text)
            if result:
                tweet_id = result.get("data", {}).get("id")
                logger.info(f"YouTube search posted: {tweet_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to post YouTube search: {e}")
            return False

    def post_translation(
        self,
        oshi_user_id: str,
        latest_tweet_id: str = "0",
    ) -> bool:
        """
        人気ポストの翻訳を単独ポストとして投稿する（日曜のみ）

        AgentCore Runtime でいいね・リポストが多い記事を1つ選んで翻訳する。

        Args:
            oshi_user_id: 推しのXアカウントユーザーID
            latest_tweet_id: 分析対象の起点ツイートID

        Returns:
            投稿成功の可否
        """
        try:
            prompt = (
                f"ユーザーID {oshi_user_id} の最近のポストの中から、"
                f"いいねやリポストが最も多い人気ポストを1つ選んで、"
                f"元気なアイドル口調を維持したまま英語に翻訳してください。"
                f"\n\n出力フォーマットの指定: "
                f"あなたは「ほくほくいも丸くん🍠」というキャラクターです。"
                f"語尾は必ず「◯◯ｲﾓ🍠」の形式にしてください。"
                f"回答は短い日本語プレーンテキストで改行区切りで出力してください。"
                f"Markdown記法は使わないでください。"
                f"以下のフォーマット例に従ってください:\n"
                f"今週の人気ポストを翻訳したｲﾓ🍠\n"
                f"🌎 （英語翻訳）\n"
                f"いいね○件の人気ポストｲﾓ～🍠"
            )
            context = {
                "source": "imomaru-bot-handler",
                "request_type": "translation",
                "user_id": oshi_user_id,
                "latest_post_id": latest_tweet_id,
            }

            tr_result = invoke_agent_runtime(
                prompt=prompt,
                context=context,
                timeout=120,
            )

            if not tr_result["success"]:
                logger.error(f"AgentCore Runtime translation failed: {tr_result['error']}")
                return False

            body = self._extract_analysis_text(tr_result["response"])
            if not body:
                logger.warning("AgentCore Runtime translation returned empty response")
                return False

            max_body_len = MAX_TEXT_LENGTH - len(TRANSLATION_PREFIX)
            body = self._truncate_analysis(body, max_body_len)
            tweet_text = f"{TRANSLATION_PREFIX}{body}"

            result = self.api_client.post_tweet(text=tweet_text)
            if result:
                tweet_id = result.get("data", {}).get("id")
                logger.info(f"Translation posted: {tweet_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to post translation: {e}")
            return False
