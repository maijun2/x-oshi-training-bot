"""
頭脳（agent/brain.py）のユニットテスト

Strands の Agent / BedrockModel をモックし、Bedrock を呼ばずに
- system / user の分離（設計書 §10-8）
- react の JSON 提案のパースと検証
- 推しの記憶の retrieve と user message への注入（3a-read）
- handle() のディスパッチとエラー整形
を検証する。
"""
import json
from unittest.mock import MagicMock, patch

import pytest

import brain
from prompts import (
    CHARACTER_SYSTEM_PROMPT,
    REACT_SYSTEM_PROMPT,
    REACT_USER_TEMPLATE,
    REPLY_USER_TEMPLATE,
)

REACT_INPUT = {
    "post_content": "今日はライブでした",
    "posted_at": "2026-09-16(火) 01:42 JST",
    "now": "2026-09-16(火) 13:18 JST",
    "publish_at": "2026-09-16(火) 14:15 JST",
    "post_type": "oshi",
}
REACT_JSON = {
    "action": "post",
    "text": "ライブお疲れさまｲﾓ🍠\n\n#さつまいもの民 #びっくえんじぇる",
    "emotion_key": "cheer",
    "reason": "ライブの報告なので応援する",
}
# 記憶なし（strands fixture は Memory を無効化する）のときの react の戻り値
REACT_RESULT = {**REACT_JSON, "memory_count": 0}


@pytest.fixture
def strands(monkeypatch):
    """Agent / BedrockModel を差し替え、生成された Agent の呼び出しを記録する"""
    agent_instance = MagicMock(name="agent_instance")
    agent_instance.return_value = json.dumps(REACT_JSON, ensure_ascii=False)
    agent_cls = MagicMock(name="Agent", return_value=agent_instance)
    model_cls = MagicMock(name="BedrockModel")
    monkeypatch.setattr(brain, "Agent", agent_cls)
    monkeypatch.setattr(brain, "BedrockModel", model_cls)
    monkeypatch.setattr(brain, "OSHI_MEMORY_ID", "")
    monkeypatch.setattr(brain, "OSHI_ACTOR_ID", "")
    return agent_cls, agent_instance, model_cls


class TestReact:
    def test_separates_system_and_user(self, strands):
        agent_cls, agent_instance, model_cls = strands

        result = brain.react(**REACT_INPUT)

        assert result == REACT_RESULT
        # キャラクター定義と出力形式は system、投稿本文と時刻は user
        assert agent_cls.call_args.kwargs["system_prompt"] == REACT_SYSTEM_PROMPT
        expected_user = REACT_USER_TEMPLATE.format(
            now=REACT_INPUT["now"],
            posted_at=REACT_INPUT["posted_at"],
            publish_at=REACT_INPUT["publish_at"],
            memories=brain.NO_MEMORIES,
            post_content=REACT_INPUT["post_content"],
        )
        agent_instance.assert_called_once_with(expected_user)
        assert "今日はライブでした" not in REACT_SYSTEM_PROMPT
        assert "14:15" in expected_user and "01:42" in expected_user
        # 履歴・ツールを持たない使い捨て Agent
        assert agent_cls.call_args.kwargs["callback_handler"] is None
        assert "tools" not in agent_cls.call_args.kwargs

    def test_model_params(self, strands):
        _, _, model_cls = strands
        brain.react(**REACT_INPUT)
        kwargs = model_cls.call_args.kwargs
        assert kwargs["model_id"] == brain.MODEL_ID
        assert kwargs["region_name"] == brain.BEDROCK_REGION
        assert kwargs["temperature"] == brain.RESPONSE_TEMPERATURE
        assert kwargs["max_tokens"] == brain.RESPONSE_MAX_TOKENS

    def test_accepts_code_fence_and_preamble(self, strands):
        _, agent_instance, _ = strands
        agent_instance.return_value = "はい、こちらです\n```json\n" + json.dumps(REACT_JSON, ensure_ascii=False) + "\n```"
        assert brain.react(**REACT_INPUT) == REACT_RESULT

    def test_skip_allows_empty_text(self, strands):
        _, agent_instance, _ = strands
        agent_instance.return_value = '{"action": "SKIP", "text": "", "emotion_key": "none", "reason": "内容が読めない"}'
        result = brain.react(**REACT_INPUT)
        assert result == {"action": "skip", "text": "", "emotion_key": "none", "reason": "内容が読めない", "memory_count": 0}

    def test_post_requires_text(self, strands):
        _, agent_instance, _ = strands
        agent_instance.return_value = '{"action": "post", "text": "", "emotion_key": "joy"}'
        with pytest.raises(brain.ReactFormatError, match="text is empty"):
            brain.react(**REACT_INPUT)

    def test_invalid_action_is_rejected(self, strands):
        _, agent_instance, _ = strands
        agent_instance.return_value = '{"action": "maybe", "text": "x"}'
        with pytest.raises(brain.ReactFormatError, match="invalid action"):
            brain.react(**REACT_INPUT)

    def test_unknown_emotion_key_becomes_none(self, strands):
        _, agent_instance, _ = strands
        agent_instance.return_value = '{"action": "post", "text": "x", "emotion_key": "Happy!", "reason": 1}'
        result = brain.react(**REACT_INPUT)
        assert result["emotion_key"] == "none"
        assert result["reason"] == ""

    def test_missing_optional_keys(self, strands):
        _, agent_instance, _ = strands
        agent_instance.return_value = '{"action": "post", "text": "x"}'
        assert brain.react(**REACT_INPUT) == {
            "action": "post", "text": "x", "emotion_key": "none", "reason": "", "memory_count": 0,
        }

    @pytest.mark.parametrize("output", ["応答ｲﾓ🍠", "{not json}", "[1, 2]", ""])
    def test_non_json_is_rejected(self, strands, output):
        _, agent_instance, _ = strands
        agent_instance.return_value = output
        with pytest.raises(brain.ReactFormatError):
            brain.react(**REACT_INPUT)

    def test_new_agent_per_request(self, strands):
        agent_cls, _, _ = strands
        brain.react(**REACT_INPUT)
        brain.react(**REACT_INPUT)
        assert agent_cls.call_count == 2


