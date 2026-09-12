"""
いも丸の頭脳（フェーズ2a）

Strands Agent ＋ Bedrock（既定: moonshotai.kimi-k2.5。BRAIN_MODEL_ID で差し替え可）で、Lambda から依頼された 3 タスクを処理する。
- oshi_response:    推し／グループの投稿への応答文
- reply_response:   許可ユーザーからのリプライへの応答文
- classify_emotion: 応答文の感情キー分類

方針:
- Agent はリクエストごとに生成する（Runtime のセッションを Lambda 1 回分で使い回すため、
  会話履歴が投稿間で混ざらないようにする）
- キャラクター定義は system prompt、反応対象は user message に分ける（設計書 §10-8）。
  フェーズ3 では推しの記憶（Memory の retrieve 結果）を user 側に足す
- 140 字への切り詰めや感情キーの検証は Lambda 側（AIGenerator）が従来どおり行う
"""
import logging
import os
from typing import Any, Callable, Dict, Optional

from strands import Agent
from strands.models import BedrockModel

from prompts import (
    CHARACTER_SYSTEM_PROMPT,
    EMOTION_CLASSIFICATION_PROMPT,
    OSHI_POST_USER_TEMPLATE,
    REPLY_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "moonshotai.kimi-k2.5"  # 東京 In-Region。Grok 4.6 はアカウント提供制限で不可（2026-09-12、サポート問い合わせ中）
DEFAULT_REGION = "ap-northeast-1"
# Reasoning が出力枠を消費する可能性があるため Lambda 側の 140 字制限より大きく取る
RESPONSE_MAX_TOKENS = 1024
RESPONSE_TEMPERATURE = 0.7
CLASSIFY_MAX_TOKENS = 64
CLASSIFY_TEMPERATURE = 0.0

# 環境変数（Runtime の EnvironmentVariables で注入）
MODEL_ID = os.environ.get("BRAIN_MODEL_ID", DEFAULT_MODEL_ID)
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", DEFAULT_REGION)


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


def oshi_response(post_content: str, post_type: str = "oshi") -> str:
    """推し／グループの投稿への応答文を生成する"""
    agent = _make_agent(CHARACTER_SYSTEM_PROMPT, RESPONSE_TEMPERATURE, RESPONSE_MAX_TOKENS)
    return _run(agent, OSHI_POST_USER_TEMPLATE.format(post_content=post_content))


def reply_response(reply_text: str, reply_username: str, bot_tweet_text: str) -> str:
    """許可ユーザーからのリプライへの応答文を生成する"""
    agent = _make_agent(CHARACTER_SYSTEM_PROMPT, RESPONSE_TEMPERATURE, RESPONSE_MAX_TOKENS)
    user_message = REPLY_USER_TEMPLATE.format(
        username=reply_username,
        bot_tweet_text=bot_tweet_text,
        reply_text=reply_text,
    )
    return _run(agent, user_message)


def classify_emotion(response_text: str) -> str:
    """応答文の感情キーを返す（検証は Lambda 側）。system prompt は使わない"""
    agent = _make_agent(None, CLASSIFY_TEMPERATURE, CLASSIFY_MAX_TOKENS)
    return _run(agent, EMOTION_CLASSIFICATION_PROMPT.format(response_text=response_text)).lower()


TASKS: Dict[str, Callable[..., str]] = {
    "oshi_response": oshi_response,
    "reply_response": reply_response,
    "classify_emotion": classify_emotion,
}


def handle(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lambda からのペイロードを処理する

    payload: {"task": <TASKS のキー>, "input": {<タスク関数のキーワード引数>}}
    returns: {"success": true, "text": ..., "model_id": ...}
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
        text = func(**task_input)
        logger.info("brain task=%s model=%s chars=%d", task, MODEL_ID, len(text))
        return {"success": True, "text": text, "model_id": MODEL_ID}
    except TypeError as e:
        # 引数の不足・過剰
        return {"success": False, "error": f"invalid input for {task}: {e}", "model_id": MODEL_ID}
    except Exception as e:  # noqa: BLE001 — Runtime 内では握りつぶして success=False を返す
        logger.exception("brain task=%s failed", task)
        return {"success": False, "error": f"{type(e).__name__}: {e}", "model_id": MODEL_ID}
