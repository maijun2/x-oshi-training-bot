"""
ほくほくいも丸くん育成ボット

X（旧Twitter）育成ボット - AWSサーバーレスアーキテクチャ
"""

__version__ = "0.1.0"

from .lambda_handler import lambda_handler

__all__ = ["lambda_handler"]
