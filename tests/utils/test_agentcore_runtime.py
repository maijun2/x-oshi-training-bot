"""
AgentCore Runtime 呼び出しモジュールのユニットテスト

invoke_agent_runtime, _read_streaming_response, _handle_error を検証
"""
import json
import io
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.hokuhoku_imomaru_bot.utils.agentcore_runtime import (
    invoke_agent_runtime,
    _read_streaming_response,
    _handle_error,
)


class TestInvokeAgentRuntime:
    """invoke_agent_runtime関数のテスト"""

    def test_returns_error_when_arn_not_set(self):
        """AGENTCORE_RUNTIME_ARN未設定時にエラーを返すことを確認"""
        with patch(
            "src.hokuhoku_imomaru_bot.utils.agentcore_runtime.AGENTCORE_RUNTIME_ARN",
            "",
        ):
            result = invoke_agent_runtime(prompt="test")

        assert result["success"] is False
        assert "AGENTCORE_RUNTIME_ARN" in result["error"]
        assert result["response"] == ""
        assert result["session_id"] is None

    def _make_mock_client(self, response_bytes=b"ok"):
        """テスト用モッククライアントを作成"""
        mock_client = Mock()
        mock_stream = io.BytesIO(response_bytes)
        mock_client.invoke_agent_runtime.return_value = {
            "contentType": "text/plain",
            "response": mock_stream,
        }
        # 例外クラスをBaseException継承で定義
        mock_client.exceptions.ThrottlingException = type(
            "ThrottlingException", (Exception,), {}
        )
        mock_client.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )
        mock_client.exceptions.AccessDeniedException = type(
            "AccessDeniedException", (Exception,), {}
        )
        mock_client.exceptions.ValidationException = type(
            "ValidationException", (Exception,), {}
        )
        return mock_client

    def test_success_with_mock_client(self):
        """正常系: モッククライアントで成功レスポンスを返すことを確認"""
        mock_client = self._make_mock_client("分析結果ｲﾓ🍠".encode("utf-8"))

        with patch(
            "src.hokuhoku_imomaru_bot.utils.agentcore_runtime.AGENTCORE_RUNTIME_ARN",
            "arn:aws:bedrock-agentcore:ap-northeast-1:123456:runtime/test",
        ):
            result = invoke_agent_runtime(
                prompt="テスト",
                client=mock_client,
                session_id="test-session",
            )

        assert result["success"] is True
        assert "分析結果" in result["response"]
        assert result["session_id"] == "test-session"
        assert result["error"] is None

    def test_passes_context_in_payload(self):
        """contextがペイロードに含まれることを確認"""
        mock_client = self._make_mock_client(b"ok")
        context = {"request_type": "ego_search", "user_id": "12345"}

        with patch(
            "src.hokuhoku_imomaru_bot.utils.agentcore_runtime.AGENTCORE_RUNTIME_ARN",
            "arn:aws:bedrock-agentcore:ap-northeast-1:123456:runtime/test",
        ):
            invoke_agent_runtime(
                prompt="テスト",
                context=context,
                client=mock_client,
            )

        call_args = mock_client.invoke_agent_runtime.call_args
        payload = json.loads(call_args.kwargs["payload"].decode("utf-8"))
        assert payload["context"]["request_type"] == "ego_search"
        assert payload["context"]["user_id"] == "12345"

    def test_auto_generates_session_id(self):
        """session_id未指定時に自動生成されることを確認"""
        mock_client = self._make_mock_client(b"ok")

        with patch(
            "src.hokuhoku_imomaru_bot.utils.agentcore_runtime.AGENTCORE_RUNTIME_ARN",
            "arn:aws:bedrock-agentcore:ap-northeast-1:123456:runtime/test",
        ):
            result = invoke_agent_runtime(prompt="テスト", client=mock_client)

        assert result["session_id"].startswith("imomaru-")

    def test_throttling_exception(self):
        """ThrottlingException時にエラーレスポンスを返すことを確認"""
        mock_client = self._make_mock_client()
        mock_client.invoke_agent_runtime.side_effect = (
            mock_client.exceptions.ThrottlingException("Rate exceeded")
        )

        with patch(
            "src.hokuhoku_imomaru_bot.utils.agentcore_runtime.AGENTCORE_RUNTIME_ARN",
            "arn:aws:bedrock-agentcore:ap-northeast-1:123456:runtime/test",
        ):
            result = invoke_agent_runtime(prompt="テスト", client=mock_client)

        assert result["success"] is False
        assert "ThrottlingException" in result["error"]

    def test_resource_not_found_exception(self):
        """ResourceNotFoundException時にエラーレスポンスを返すことを確認"""
        mock_client = self._make_mock_client()
        mock_client.invoke_agent_runtime.side_effect = (
            mock_client.exceptions.ResourceNotFoundException("Not found")
        )

        with patch(
            "src.hokuhoku_imomaru_bot.utils.agentcore_runtime.AGENTCORE_RUNTIME_ARN",
            "arn:aws:bedrock-agentcore:ap-northeast-1:123456:runtime/test",
        ):
            result = invoke_agent_runtime(prompt="テスト", client=mock_client)

        assert result["success"] is False
        assert "ResourceNotFoundException" in result["error"]

    def test_access_denied_exception(self):
        """AccessDeniedException時にエラーレスポンスを返すことを確認"""
        mock_client = self._make_mock_client()
        mock_client.invoke_agent_runtime.side_effect = (
            mock_client.exceptions.AccessDeniedException("Denied")
        )

        with patch(
            "src.hokuhoku_imomaru_bot.utils.agentcore_runtime.AGENTCORE_RUNTIME_ARN",
            "arn:aws:bedrock-agentcore:ap-northeast-1:123456:runtime/test",
        ):
            result = invoke_agent_runtime(prompt="テスト", client=mock_client)

        assert result["success"] is False
        assert "AccessDeniedException" in result["error"]

    def test_validation_exception(self):
        """ValidationException時にエラーレスポンスを返すことを確認"""
        mock_client = self._make_mock_client()
        mock_client.invoke_agent_runtime.side_effect = (
            mock_client.exceptions.ValidationException("Invalid")
        )

        with patch(
            "src.hokuhoku_imomaru_bot.utils.agentcore_runtime.AGENTCORE_RUNTIME_ARN",
            "arn:aws:bedrock-agentcore:ap-northeast-1:123456:runtime/test",
        ):
            result = invoke_agent_runtime(prompt="テスト", client=mock_client)

        assert result["success"] is False
        assert "ValidationException" in result["error"]

    def test_generic_exception(self):
        """予期しない例外時にエラーレスポンスを返すことを確認"""
        mock_client = self._make_mock_client()
        mock_client.invoke_agent_runtime.side_effect = ConnectionError("Network error")

        with patch(
            "src.hokuhoku_imomaru_bot.utils.agentcore_runtime.AGENTCORE_RUNTIME_ARN",
            "arn:aws:bedrock-agentcore:ap-northeast-1:123456:runtime/test",
        ):
            result = invoke_agent_runtime(prompt="テスト", client=mock_client)

        assert result["success"] is False
        assert "ConnectionError" in result["error"]


