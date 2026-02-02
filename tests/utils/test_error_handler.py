"""
エラーハンドリングのユニットテスト
"""
import json
import logging
import pytest

from src.hokuhoku_imomaru_bot.utils.error_handler import (
    handle_api_error,
    handle_critical_error,
    generate_response_with_fallback,
    get_default_response,
    BotError,
    CriticalError,
    DEFAULT_RESPONSE_OSHI,
    DEFAULT_RESPONSE_GROUP,
)
from src.hokuhoku_imomaru_bot.utils.logging import logger


class TestHandleApiError:
    """handle_api_error関数のテスト"""
    
    def test_logs_error_type(self, caplog):
        """エラータイプがログに記録されることを確認"""
        with caplog.at_level(logging.ERROR, logger="hokuhoku_imomaru_bot"):
            error = ValueError("Test error")
            handle_api_error(error, "test_context")
        
        assert len(caplog.records) > 0
        log_message = caplog.records[-1].message
        parsed = json.loads(log_message)
        
        assert parsed["error_type"] == "ValueError"
    
    def test_logs_error_message(self, caplog):
        """エラーメッセージがログに記録されることを確認"""
        with caplog.at_level(logging.ERROR, logger="hokuhoku_imomaru_bot"):
            error = RuntimeError("Something went wrong")
            handle_api_error(error, "api_call")
        
        log_message = caplog.records[-1].message
        parsed = json.loads(log_message)
        
        assert parsed["error_message"] == "Something went wrong"
    
    def test_logs_context(self, caplog):
        """コンテキストがログに記録されることを確認"""
        with caplog.at_level(logging.ERROR, logger="hokuhoku_imomaru_bot"):
            error = Exception("Error")
            handle_api_error(error, "timeline_check")
        
        log_message = caplog.records[-1].message
        parsed = json.loads(log_message)
        
        assert parsed["context"] == "timeline_check"
    
    def test_logs_retry_info(self, caplog):
        """リトライ情報がログに記録されることを確認"""
        with caplog.at_level(logging.ERROR, logger="hokuhoku_imomaru_bot"):
            error = Exception("Error")
            handle_api_error(error, "test", retry_info="manual_retry")
        
        log_message = caplog.records[-1].message
        parsed = json.loads(log_message)
        
        assert parsed["retry"] == "manual_retry"
    
    def test_default_retry_info(self, caplog):
        """デフォルトのリトライ情報を確認"""
        with caplog.at_level(logging.ERROR, logger="hokuhoku_imomaru_bot"):
            error = Exception("Error")
            handle_api_error(error, "test")
        
        log_message = caplog.records[-1].message
        parsed = json.loads(log_message)
        
        assert parsed["retry"] == "next_scheduled_run"


class TestHandleCriticalError:
    """handle_critical_error関数のテスト"""
    
    def test_logs_critical_level(self, caplog):
        """CRITICALレベルでログが記録されることを確認"""
        with caplog.at_level(logging.CRITICAL, logger="hokuhoku_imomaru_bot"):
            error = Exception("Critical error")
            
            with pytest.raises(CriticalError):
                handle_critical_error(error, "auth_failure", exit_process=False)
        
        assert len(caplog.records) > 0
        assert caplog.records[-1].levelno == logging.CRITICAL
    
    def test_logs_stack_trace(self, caplog):
        """スタックトレースがログに記録されることを確認"""
        with caplog.at_level(logging.CRITICAL, logger="hokuhoku_imomaru_bot"):
            error = Exception("Critical error")
            
            with pytest.raises(CriticalError):
                handle_critical_error(error, "test", exit_process=False)
        
        log_message = caplog.records[-1].message
        parsed = json.loads(log_message)
        
        assert "stack_trace" in parsed
        assert len(parsed["stack_trace"]) > 0
    
    def test_raises_critical_error_when_not_exiting(self):
        """exit_process=Falseの場合にCriticalErrorが発生することを確認"""
        error = ValueError("Missing credentials")
        
        with pytest.raises(CriticalError) as exc_info:
            handle_critical_error(error, "secrets_manager", exit_process=False)
        
        assert "secrets_manager" in str(exc_info.value)
    
    def test_logs_error_type_and_message(self, caplog):
        """エラータイプとメッセージがログに記録されることを確認"""
        with caplog.at_level(logging.CRITICAL, logger="hokuhoku_imomaru_bot"):
            error = KeyError("missing_key")
            
            with pytest.raises(CriticalError):
                handle_critical_error(error, "config", exit_process=False)
        
        log_message = caplog.records[-1].message
        parsed = json.loads(log_message)
        
        assert parsed["error_type"] == "KeyError"
        assert "missing_key" in parsed["error_message"]


