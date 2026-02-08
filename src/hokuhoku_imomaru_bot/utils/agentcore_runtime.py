"""
AgentCore Runtime 呼び出しモジュール

Amazon Bedrock AgentCore Runtime にデプロイされた Supervisor Agent を
呼び出すためのユーティリティを提供します。
"""
import json
import os
import uuid
from typing import Any, Dict, Optional

import boto3

from .logging import log_event, EventType, LogLevel

# 環境変数
AGENTCORE_RUNTIME_ARN = os.environ.get("AGENTCORE_RUNTIME_ARN", "")

# デフォルトタイムアウト（秒）
DEFAULT_TIMEOUT = 60


def invoke_agent_runtime(
    prompt: str,
    context: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    AgentCore Runtime の Supervisor Agent を呼び出す

    Args:
        prompt: エージェントへの自然言語の指示
        context: 追加コンテキスト情報（オプション）
        session_id: セッションID（省略時は自動生成）
        timeout: タイムアウト秒数
        client: boto3 bedrock-agentcore クライアント（テスト用DI）

    Returns:
        {
            "success": True/False,
            "response": "エージェントの応答テキスト",
            "session_id": "使用されたセッションID",
            "error": None or "エラーメッセージ"
        }
    """
    if not AGENTCORE_RUNTIME_ARN:
        return {
            "success": False,
            "response": "",
            "session_id": None,
            "error": "AGENTCORE_RUNTIME_ARN が設定されていません",
        }

    if session_id is None:
        session_id = f"imomaru-{uuid.uuid4()}"

    # ペイロードの構築
    payload_dict: Dict[str, Any] = {"prompt": prompt}
    if context:
        payload_dict["context"] = context

    payload = json.dumps(payload_dict).encode()

    log_event(
        level=LogLevel.INFO,
        event_type=EventType.TIMELINE_CHECK,
        data={
            "action": "agentcore_invoke",
            "prompt_length": len(prompt),
            "has_context": context is not None,
            "session_id": session_id,
        },
        message=f"Invoking AgentCore Runtime: {prompt[:80]}...",
    )

    try:
        if client is None:
            config = boto3.session.Config(
                read_timeout=timeout,
                connect_timeout=10,
                retries={"max_attempts": 2},
            )
            client = boto3.client(
                "bedrock-agentcore",
                region_name="ap-northeast-1",
                config=config,
            )

        response = client.invoke_agent_runtime(
            agentRuntimeArn=AGENTCORE_RUNTIME_ARN,
            runtimeSessionId=session_id,
            payload=payload,
        )

        # ストリーミングレスポンスの処理
        response_text = _read_streaming_response(response)

        log_event(
            level=LogLevel.INFO,
            event_type=EventType.TIMELINE_CHECK,
            data={
                "action": "agentcore_response",
                "response_length": len(response_text),
                "session_id": session_id,
            },
            message="AgentCore Runtime response received",
        )

        return {
            "success": True,
            "response": response_text,
            "session_id": session_id,
            "error": None,
        }

    except client.exceptions.ThrottlingException as e:
        return _handle_error(e, "ThrottlingException", session_id)
    except client.exceptions.ResourceNotFoundException as e:
        return _handle_error(e, "ResourceNotFoundException", session_id)
    except client.exceptions.AccessDeniedException as e:
        return _handle_error(e, "AccessDeniedException", session_id)
    except client.exceptions.ValidationException as e:
        return _handle_error(e, "ValidationException", session_id)
    except Exception as e:
        return _handle_error(e, type(e).__name__, session_id)


def _read_streaming_response(response: Dict[str, Any]) -> str:
    """
    ストリーミングレスポンスを読み取って文字列に結合する

    バイナリチャンクを全て結合してからデコードすることで、
    マルチバイト文字（日本語等）の途中でチャンクが切れる問題を回避する。

    Args:
        response: invoke_agent_runtime のレスポンス

    Returns:
        結合されたレスポンステキスト
    """
    content_type = response.get("contentType", "")

    # まずバイナリとして全チャンクを結合
    raw_chunks = []
    stream = response.get("response")
    if stream is None:
        return ""

    if hasattr(stream, "iter_chunks"):
        for chunk in stream.iter_chunks():
            if isinstance(chunk, bytes):
                raw_chunks.append(chunk)
            elif isinstance(chunk, tuple):
                raw_chunks.append(chunk[0])
    elif hasattr(stream, "read"):
        raw_chunks.append(stream.read())
    else:
        for chunk in stream:
            if isinstance(chunk, bytes):
                raw_chunks.append(chunk)
            else:
                raw_chunks.append(str(chunk).encode("utf-8"))

    raw_data = b"".join(raw_chunks)
    decoded = raw_data.decode("utf-8", errors="replace")

    # text/event-stream の場合は "data: " プレフィックスを除去
    if "text/event-stream" in content_type:
        lines = []
        for line in decoded.splitlines():
            if line.startswith("data: "):
                lines.append(line[6:])
            elif line.strip():
                lines.append(line)
        return "\n".join(lines)

    return decoded


def _handle_error(
    error: Exception,
    error_type: str,
    session_id: str,
) -> Dict[str, Any]:
    """
    AgentCore Runtime 呼び出しエラーを処理

    Args:
        error: 発生した例外
        error_type: エラータイプ名
        session_id: セッションID

    Returns:
        エラーレスポンス辞書
    """
    log_event(
        level=LogLevel.ERROR,
        event_type=EventType.ERROR,
        data={
            "action": "agentcore_error",
            "error_type": error_type,
            "error_message": str(error),
            "session_id": session_id,
        },
        message=f"AgentCore Runtime error: {error_type} - {error}",
    )

    return {
        "success": False,
        "response": "",
        "session_id": session_id,
        "error": f"{error_type}: {error}",
    }