FACT_SHOOT = "甘木ジュリ（@juri_bigangel）は2026年9月24日に撮影を行い、早くファンに見せたいと述べていた。"
FACT_FAN_VIEW = "ユーザーは@juri_bigangelの投稿を繰り返し閲覧・転載している。"
FACT_SLEEP = "甘木ジュリは2026年9月21日の朝、久しぶりによく眠れたと感じた。"
PREF_BURGER = json.dumps(
    {"context": "ユーザーが自身の投稿でマッシュルームワッパーが好きと述べた", "preference": "マッシュルームワッパーがとても好き"},
    ensure_ascii=False,
)
PREF_FAN_VIEW = json.dumps(
    {"context": "ユーザーは甘木ジュリの投稿を繰り返し閲覧・引用・転載し…", "preference": "甘木ジュリの投稿を追う"},
    ensure_ascii=False,
)


@pytest.fixture
def memory(monkeypatch):
    """Memory を有効化し、retrieve_memory_records を namespace ごとの固定レコードで返す"""
    records = {
        "/oshi/juri_bigangel/facts/": [FACT_SHOOT, FACT_FAN_VIEW, FACT_SLEEP],
        "/oshi/juri_bigangel/preferences/": [PREF_BURGER, PREF_FAN_VIEW],
    }
    client = MagicMock(name="bedrock-agentcore")
    client.retrieve_memory_records.side_effect = lambda **kw: {
        "memoryRecordSummaries": [{"content": {"text": t}} for t in records[kw["namespace"]]]
    }
    monkeypatch.setattr(brain, "OSHI_MEMORY_ID", "mem-1")
    monkeypatch.setattr(brain, "OSHI_ACTOR_ID", "juri_bigangel")
    monkeypatch.setattr(brain, "_memory_client", client)
    return client


