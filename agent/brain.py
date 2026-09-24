"""
いも丸の頭脳（フェーズ2b-2-1、3a-read）

Strands Agent ＋ Bedrock（既定: moonshotai.kimi-k2.5。BRAIN_MODEL_ID で差し替え可）で、Lambda から依頼された 2 タスクを処理する。
- react:          推し／グループの投稿への反応を JSON の「提案」で返す
                  {"action": "post"|"skip", "text": 応答文, "emotion_key": 感情キー|"none", "reason": 理由}
- reply_response: 許可ユーザーからのリプライへの応答文

方針:
- Agent はリクエストごとに生成する（Runtime のセッションを Lambda 1 回分で使い回すため、
  会話履歴が投稿間で混ざらないようにする）
- キャラクター定義は system prompt、反応対象（投稿本文・時刻情報・推しの記憶）は user message に分ける（設計書 §10-8）
- 推しの記憶（3a-read）: react のたびに投稿本文をクエリに AgentCore Memory を retrieve し、user message に注入する
  （Strands の @tool にはしない。モデル呼び出しは 1 回のまま。maijun 決定 2026-09-25）。
  取得に失敗しても記憶なしで生成を続け、memory_count=-1 を返す（Lambda が ERROR ログ → アラーム）
- 頭脳は「考える」だけ。Buffer／メール／X への書き込みとガード（140 字・キャップ・画像 1 日 1 回）は
  Lambda 側（AIGenerator / BufferScheduler）が従来どおり行う（設計書 §10-11）
- JSON はプロンプト指示で出させ、ここで寛容にパースして形を検証する。形が崩れていれば success=False を返し、
  Lambda は反応を skip する
"""
import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import boto3
from strands import Agent
from strands.models import BedrockModel

