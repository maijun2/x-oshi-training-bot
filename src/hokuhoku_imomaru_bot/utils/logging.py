"""
構造化ロギングモジュール

JSON形式でログを出力し、CloudWatch Logsでの検索・分析を容易にします。
"""
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

# ロガーの設定
logger = logging.getLogger("hokuhoku_imomaru_bot")
logger.setLevel(logging.INFO)


class LogLevel(str, Enum):
    """ログレベル"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EventType(str, Enum):
    """イベントタイプ"""
    LAMBDA_START = "lambda_start"
    TIMELINE_CHECK = "timeline_check"
    POST_DETECTED = "post_detected"
    XP_GAINED = "xp_gained"
    LEVEL_UP = "level_up"
    PROFILE_UPDATED = "profile_updated"
    DAILY_REPORT = "daily_report"
    ERROR = "error"
    LAMBDA_END = "lambda_end"


def log_event(
    level: LogLevel,
    event_type: EventType,
    data: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    構造化ログを出力
    
    Args:
        level: ログレベル（INFO, WARNING, ERROR, CRITICAL）
        event_type: イベントタイプ
        data: ログデータ（オプション）
        message: ログメッセージ（オプション）
    
    Returns:
        出力されたログエントリ
    """
    log_entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level.value,
        "event_type": event_type.value,
    }
    
    if message:
        log_entry["message"] = message
    
    if data:
        log_entry.update(data)
    
    log_json = json.dumps(log_entry, ensure_ascii=False, default=str)
    
    if level == LogLevel.INFO:
        logger.info(log_json)
    elif level == LogLevel.WARNING:
        logger.warning(log_json)
    elif level == LogLevel.ERROR:
        logger.error(log_json)
    elif level == LogLevel.CRITICAL:
        logger.critical(log_json)
    
    return log_entry
