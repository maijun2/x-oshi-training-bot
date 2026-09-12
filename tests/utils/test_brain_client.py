"""BrainClient のユニットテスト（boto3 はモック）"""
import io
import json
from unittest.mock import MagicMock

import pytest

from src.hokuhoku_imomaru_bot.utils.brain_client import BrainClient, BrainError, _read_response_body

ARN = "arn:aws:bedrock-agentcore:ap-northeast-1:123456789012:runtime/imomaru_brain-abc123"


def _response(body: dict | str, content_type: str = "application/json"):
    raw = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    stream = MagicMock()
    stream.iter_chunks.return_value = [raw.encode("utf-8")[:5], raw.encode("utf-8")[5:]]
    return {"contentType": content_type, "response": stream}


@pytest.fixture
def boto():
    return MagicMock()


@pytest.fixture
def client(boto):
    return BrainClient(runtime_arn=ARN, client=boto)


class TestInvoke:
    def test_success_returns_text(self, client, boto):
        boto.invoke_agent_runtime.return_value = _response(
            {"success": True, "text": "嬉しいｲﾓ🍠", "model_id": "moonshotai.kimi-k2.5"}
        )

        assert client.invoke("oshi_response", {"post_content": "x", "post_type": "oshi"}) == "嬉しいｲﾓ🍠"

        kwargs = boto.invoke_agent_runtime.call_args.kwargs
        assert kwargs["agentRuntimeArn"] == ARN
        assert kwargs["qualifier"] == "DEFAULT"
        assert json.loads(kwargs["payload"]) == {"task": "oshi_response", "input": {"post_content": "x", "post_type": "oshi"}}

    def test_session_id_is_reused_and_long_enough(self, client, boto):
        boto.invoke_agent_runtime.return_value = _response({"success": True, "text": "a"})
        client.invoke("oshi_response", {})
        boto.invoke_agent_runtime.return_value = _response({"success": True, "text": "b"})
        client.invoke("classify_emotion", {})

        sids = {c.kwargs["runtimeSessionId"] for c in boto.invoke_agent_runtime.call_args_list}
        assert len(sids) == 1
        assert len(sids.pop()) >= 33
        assert client.session_id.startswith("imomaru-")

    def test_new_client_gets_new_session(self, boto):
        assert BrainClient(ARN, client=boto).session_id != BrainClient(ARN, client=boto).session_id

    def test_multibyte_split_across_chunks(self, client, boto):
        boto.invoke_agent_runtime.return_value = _response({"success": True, "text": "甘木ジュリさん最高ｲﾓ🍠"})
        assert client.invoke("oshi_response", {}) == "甘木ジュリさん最高ｲﾓ🍠"

    def test_brain_failure_raises(self, client, boto):
        boto.invoke_agent_runtime.return_value = _response({"success": False, "error": "unknown task"})
        with pytest.raises(BrainError, match="unknown task"):
            client.invoke("bogus", {})

    def test_empty_text_raises(self, client, boto):
        boto.invoke_agent_runtime.return_value = _response({"success": True, "text": "   "})
        with pytest.raises(BrainError, match="empty text"):
            client.invoke("oshi_response", {})

    def test_non_json_raises(self, client, boto):
        boto.invoke_agent_runtime.return_value = _response("<html>oops</html>")
        with pytest.raises(BrainError, match="non-JSON"):
            client.invoke("oshi_response", {})

    def test_transport_exception_wrapped(self, client, boto):
        boto.invoke_agent_runtime.side_effect = RuntimeError("timeout")
        with pytest.raises(BrainError, match="RuntimeError: timeout"):
            client.invoke("oshi_response", {})

    def test_requires_arn(self, boto):
        with pytest.raises(ValueError):
            BrainClient("", client=boto)


class TestReadResponseBody:
    def test_read_interface(self):
        body = {"contentType": "application/json", "response": io.BytesIO(b'{"a":1}')}
        assert _read_response_body(body) == '{"a":1}'

    def test_event_stream_strips_data_prefix(self):
        stream = MagicMock()
        stream.iter_chunks.return_value = [b'data: {"success": true}\n\n']
        assert _read_response_body({"contentType": "text/event-stream", "response": stream}) == '{"success": true}'

    def test_missing_body(self):
        with pytest.raises(BrainError):
            _read_response_body({"contentType": "application/json"})
