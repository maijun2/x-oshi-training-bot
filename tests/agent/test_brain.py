"""
頭脳（agent/brain.py）のユニットテスト

Strands の Agent / BedrockModel をモックし、Bedrock を呼ばずに
- system / user の分離（設計書 §10-8）
- タスクごとの推論パラメータ
- handle() のディスパッチとエラー整形
を検証する。
"""
from unittest.mock import MagicMock, patch

import pytest

import brain
from prompts import (
    CHARACTER_SYSTEM_PROMPT,
    EMOTION_CLASSIFICATION_PROMPT,
    OSHI_POST_USER_TEMPLATE,
    REPLY_USER_TEMPLATE,
)


@pytest.fixture
def strands(monkeypatch):
    """Agent / BedrockModel を差し替え、生成された Agent の呼び出しを記録する"""
    agent_instance = MagicMock(name="agent_instance")
    agent_instance.return_value = "  応答ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる  "
    agent_cls = MagicMock(name="Agent", return_value=agent_instance)
    model_cls = MagicMock(name="BedrockModel")
    monkeypatch.setattr(brain, "Agent", agent_cls)
    monkeypatch.setattr(brain, "BedrockModel", model_cls)
    return agent_cls, agent_instance, model_cls


class TestTasks:
    def test_oshi_response_separates_system_and_user(self, strands):
        agent_cls, agent_instance, model_cls = strands

        text = brain.oshi_response("今日はライブでした", post_type="oshi")

        assert text == "応答ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる"
        # キャラクター定義は system、投稿本文は user
        assert agent_cls.call_args.kwargs["system_prompt"] == CHARACTER_SYSTEM_PROMPT
        agent_instance.assert_called_once_with(OSHI_POST_USER_TEMPLATE.format(post_content="今日はライブでした"))
        assert "今日はライブでした" not in CHARACTER_SYSTEM_PROMPT
        # 履歴・ツールを持たない使い捨て Agent
        assert agent_cls.call_args.kwargs["callback_handler"] is None
        assert "tools" not in agent_cls.call_args.kwargs

    def test_oshi_response_model_params(self, strands):
        _, _, model_cls = strands
        brain.oshi_response("x")
        kwargs = model_cls.call_args.kwargs
        assert kwargs["model_id"] == brain.MODEL_ID
        assert kwargs["region_name"] == brain.BEDROCK_REGION
        assert kwargs["temperature"] == brain.RESPONSE_TEMPERATURE
        assert kwargs["max_tokens"] == brain.RESPONSE_MAX_TOKENS

    def test_reply_response_fills_template(self, strands):
        _, agent_instance, _ = strands
        brain.reply_response(reply_text="かわいい", reply_username="fan_taro", bot_tweet_text="元投稿")
        agent_instance.assert_called_once_with(
            REPLY_USER_TEMPLATE.format(username="fan_taro", bot_tweet_text="元投稿", reply_text="かわいい")
        )

    def test_classify_emotion_is_deterministic_and_lowercased(self, strands):
        agent_cls, agent_instance, model_cls = strands
        agent_instance.return_value = "  JOY\n"

        assert brain.classify_emotion("嬉しいｲﾓ🍠") == "joy"
        assert agent_cls.call_args.kwargs["system_prompt"] is None
        assert model_cls.call_args.kwargs["temperature"] == 0.0
        assert model_cls.call_args.kwargs["max_tokens"] == brain.CLASSIFY_MAX_TOKENS
        agent_instance.assert_called_once_with(EMOTION_CLASSIFICATION_PROMPT.format(response_text="嬉しいｲﾓ🍠"))

    def test_new_agent_per_request(self, strands):
        agent_cls, _, _ = strands
        brain.oshi_response("a")
        brain.oshi_response("b")
        assert agent_cls.call_count == 2


class TestHandle:
    def test_dispatch_success(self, strands):
        result = brain.handle({"task": "oshi_response", "input": {"post_content": "x", "post_type": "oshi"}})
        assert result == {
            "success": True,
            "text": "応答ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる",
            "model_id": brain.MODEL_ID,
        }

    def test_unknown_task(self, strands):
        result = brain.handle({"task": "bogus", "input": {}})
        assert result["success"] is False
        assert "unknown task" in result["error"]

    def test_missing_task(self, strands):
        assert brain.handle({})["success"] is False

    def test_input_must_be_object(self, strands):
        result = brain.handle({"task": "oshi_response", "input": "x"})
        assert result["success"] is False
        assert "object" in result["error"]

    def test_invalid_arguments(self, strands):
        result = brain.handle({"task": "reply_response", "input": {"reply_text": "x"}})
        assert result["success"] is False
        assert "invalid input" in result["error"]

    def test_model_exception_is_wrapped(self, strands):
        _, agent_instance, _ = strands
        agent_instance.side_effect = RuntimeError("bedrock down")
        result = brain.handle({"task": "oshi_response", "input": {"post_content": "x"}})
        assert result["success"] is False
        assert "RuntimeError: bedrock down" == result["error"]
        assert result["model_id"] == brain.MODEL_ID


class TestMain:
    def test_entrypoint_delegates_to_handle(self, strands):
        import main

        with patch.object(main.brain, "handle", return_value={"success": True}) as h:
            assert main.invoke({"task": "oshi_response", "input": {}}) == {"success": True}
            h.assert_called_once_with({"task": "oshi_response", "input": {}})
