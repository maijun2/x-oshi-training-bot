"""
BrainClient — 頭脳（AgentCore Runtime `imomaru_brain`）の呼び出し

Lambda 1 invocation につき 1 つの runtimeSessionId を使い回し、Runtime 側の
microVM をウォームのまま複数タスク（投稿ごとの応答生成・感情分類・リプライ応答）に使う。
Runtime 側の Agent はリクエストごとに使い捨てなので、セッションを共有しても
会話履歴は混ざらない（agent/brain.py 参照）。

失敗時の扱い:
- ここでは例外を投げる（BrainError）。フォールバック（Haiku 直呼び）は AIGenerator 側の責務
- boto3 の自動リトライは無効。同じ生成を二重に走らせないため
"""
import json
import logging
import uuid
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

DEFAULT_REGION = "ap-northeast-1"
DEFAULT_READ_TIMEOUT = 90
DEFAULT_CONNECT_TIMEOUT = 10
SESSION_ID_PREFIX = "imomaru-"  # 接頭辞 + uuid4(36 文字) = 44 文字（Runtime の要件は 33 文字以上）


class BrainError(Exception):
    """頭脳の呼び出しに失敗した（通信・Runtime 側エラー・不正なレスポンス）"""


class BrainClient:
    """AgentCore Runtime に {"task", "input"} を送り {"success", "text"|"error", "model_id"} を受け取る"""

    def __init__(
        self,
        runtime_arn: str,
        region: str = DEFAULT_REGION,
        client: Optional[Any] = None,
        read_timeout: int = DEFAULT_READ_TIMEOUT,
    ):
        if not runtime_arn:
            raise ValueError("runtime_arn is required")
        self._runtime_arn = runtime_arn
        self._session_id = f"{SESSION_ID_PREFIX}{uuid.uuid4()}"
        self._client = client or boto3.client(
            "bedrock-agentcore",
            region_name=region,
            config=Config(
                read_timeout=read_timeout,
                connect_timeout=DEFAULT_CONNECT_TIMEOUT,
                retries={"max_attempts": 1},
            ),
        )

    @property
    def session_id(self) -> str:
        return self._session_id

    def invoke(self, task: str, task_input: Dict[str, Any]) -> str:
        """
        タスクを頭脳に依頼し、生成テキストを返す

        Raises:
            BrainError: 呼び出し失敗、Runtime が success=false を返した、レスポンスが解釈不能
        """
        payload = json.dumps({"task": task, "input": task_input}, ensure_ascii=False).encode("utf-8")
        try:
            response = self._client.invoke_agent_runtime(
                agentRuntimeArn=self._runtime_arn,
                runtimeSessionId=self._session_id,
                qualifier="DEFAULT",
                payload=payload,
            )
            raw = _read_response_body(response)
        except BrainError:
            raise
        except Exception as e:  # botocore の各種例外・ネットワーク
            raise BrainError(f"invoke failed for task={task}: {type(e).__name__}: {e}") from e

        try:
            body = json.loads(raw)
        except (TypeError, ValueError) as e:
            raise BrainError(f"non-JSON response for task={task}: {raw[:200]!r}") from e

        if not isinstance(body, dict) or not body.get("success"):
            error = body.get("error") if isinstance(body, dict) else body
            raise BrainError(f"brain returned failure for task={task}: {error}")

        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            raise BrainError(f"brain returned empty text for task={task}")

        logger.info(
            f"Brain task={task} model={body.get('model_id')} chars={len(text)} session={self._session_id}"
        )
        return text


def _read_response_body(response: Dict[str, Any]) -> str:
    """
    invoke_agent_runtime のレスポンスボディを文字列にする

    バイナリチャンクを全て結合してからデコードし、マルチバイト文字の途中で
    チャンクが切れる問題を避ける。text/event-stream の場合は "data: " を剥がす。
    """
    content_type = response.get("contentType", "") or ""
    stream = response.get("response")
    if stream is None:
        raise BrainError("response body is missing")

    chunks = []
    if hasattr(stream, "iter_chunks"):
        for chunk in stream.iter_chunks():
            chunks.append(chunk[0] if isinstance(chunk, tuple) else chunk)
    elif hasattr(stream, "read"):
        chunks.append(stream.read())
    else:
        for chunk in stream:
            chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))

    decoded = b"".join(chunks).decode("utf-8", errors="replace")
    if "text/event-stream" in content_type:
        lines = [line[6:] if line.startswith("data: ") else line for line in decoded.splitlines() if line.strip()]
        return "\n".join(lines)
    return decoded