class TestRecallOshiMemory:
    # react のテストは strands → memory の順に fixture を取る（memory が Memory を有効化し直す）

    def test_retrieves_facts_and_preferences_with_post_as_query(self, memory):
        lines, ok = brain.recall_oshi_memory("撮影した！")

        assert ok is True
        # ファン視点の誤抽出と睡眠・体調（タイプ E）は除外、preferences は本人の好みの 1 文だけ
        assert lines == [FACT_SHOOT, "好み: マッシュルームワッパーがとても好き"]
        calls = {c.kwargs["namespace"]: c.kwargs for c in memory.retrieve_memory_records.call_args_list}
        assert calls["/oshi/juri_bigangel/facts/"]["searchCriteria"] == {"searchQuery": "撮影した！", "topK": brain.FACTS_TOP_K}
        assert calls["/oshi/juri_bigangel/preferences/"]["searchCriteria"]["topK"] == brain.PREFERENCES_TOP_K
        assert all(c["memoryId"] == "mem-1" for c in calls.values())

    def test_disabled_without_memory_id(self, memory, monkeypatch):
        monkeypatch.setattr(brain, "OSHI_MEMORY_ID", "")
        assert brain.recall_oshi_memory("撮影") == ([], True)
        memory.retrieve_memory_records.assert_not_called()

    def test_failure_returns_not_ok(self, memory):
        memory.retrieve_memory_records.side_effect = RuntimeError("AccessDenied")
        assert brain.recall_oshi_memory("撮影") == ([], False)

    def test_fan_view_rule_needs_both_prefix_and_word(self):
        assert brain._is_fan_view("ユーザーは投稿を閲覧している") is True
        assert brain._is_fan_view("ユーザーはマッシュルームワッパーが好き") is False
        assert brain._is_fan_view("甘木ジュリは運営に相談した") is False

    def test_private_life_words(self):
        assert brain._is_private_life("帰宅して早く寝なければならない") is True
        assert brain._is_private_life("体調を崩して病院に行った") is True
        assert brain._is_private_life("福岡でまんぷく祭の公演に出演した") is False

    def test_react_injects_memories_into_user_message(self, strands, memory):
        _, agent_instance, _ = strands

        result = brain.react(**REACT_INPUT)

        user_message = agent_instance.call_args.args[0]
        assert f"- {FACT_SHOOT}\n- 好み: マッシュルームワッパーがとても好き" in user_message
        assert "閲覧" not in user_message
        assert FACT_SHOOT not in REACT_SYSTEM_PROMPT
        assert result["memory_count"] == 2

    def test_react_continues_when_recall_fails(self, strands, memory):
        _, agent_instance, _ = strands
        memory.retrieve_memory_records.side_effect = RuntimeError("throttled")

        result = brain.react(**REACT_INPUT)

        assert result["memory_count"] == -1
        assert result["action"] == "post"
        assert brain.NO_MEMORIES in agent_instance.call_args.args[0]


class TestReplyResponse:
    def test_fills_template_with_character_prompt(self, strands):
        agent_cls, agent_instance, _ = strands
        agent_instance.return_value = "  応答ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる  "

        text = brain.reply_response(reply_text="かわいい", reply_username="fan_taro", bot_tweet_text="元投稿")

        assert text == "応答ｲﾓ🍠 #さつまいもの民 #びっくえんじぇる"
        assert agent_cls.call_args.kwargs["system_prompt"] == CHARACTER_SYSTEM_PROMPT
        agent_instance.assert_called_once_with(
            REPLY_USER_TEMPLATE.format(username="fan_taro", bot_tweet_text="元投稿", reply_text="かわいい")
        )


class TestHandle:
    def test_react_returns_result_object(self, strands):
        result = brain.handle({"task": "react", "input": REACT_INPUT})
        assert result == {"success": True, "result": REACT_RESULT, "model_id": brain.MODEL_ID}
        assert "text" not in result

    def test_reply_returns_text(self, strands):
        _, agent_instance, _ = strands
        agent_instance.return_value = "応答ｲﾓ🍠"
        result = brain.handle({
            "task": "reply_response",
            "input": {"reply_text": "x", "reply_username": "u", "bot_tweet_text": "b"},
        })
        assert result == {"success": True, "text": "応答ｲﾓ🍠", "model_id": brain.MODEL_ID}

    def test_removed_tasks_are_unknown(self, strands):
        for task in ("oshi_response", "classify_emotion"):
            result = brain.handle({"task": task, "input": {}})
            assert result["success"] is False
            assert "unknown task" in result["error"]

    def test_missing_task(self, strands):
        assert brain.handle({})["success"] is False

    def test_input_must_be_object(self, strands):
        result = brain.handle({"task": "react", "input": "x"})
        assert result["success"] is False
        assert "object" in result["error"]

    def test_invalid_arguments(self, strands):
        result = brain.handle({"task": "react", "input": {"post_content": "x"}})
        assert result["success"] is False
        assert "invalid input" in result["error"]

    def test_format_error_is_reported_as_failure(self, strands):
        _, agent_instance, _ = strands
        agent_instance.return_value = "応答ｲﾓ🍠"
        result = brain.handle({"task": "react", "input": REACT_INPUT})
        assert result["success"] is False
        assert result["error"].startswith("ReactFormatError:")

    def test_model_exception_is_wrapped(self, strands):
        _, agent_instance, _ = strands
        agent_instance.side_effect = RuntimeError("bedrock down")
        result = brain.handle({"task": "react", "input": REACT_INPUT})
        assert result["success"] is False
        assert "RuntimeError: bedrock down" == result["error"]
        assert result["model_id"] == brain.MODEL_ID


class TestMain:
    def test_entrypoint_delegates_to_handle(self, strands):
        import main

        with patch.object(main.brain, "handle", return_value={"success": True}) as h:
            assert main.invoke({"task": "react", "input": {}}) == {"success": True}
            h.assert_called_once_with({"task": "react", "input": {}})