from prompts import (
    CHARACTER_SYSTEM_PROMPT,
    REACT_SYSTEM_PROMPT,
    REACT_USER_TEMPLATE,
    REPLY_USER_TEMPLATE,
    VALID_EMOTION_KEYS,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "moonshotai.kimi-k2.5"  # 東京 In-Region。Grok 4.6 はアカウント提供制限で不可（2026-09-12、サポート問い合わせ中）
DEFAULT_REGION = "ap-northeast-1"
# Reasoning が出力枠を消費する可能性があるため Lambda 側の 140 字制限より大きく取る
RESPONSE_MAX_TOKENS = 1024
RESPONSE_TEMPERATURE = 0.7

REACT_ACTIONS = frozenset({"post", "skip"})

# 環境変数（Runtime の EnvironmentVariables で注入）
MODEL_ID = os.environ.get("BRAIN_MODEL_ID", DEFAULT_MODEL_ID)
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", DEFAULT_REGION)
OSHI_MEMORY_ID = os.environ.get("OSHI_MEMORY_ID", "")  # 推しの記憶（AgentCore Memory）。空なら記憶なし
OSHI_ACTOR_ID = os.environ.get("OSHI_ACTOR_ID", "")    # Memory の actorId（推しの X ユーザー名）

# retrieve する件数（facts は本人の出来事・事実、preferences は本人の好み）
FACTS_TOP_K = 3
PREFERENCES_TOP_K = 2
NO_MEMORIES = "（なし）"

# ファン視点への誤抽出（「ユーザーは…閲覧・転載…」）は除外する（設計書 §10-11）
_FAN_VIEW_PREFIX = "ユーザーは"
_FAN_VIEW_WORDS = ("閲覧", "転載", "運営")
# 体調・睡眠など生活の細部（設計書 v19 のタイプ E）は渡さない。プロンプトの指示だけでは本文に出た（2026-09-25 のローカル確認）。
# 出来事と混ざったレコードも丸ごと落とす（取りこぼしより、監視しているような文面を避ける方を優先）
_PRIVATE_LIFE_WORDS = ("眠", "寝", "睡眠", "起床", "目覚まし", "体調", "風邪", "発熱", "熱が", "病院", "通院", "怪我", "ケガ")

_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


class ReactFormatError(ValueError):
    """react の出力が JSON 提案の形になっていない"""


_memory_client = None


def _get_memory_client():
    """AgentCore Memory のデータプレーンクライアント（コンテナ内で使い回す）"""
    global _memory_client
    if _memory_client is None:
        _memory_client = boto3.client("bedrock-agentcore", region_name=BEDROCK_REGION)
    return _memory_client


def _is_private_life(text: str) -> bool:
    return any(word in text for word in _PRIVATE_LIFE_WORDS)


def _is_fan_view(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(_FAN_VIEW_PREFIX) and any(word in stripped for word in _FAN_VIEW_WORDS)


def _preference_text(raw: str) -> Optional[str]:
    """preferences のレコード（{"context", "preference", ...} の JSON）から本人の好みの 1 文を取り出す"""
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None if _is_fan_view(raw) else raw.strip()
    if not isinstance(parsed, dict):
        return None
    if _is_fan_view(str(parsed.get("context", ""))):
        return None
    preference = parsed.get("preference")
    if not isinstance(preference, str) or not preference.strip() or _is_private_life(preference):
        return None
    return preference.strip()


def _retrieve(namespace_kind: str, query: str, top_k: int) -> List[str]:
    response = _get_memory_client().retrieve_memory_records(
        memoryId=OSHI_MEMORY_ID,
        namespace=f"/oshi/{OSHI_ACTOR_ID}/{namespace_kind}/",
        searchCriteria={"searchQuery": query, "topK": top_k},
    )
    return [
        record.get("content", {}).get("text", "")
        for record in response.get("memoryRecordSummaries", [])
    ]


def recall_oshi_memory(query: str) -> Tuple[List[str], bool]:
    """
    推しの記憶を retrieve して、user message に載せる行のリストを返す

    MemoryClient.retrieve_memories は ClientError を握りつぶして [] を返すので使わず、
    データプレーン API を直接呼ぶ（失敗を ok=False で呼び出し側に知らせるため）。

    Returns:
        (行のリスト, ok)。Memory 未設定なら ([], True)、取得失敗なら ([], False)
    """
    if not OSHI_MEMORY_ID or not OSHI_ACTOR_ID or not query.strip():
        return [], True
    try:
        facts = [
            t.strip() for t in _retrieve("facts", query, FACTS_TOP_K)
            if t.strip() and not _is_fan_view(t) and not _is_private_life(t)
        ]
        preferences = [
            text for text in (_preference_text(t) for t in _retrieve("preferences", query, PREFERENCES_TOP_K))
            if text
        ]
    except Exception:  # noqa: BLE001 — 記憶は補助。取れなくても反応は作る
        logger.exception("recall_oshi_memory failed")
        return [], False

    lines: List[str] = []
    for text in facts + [f"好み: {p}" for p in preferences]:
        if text not in lines:
            lines.append(text)
    return lines, True


def _make_agent(
    system_prompt: Optional[str],
    temperature: float,
    max_tokens: int,
) -> Agent:
    """使い捨ての Agent を生成する（履歴なし・ツールなし・コールバックなし）"""
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=BEDROCK_REGION,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return Agent(model=model, system_prompt=system_prompt, callback_handler=None)


def _run(agent: Agent, user_message: str) -> str:
    result = agent(user_message)
    return str(result).strip()


def _parse_json_object(text: str) -> Dict[str, Any]:
    """
    モデル出力から JSON オブジェクトを取り出す

    コードフェンスや前置きが混ざっても、最初の "{" から最後の "}" までを読む。
    """
    stripped = _CODE_FENCE.sub("", text)
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        raise ReactFormatError(f"no JSON object in output: {text[:120]!r}")
    try:
        parsed = json.loads(stripped[start:end + 1])
    except ValueError as e:
        raise ReactFormatError(f"invalid JSON in output: {e}: {text[:120]!r}") from e
    if not isinstance(parsed, dict):
        raise ReactFormatError(f"JSON output is not an object: {text[:120]!r}")
    return parsed


def _validate_reaction(raw: Dict[str, Any]) -> Dict[str, Any]:
    """react の提案を {action, text, emotion_key, reason} に正規化する（値域の検証は最小限）"""
    action = str(raw.get("action", "")).strip().lower()
    if action not in REACT_ACTIONS:
        raise ReactFormatError(f"invalid action: {raw.get('action')!r}")

    text = raw.get("text")
    text = text.strip() if isinstance(text, str) else ""
    if action == "post" and not text:
        raise ReactFormatError("action=post but text is empty")

    emotion_key = raw.get("emotion_key")
    emotion_key = emotion_key.strip().lower() if isinstance(emotion_key, str) else "none"
    if emotion_key not in VALID_EMOTION_KEYS:
        # 感情キーは補助情報なので、未知の値は none に丸めて提案自体は通す
        if emotion_key != "none":
            logger.warning("react returned unknown emotion_key=%r; treating as none", emotion_key)
        emotion_key = "none"

    reason = raw.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""

    return {"action": action, "text": text, "emotion_key": emotion_key, "reason": reason}


def react(
    post_content: str,
    posted_at: str,
    now: str,
    publish_at: str,
    post_type: str = "oshi",
) -> Dict[str, Any]:
    """
    推し／グループの投稿への反応を JSON 提案で返す

    Args:
        post_content: 投稿本文
        posted_at: 投稿時刻（Lambda が整形した JST 表記）
        now: 現在時刻（同上）
        publish_at: 公開予定時刻（次の Buffer 予約枠、同上）
        post_type: "oshi" または "group"

    Returns:
        {action, text, emotion_key, reason, memory_count}。memory_count は注入した記憶の件数（取得失敗は -1）
    """
    memories, recalled = recall_oshi_memory(post_content)
    agent = _make_agent(REACT_SYSTEM_PROMPT, RESPONSE_TEMPERATURE, RESPONSE_MAX_TOKENS)
    user_message = REACT_USER_TEMPLATE.format(
        now=now,
        posted_at=posted_at,
        publish_at=publish_at,
        memories="\n".join(f"- {line}" for line in memories) if memories else NO_MEMORIES,
        post_content=post_content,
    )
    output = _run(agent, user_message)
    reaction = _validate_reaction(_parse_json_object(output))
    reaction["memory_count"] = len(memories) if recalled else -1
    return reaction


def reply_response(reply_text: str, reply_username: str, bot_tweet_text: str) -> str:
    """許可ユーザーからのリプライへの応答文を生成する"""
    agent = _make_agent(CHARACTER_SYSTEM_PROMPT, RESPONSE_TEMPERATURE, RESPONSE_MAX_TOKENS)
    user_message = REPLY_USER_TEMPLATE.format(
        username=reply_username,
        bot_tweet_text=bot_tweet_text,
        reply_text=reply_text,
    )
    return _run(agent, user_message)


TASKS: Dict[str, Callable[..., Union[str, Dict[str, Any]]]] = {
    "react": react,
    "reply_response": reply_response,
}


def handle(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lambda からのペイロードを処理する

    payload: {"task": <TASKS のキー>, "input": {<タスク関数のキーワード引数>}}
    returns: {"success": true, "text": ..., "model_id": ...}      文字列を返すタスク
             {"success": true, "result": {...}, "model_id": ...}  JSON 提案を返すタスク（react）
             {"success": false, "error": ..., "model_id": ...}
    """
    task = payload.get("task")
    task_input = payload.get("input") or {}
    func = TASKS.get(task) if isinstance(task, str) else None
    if func is None:
        return {"success": False, "error": f"unknown task: {task!r}", "model_id": MODEL_ID}
    if not isinstance(task_input, dict):
        return {"success": False, "error": "input must be an object", "model_id": MODEL_ID}

    try:
        output = func(**task_input)
        if isinstance(output, dict):
            logger.info(
                "brain task=%s model=%s action=%s chars=%d memories=%s",
                task, MODEL_ID, output.get("action"), len(output.get("text", "")), output.get("memory_count"),
            )
            return {"success": True, "result": output, "model_id": MODEL_ID}
        logger.info("brain task=%s model=%s chars=%d", task, MODEL_ID, len(output))
        return {"success": True, "text": output, "model_id": MODEL_ID}
    except TypeError as e:
        # 引数の不足・過剰
        return {"success": False, "error": f"invalid input for {task}: {e}", "model_id": MODEL_ID}
    except Exception as e:  # noqa: BLE001 — Runtime 内では握りつぶして success=False を返す
        logger.exception("brain task=%s failed", task)
        return {"success": False, "error": f"{type(e).__name__}: {e}", "model_id": MODEL_ID}
