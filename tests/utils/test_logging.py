"""
構造化ロギングのユニットテスト
"""
import json
import logging
import pytest
from datetime import datetime, timezone

from src.hokuhoku_imomaru_bot.utils.logging import (
    log_event,
    EventType,
    LogLevel,
    logger,
)


class TestLogEvent:
    """log_event関数のテスト"""
    
    def test_log_event_returns_dict(self):
        """log_eventが辞書を返すことを確認"""
        result = log_event(
            level=LogLevel.INFO,
            event_type=EventType.LAMBDA_START,
        )
        
        assert isinstance(result, dict)
    
    def test_log_event_contains_timestamp(self):
        """ログエントリにタイムスタンプが含まれることを確認"""
        result = log_event(
            level=LogLevel.INFO,
            event_type=EventType.LAMBDA_START,
        )
        
        assert "timestamp" in result
        # ISO 8601形式であることを確認
        datetime.fromisoformat(result["timestamp"].replace("Z", "+00:00"))
    
    def test_log_event_contains_level(self):
        """ログエントリにレベルが含まれることを確認"""
        result = log_event(
            level=LogLevel.WARNING,
            event_type=EventType.ERROR,
        )
        
        assert result["level"] == "WARNING"
    
    def test_log_event_contains_event_type(self):
        """ログエントリにイベントタイプが含まれることを確認"""
        result = log_event(
            level=LogLevel.INFO,
            event_type=EventType.POST_DETECTED,
        )
        
        assert result["event_type"] == "post_detected"
    
    def test_log_event_with_message(self):
        """メッセージ付きログエントリを確認"""
        result = log_event(
            level=LogLevel.INFO,
            event_type=EventType.XP_GAINED,
            message="XP gained successfully",
        )
        
        assert result["message"] == "XP gained successfully"
    
    def test_log_event_with_data(self):
        """データ付きログエントリを確認"""
        result = log_event(
            level=LogLevel.INFO,
            event_type=EventType.LEVEL_UP,
            data={"old_level": 5, "new_level": 6},
        )
        
        assert result["old_level"] == 5
        assert result["new_level"] == 6
    
    def test_log_event_json_format(self, caplog):
        """ログがJSON形式で出力されることを確認"""
        with caplog.at_level(logging.INFO, logger="hokuhoku_imomaru_bot"):
            log_event(
                level=LogLevel.INFO,
                event_type=EventType.TIMELINE_CHECK,
                data={"tweets_found": 3},
            )
        
        # ログレコードを取得
        assert len(caplog.records) > 0
        log_message = caplog.records[-1].message
        
        # JSON形式であることを確認
        parsed = json.loads(log_message)
        assert parsed["event_type"] == "timeline_check"
        assert parsed["tweets_found"] == 3
    
    def test_log_event_all_levels(self, caplog):
        """すべてのログレベルが正しく出力されることを確認"""
        levels = [
            (LogLevel.INFO, logging.INFO),
            (LogLevel.WARNING, logging.WARNING),
            (LogLevel.ERROR, logging.ERROR),
            (LogLevel.CRITICAL, logging.CRITICAL),
        ]
        
        for log_level, python_level in levels:
            with caplog.at_level(logging.DEBUG, logger="hokuhoku_imomaru_bot"):
                caplog.clear()
                log_event(
                    level=log_level,
                    event_type=EventType.LAMBDA_START,
                )
                
                assert len(caplog.records) > 0
                assert caplog.records[-1].levelno == python_level


class TestEventType:
    """EventType列挙型のテスト"""
    
    def test_all_event_types_exist(self):
        """すべてのイベントタイプが存在することを確認"""
        expected_types = [
            "lambda_start",
            "timeline_check",
            "post_detected",
            "xp_gained",
            "level_up",
            "profile_updated",
            "daily_report",
            "error",
            "lambda_end",
        ]
        
        for event_type in expected_types:
            assert hasattr(EventType, event_type.upper())


class TestLogLevel:
    """LogLevel列挙型のテスト"""
    
    def test_all_log_levels_exist(self):
        """すべてのログレベルが存在することを確認"""
        expected_levels = ["INFO", "WARNING", "ERROR", "CRITICAL"]
        
        for level in expected_levels:
            assert hasattr(LogLevel, level)
