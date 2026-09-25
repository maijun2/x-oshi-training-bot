"""
AIGeneratorクラス

キャラクターに合った応答テキストを生成します。

生成元は頭脳（AgentCore Runtime、BrainClient 経由）のみ（フェーズ2b-3 で Haiku 直呼びを撤去）:
- 推し投稿への反応: `react` 1 回で JSON 提案 {action, text, emotion_key, reason} を受け取る（generate_reaction）
- 独り言（3b-1）: `autonomous` 1 回で JSON 提案 ＋ sources を受け取る（generate_autonomous）
- リプライ応答: `reply_response`（generate_reply_response）

頭脳が未設定・失敗したときは logger.error で記録して imomaru-bot-app-errors アラームを鳴らし、
反応は skip（Buffer に入れずメールのみ）、リプライは固定文にする。
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

from ..prompts import (  # noqa: F401  (re-export: 既存の import 経路を維持)
    DEFAULT_REPLY_RESPONSE_TEMPLATE,
    HASHTAGS,
    MAX_TEXT_LENGTH,
    VALID_EMOTION_KEYS,
)
from ..utils.brain_client import BrainClient, BrainError
from .daily_reporter import JST
from .draft_notifier import WEEKDAYS_JA

logger = logging.getLogger(__name__)

REACTION_POST = "post"
REACTION_SKIP = "skip"

# 頭脳が未設定・失敗したときの skip 理由（素案メールに表示）
BRAIN_FAILED_REASON = "頭脳の呼び出しに失敗したため素案なし"


@dataclass
class Reaction:
    """推し投稿への反応の提案（頭脳の JSON を Lambda 側で検証・整形したもの）"""
    action: str                      # REACTION_POST | REACTION_SKIP
    text: str                        # 投稿本文（整形・140 字済み。skip のときは空のことがある）
    emotion_key: Optional[str]       # VALID_EMOTION_KEYS のいずれか。該当なし・不正は None
    reason: str = ""                 # 判断理由（メール表示用）
    source: str = "brain"            # "brain" | "error"（頭脳が未設定・失敗。action は skip）
    sources: List[str] = field(default_factory=list)  # 独り言で使った記憶の id（autonomous のみ）


def format_jst(moment: datetime) -> str:
    """頭脳に渡す時刻表記: 2026-09-16(火) 13:18 JST"""
    jst = moment.astimezone(JST)
    return f"{jst:%Y-%m-%d}({WEEKDAYS_JA[jst.weekday()]}) {jst:%H:%M} JST"

# 文末「ｲﾓ🍠」＋後続の絵文字・記号のあとに次の文が続いていれば、その境界（ハッシュタグ・空白は除く）
# 絵文字・記号は possessive（*+、Python 3.11+）で全部食わせ、末尾の絵文字の手前で切らないようにする。
# 開き括弧類は次の文の先頭なので記号に含めない
# 語尾「ｲﾓ🍠」の崩れ: 「ｲﾐ🍠」（2026-09-23 に公開済み）・全角／全半角混じり。
# 「ｲﾓ🍠🍠」は強調として許容している（TestFormatPostText の実例）ので 🍠 の数は触らない
_BROKEN_IMO = re.compile(r"[ｲイ][ﾐミﾓモ]🍠")

_SENTENCE_BOUNDARY = re.compile(r"(ｲﾓ🍠[^\w\s#「『（(【\[〈《“‘]*+)[ \t]*(?=[^\s#])")


def format_post_text(text: str) -> str:
    """
    投稿本文を「1 文 1 行 ＋ 空行 ＋ ハッシュタグ（最終行）」の形に整える

    モデルが改行を出さずに 1 行で返してきた場合の保険。プロンプトの指示どおり改行済みなら
    文の分割はせず、ハッシュタグの位置だけ正規化する。冪等。
    語尾の崩れ（全角「イモ🍠」・「ｲﾐ🍠」など）は半角「ｲﾓ🍠」に揃える
    （全角は 2026-09-18、ｲﾐ は 09-23 に発生。文の分割も半角前提）。
    """
    body = _BROKEN_IMO.sub("ｲﾓ🍠", text).replace(HASHTAGS, "").strip()
    if "\n" not in body:
        body = _SENTENCE_BOUNDARY.sub(r"\1\n", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return f"{body}\n\n{HASHTAGS}" if body else HASHTAGS


class AIGenerator:
    """
    頭脳（AgentCore Runtime）に依頼してキャラクターに合った応答テキストを生成するクラス

    Attributes:
        brain_client: 頭脳（AgentCore Runtime）クライアント
    """

    def __init__(self, brain_client: Optional[BrainClient]):
        """
        AIGeneratorを初期化

        Args:
            brain_client: 頭脳（AgentCore Runtime）クライアント。None なら頭脳の失敗と同じ扱い
        """
        self.brain_client = brain_client

    def truncate_text(self, text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
        """
        テキストを指定文字数以内に切り詰め
        
        Args:
            text: 切り詰めるテキスト
            max_length: 最大文字数
        
        Returns:
            切り詰められたテキスト
        """
        if len(text) <= max_length:
            return text
        
        # ハッシュタグを保持するために、ハッシュタグ部分を抽出
        hashtags = HASHTAGS
        hashtag_len = len(hashtags)
        
        # ハッシュタグを除いた最大長（本文とハッシュタグの間の空行 "\n\n" 分を引く）
        content_max_len = max_length - hashtag_len - 2
        
        # テキストからハッシュタグを除去
        text_without_hashtags = text.replace(hashtags, "").strip()
        
        if len(text_without_hashtags) > content_max_len:
            # 切り詰めて「...」を追加（切れ目が改行で終わらないように詰める）
            truncated = text_without_hashtags[:content_max_len - 3].rstrip() + "..."
            return f"{truncated}\n\n{hashtags}"
        
        # ハッシュタグがない場合でも、本文が短ければハッシュタグを追加
        if hashtags not in text:
            return f"{text_without_hashtags}\n\n{hashtags}"
        
        return text
    
    def _finalize_post_text(self, text: str) -> str:
        """改行・ハッシュタグ位置を整えてから 140 字（改行込み）に収める"""
        return self.truncate_text(format_post_text(text))

    def _ask_brain(self, task: str, task_input: Dict[str, Any]) -> Optional[str]:
        """
        頭脳にタスクを依頼する。未設定・失敗なら ERROR ログ（アラーム）を出して None
        """
        if self.brain_client is None:
            logger.error(f"Brain not configured for task={task}")
            return None
        try:
            return self.brain_client.invoke(task, task_input)
        except BrainError as e:
            logger.error(f"Brain failed for task={task}: {e}")
            return None

    def _ask_brain_json(self, task: str, task_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """_ask_brain の JSON 提案版（react）。未設定・失敗なら ERROR ログ（アラーム）を出して None"""
        if self.brain_client is None:
            logger.error(f"Brain not configured for task={task}")
            return None
        try:
            return self.brain_client.invoke_json(task, task_input)
        except BrainError as e:
            logger.error(f"Brain failed for task={task}: {e}")
            return None

    def generate_reaction(
        self,
        post_content: str,
        posted_at: datetime,
        now: datetime,
        publish_at: Optional[datetime],
        post_type: str = "oshi",
    ) -> Reaction:
        """
        推し投稿への反応を提案として生成する（頭脳 `react`。未設定・失敗時は skip）

        Args:
            post_content: 元の投稿内容
            posted_at: 投稿時刻（aware datetime）
            now: 現在時刻（aware datetime）
            publish_at: 公開予定時刻（次の Buffer 予約枠）。不明なら None
            post_type: "oshi" または "group"

        Returns:
            Reaction。text は整形・140 字済み、emotion_key は検証済み（不正は None）。
            頭脳が未設定・失敗・post なのに本文なしのときは action=skip、reason=BRAIN_FAILED_REASON
        """
        proposal = self._ask_brain_json(
            "react",
            {
                "post_content": post_content,
                "post_type": post_type,
                "posted_at": format_jst(posted_at),
                "now": format_jst(now),
                "publish_at": format_jst(publish_at) if publish_at else "不明（数時間後）",
            },
        )
        if proposal is not None:
            action = proposal.get("action")
            raw_text = proposal.get("text") or ""
            if action not in (REACTION_POST, REACTION_SKIP):
                logger.error(f"Brain returned unknown action={action!r}; treating as post")
                action = REACTION_POST
            text = self._finalize_post_text(raw_text) if raw_text.strip() else ""
            memory_count = proposal.get("memory_count")
            if memory_count == -1:
                # 記憶は補助なので反応はそのまま使う。取れていないことに気づけるよう ERROR（アラーム）で残す
                logger.error("Brain memory recall failed for task=react; reaction generated without memories")
            if action == REACTION_POST and not text:
                logger.error("Brain returned action=post without text; skipping reaction")
            else:
                emotion_key = self._validate_emotion_key(proposal.get("emotion_key"))
                reason = str(proposal.get("reason") or "")
                logger.info(
                    f"Generated reaction using brain for {post_type} post: action={action} "
                    f"emotion={emotion_key} {len(text)} chars"
                )
                return Reaction(action=action, text=text, emotion_key=emotion_key, reason=reason, source="brain")

        return Reaction(action=REACTION_SKIP, text="", emotion_key=None, reason=BRAIN_FAILED_REASON, source="error")

    def generate_autonomous(
        self,
        kind: str,
        candidates: Sequence[Dict[str, str]],
        now: datetime,
        publish_at: Optional[datetime],
        days_left: Optional[int] = None,
        event_date: Optional[date] = None,
        recent_texts: Sequence[str] = (),
    ) -> Reaction:
        """
        推しの投稿がない夜の独り言を提案として生成する（頭脳 `autonomous`、3b-1。未設定・失敗時は skip）

        Args:
            kind: 素案タイプ（"A" / "B"）
            candidates: [{"id", "text", "created_at"}]（AutonomousSelector が選んだ記憶）
            now: 現在時刻
            publish_at: 公開予定時刻（次の Buffer 予約枠）
            days_left: タイプ A のイベントまでの日数
            event_date: タイプ A のイベント日
            recent_texts: 直近の独り言の本文

        Returns:
            Reaction（sources は候補の id に含まれるものだけ）。頭脳が未設定・失敗・post なのに本文なしは
            action=skip、reason=BRAIN_FAILED_REASON、source="error"
        """
        task_input: Dict[str, Any] = {
            "kind": kind,
            "candidates": [dict(c) for c in candidates],
            "now": format_jst(now),
            "publish_at": format_jst(publish_at) if publish_at else "不明（数時間後）",
            "recent_texts": list(recent_texts),
        }
        if days_left is not None:
            task_input["days_left"] = days_left
        if event_date is not None:
            task_input["event_date"] = f"{event_date:%Y-%m-%d}({WEEKDAYS_JA[event_date.weekday()]})"

        proposal = self._ask_brain_json("autonomous", task_input)
        if proposal is not None:
            action = proposal.get("action")
            raw_text = proposal.get("text") or ""
            if action not in (REACTION_POST, REACTION_SKIP):
                logger.error(f"Brain returned unknown action={action!r} for task=autonomous; skipping")
                action = None
            text = self._finalize_post_text(raw_text) if raw_text.strip() else ""
            if action == REACTION_POST and not text:
                logger.error("Brain returned action=post without text for task=autonomous; skipping")
            elif action is not None:
                candidate_ids = [str(c.get("id", "")) for c in candidates]
                raw_sources = proposal.get("sources")
                sources = [s for s in candidate_ids if isinstance(raw_sources, list) and s in raw_sources]
                if action == REACTION_POST and not sources:
                    # 根拠をメールに出すのが安全弁なので、頭脳が id を返さなければ渡した候補を全部載せる
                    logger.warning("Brain returned no valid sources for task=autonomous; using all candidates")
                    sources = candidate_ids
                emotion_key = self._validate_emotion_key(proposal.get("emotion_key"))
                logger.info(
                    f"Generated autonomous post using brain: kind={kind} action={action} "
                    f"emotion={emotion_key} {len(text)} chars sources={len(sources)}"
                )
                return Reaction(
                    action=action, text=text, emotion_key=emotion_key,
                    reason=str(proposal.get("reason") or ""), source="brain", sources=sources,
                )

        return Reaction(action=REACTION_SKIP, text="", emotion_key=None, reason=BRAIN_FAILED_REASON, source="error")

    @staticmethod
    def _validate_emotion_key(value: Any) -> Optional[str]:
        """感情キーを検証する。有効なら小文字のキー、none・不正・未指定は None"""
        if not isinstance(value, str):
            return None
        emotion_key = value.strip().lower()
        if emotion_key in VALID_EMOTION_KEYS:
            return emotion_key
        if emotion_key not in ("", "none"):
            logger.warning(f"Unknown emotion key returned: {emotion_key}")
        return None

    def generate_reply_response(
        self,
        reply_text: str,
        reply_username: str,
        bot_tweet_text: str,
    ) -> str:
        """
        リプライに対する応答テキストを生成

        Args:
            reply_text: リプライの本文
            reply_username: リプライユーザーのユーザー名
            bot_tweet_text: ボットが投稿した元のツイート本文

        Returns:
            生成された応答テキスト（140文字以内）。頭脳が未設定・失敗なら固定文
            （latest_reply_check_id は先に進むので再試行されない。黙って落とさず固定文で返す）
        """
        brain_text = self._ask_brain(
            "reply_response",
            {"reply_text": reply_text, "reply_username": reply_username, "bot_tweet_text": bot_tweet_text},
        )
        if brain_text is not None:
            truncated_text = self._finalize_post_text(brain_text)
            logger.info(f"Generated reply response using brain: {len(truncated_text)} chars")
            return truncated_text

        return DEFAULT_REPLY_RESPONSE_TEMPLATE.format(username=reply_username)