class TestReadStreamingResponse:
    """_read_streaming_response関数のテスト"""

    def test_read_from_stream_with_read_method(self):
        """read()メソッドを持つストリームから読み取れることを確認"""
        stream = io.BytesIO("テスト結果".encode("utf-8"))
        response = {"contentType": "text/plain", "response": stream}

        result = _read_streaming_response(response)

        assert result == "テスト結果"

    def test_read_from_iter_chunks(self):
        """iter_chunks()メソッドを持つストリームから読み取れることを確認"""
        mock_stream = Mock()
        mock_stream.iter_chunks.return_value = [
            "こんにちは".encode("utf-8"),
            "世界".encode("utf-8"),
        ]
        # hasattr チェック用
        mock_stream.read = Mock()
        response = {"contentType": "text/plain", "response": mock_stream}

        result = _read_streaming_response(response)

        assert result == "こんにちは世界"

    def test_read_from_iter_chunks_with_tuples(self):
        """iter_chunks()がタプルを返す場合に対応できることを確認"""
        mock_stream = Mock()
        mock_stream.iter_chunks.return_value = [
            ("チャンク1".encode("utf-8"), {}),
            ("チャンク2".encode("utf-8"), {}),
        ]
        response = {"contentType": "text/plain", "response": mock_stream}

        result = _read_streaming_response(response)

        assert result == "チャンク1チャンク2"

    def test_read_event_stream_format(self):
        """text/event-stream形式のレスポンスを正しくパースすることを確認"""
        stream_data = "data: 行1\ndata: 行2\n\n"
        stream = io.BytesIO(stream_data.encode("utf-8"))
        response = {"contentType": "text/event-stream", "response": stream}

        result = _read_streaming_response(response)

        assert "行1" in result
        assert "行2" in result
        assert "data: " not in result

    def test_read_none_stream(self):
        """responseがNoneの場合に空文字を返すことを確認"""
        response = {"contentType": "text/plain", "response": None}

        result = _read_streaming_response(response)

        assert result == ""

    def test_read_multibyte_across_chunks(self):
        """マルチバイト文字がチャンク境界をまたぐ場合に正しくデコードされることを確認"""
        full_text = "日本語テスト🍠"
        encoded = full_text.encode("utf-8")
        # 途中で分割
        mid = len(encoded) // 2
        chunk1 = encoded[:mid]
        chunk2 = encoded[mid:]

        mock_stream = Mock()
        mock_stream.iter_chunks.return_value = [chunk1, chunk2]
        response = {"contentType": "text/plain", "response": mock_stream}

        result = _read_streaming_response(response)

        assert result == full_text

    def test_read_from_iterable_bytes(self):
        """バイト列のイテラブルから読み取れることを確認"""
        mock_stream = Mock()
        # iter_chunks も read も持たない → __iter__ にフォールバック
        del mock_stream.iter_chunks
        del mock_stream.read
        mock_stream.__iter__ = Mock(
            return_value=iter([b"hello", b" ", b"world"])
        )
        response = {"contentType": "text/plain", "response": mock_stream}

        result = _read_streaming_response(response)

        assert result == "hello world"

    def test_read_from_iterable_non_bytes(self):
        """非バイト列のイテラブルから読み取れることを確認"""
        mock_stream = Mock()
        del mock_stream.iter_chunks
        del mock_stream.read
        mock_stream.__iter__ = Mock(return_value=iter(["text1", "text2"]))
        response = {"contentType": "text/plain", "response": mock_stream}

        result = _read_streaming_response(response)

        assert "text1" in result
        assert "text2" in result


class TestHandleError:
    """_handle_error関数のテスト"""

    def test_returns_error_dict(self):
        """エラー辞書を返すことを確認"""
        error = ValueError("test error")
        result = _handle_error(error, "ValueError", "session-123")

        assert result["success"] is False
        assert result["response"] == ""
        assert result["session_id"] == "session-123"
        assert "ValueError" in result["error"]
        assert "test error" in result["error"]

    def test_preserves_session_id(self):
        """セッションIDが保持されることを確認"""
        error = RuntimeError("fail")
        result = _handle_error(error, "RuntimeError", "my-session")

        assert result["session_id"] == "my-session"