class TestGenerateResponseWithFallback:
    """generate_response_with_fallback関数のテスト"""
    
    def test_returns_generator_result_on_success(self):
        """成功時にジェネレータの結果を返すことを確認"""
        def generator():
            return "Generated response"
        
        result = generate_response_with_fallback(
            generator_func=generator,
            fallback_value="Fallback",
            context="test",
        )
        
        assert result == "Generated response"
    
    def test_returns_fallback_on_failure(self):
        """失敗時にフォールバック値を返すことを確認"""
        def failing_generator():
            raise Exception("Generation failed")
        
        result = generate_response_with_fallback(
            generator_func=failing_generator,
            fallback_value="Fallback response",
            context="test",
        )
        
        assert result == "Fallback response"
    
    def test_logs_warning_on_fallback(self, caplog):
        """フォールバック使用時にWARNINGログが記録されることを確認"""
        def failing_generator():
            raise ValueError("Error")
        
        with caplog.at_level(logging.WARNING, logger="hokuhoku_imomaru_bot"):
            generate_response_with_fallback(
                generator_func=failing_generator,
                fallback_value="Fallback",
                context="bedrock_call",
            )
        
        assert len(caplog.records) > 0
        log_message = caplog.records[-1].message
        parsed = json.loads(log_message)
        
        assert parsed["context"] == "bedrock_call"
        assert parsed["fallback"] == "using_fallback_value"
    
    def test_works_with_different_types(self):
        """異なる型で動作することを確認"""
        # 整数
        result_int = generate_response_with_fallback(
            generator_func=lambda: 42,
            fallback_value=0,
            context="test",
        )
        assert result_int == 42
        
        # リスト
        result_list = generate_response_with_fallback(
            generator_func=lambda: [1, 2, 3],
            fallback_value=[],
            context="test",
        )
        assert result_list == [1, 2, 3]
        
        # 辞書
        result_dict = generate_response_with_fallback(
            generator_func=lambda: {"key": "value"},
            fallback_value={},
            context="test",
        )
        assert result_dict == {"key": "value"}


class TestGetDefaultResponse:
    """get_default_response関数のテスト"""
    
    def test_oshi_response(self):
        """推し用のデフォルト応答を確認"""
        result = get_default_response("oshi")
        assert result == DEFAULT_RESPONSE_OSHI
        assert "じゅりちゃん" in result
        assert "#さつまいもの民" in result
    
    def test_group_response(self):
        """グループ用のデフォルト応答を確認"""
        result = get_default_response("group")
        assert result == DEFAULT_RESPONSE_GROUP
        assert "グループ" in result
        assert "#さつまいもの民" in result
    
    def test_unknown_type_returns_group(self):
        """不明なタイプの場合はグループ応答を返すことを確認"""
        result = get_default_response("unknown")
        assert result == DEFAULT_RESPONSE_GROUP


class TestBotError:
    """BotError例外のテスト"""
    
    def test_can_raise_bot_error(self):
        """BotErrorを発生させられることを確認"""
        with pytest.raises(BotError):
            raise BotError("Test error")
    
    def test_bot_error_message(self):
        """BotErrorのメッセージを確認"""
        try:
            raise BotError("Custom message")
        except BotError as e:
            assert str(e) == "Custom message"


class TestCriticalError:
    """CriticalError例外のテスト"""
    
    def test_can_raise_critical_error(self):
        """CriticalErrorを発生させられることを確認"""
        with pytest.raises(CriticalError):
            raise CriticalError("Critical test error")
    
    def test_critical_error_message(self):
        """CriticalErrorのメッセージを確認"""
        try:
            raise CriticalError("Critical message")
        except CriticalError as e:
            assert str(e) == "Critical message"
