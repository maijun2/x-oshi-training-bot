"""
エラーハンドリングモジュール

一時的なエラー、重大なエラー、フォールバック処理を提供します。
"""
import sys
import traceback
from typing import Any, Callable, Optional, TypeVar

from .logging import log_event, EventType, LogLevel

# デフォルト応答テキスト
DEFAULT_RESPONSE_OSHI = "じゅりちゃんの投稿を見つけたｲﾓ🍠✨ #さつまいもの民 #びっくえんじぇる"
DEFAULT_RESPONSE_GROUP = "グループの投稿を見つけたｲﾓ🍠✨ #さつまいもの民 #びっくえんじぇる"

T = TypeVar("T")


class BotError(Exception):
    """ボットの一般的なエラー"""
    pass


class CriticalError(Exception):
    """重大なエラー（リトライ不可能）"""
    pass


def handle_api_error(
    error: Exception,
    context: str,
    retry_info: str = "next_scheduled_run",
) -> None:
    """
    API呼び出しエラーを処理（一時的なエラー）
    
    一時的なエラーはログに記録し、次回のスケジュール実行で自動的に再試行されます。
    
    Args:
        error: 発生した例外
        context: エラーのコンテキスト情報
        retry_info: リトライ情報
    """
    log_event(
        level=LogLevel.ERROR,
        event_type=EventType.ERROR,
        data={
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
            "retry": retry_info,
        },
        message=f"API error in {context}: {error}",
    )


def handle_critical_error(
    error: Exception,
    context: str,
    exit_process: bool = True,
) -> None:
    """
    重大なエラーを処理してLambda実行を終了
    
    重大なエラーはリトライ不可能なエラーで、認証情報の欠落や
    必須リソースの欠落などが該当します。
    
    Args:
        error: 発生した例外
        context: エラーのコンテキスト情報
        exit_process: プロセスを終了するかどうか（テスト時はFalse）
    
    Raises:
        CriticalError: exit_process=Falseの場合
    """
    log_event(
        level=LogLevel.CRITICAL,
        event_type=EventType.ERROR,
        data={
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
            "stack_trace": traceback.format_exc(),
        },
        message=f"Critical error in {context}: {error}",
    )
    
    if exit_process:
        sys.exit(1)
    else:
        raise CriticalError(f"Critical error in {context}: {error}") from error


def generate_response_with_fallback(
    generator_func: Callable[[], T],
    fallback_value: T,
    context: str,
) -> T:
    """
    フォールバック付きで処理を実行
    
    Args:
        generator_func: 実行する関数
        fallback_value: 失敗時のフォールバック値
        context: コンテキスト情報
    
    Returns:
        生成された値またはフォールバック値
    """
    try:
        return generator_func()
    except Exception as e:
        log_event(
            level=LogLevel.WARNING,
            event_type=EventType.ERROR,
            data={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "context": context,
                "fallback": "using_fallback_value",
            },
            message=f"Using fallback for {context}: {e}",
        )
        return fallback_value


def get_default_response(post_type: str) -> str:
    """
    デフォルト応答を取得
    
    Args:
        post_type: "oshi" または "group"
    
    Returns:
        デフォルト応答テキスト
    """
    if post_type == "oshi":
        return DEFAULT_RESPONSE_OSHI
    return DEFAULT_RESPONSE_GROUP
