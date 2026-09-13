"""
OshiMemoryWriter — 推しの投稿を AgentCore Memory に書き込む（フェーズ3a-write）

いも丸が「推しのことを覚える」ための記憶（設計書 §8 / §10-8）。書き込みは頭脳を通さず
Lambda から直接 CreateEvent を呼ぶ。長期記憶（事実・好み・エピソード）への抽出は
Memory 側の戦略が非同期に行うので、ここでは短期記憶へのイベント投入だけを担う。

- actorId  = 推しの X ユーザー名（推し 1 本の namespace）
- sessionId = 推しの 1 日（JST）。Episodic 戦略は 1 セッションを 1 エピソードとして抽出する
- role     = USER。Semantic / User Preference 戦略は USER ロールの発言から「本人の事実・好み」を抽出する
- clientToken = tweet_id。再実行時の二重書き込みを防ぐ（冪等ロックの外側の保険）

失敗時は例外を投げる。握りつぶし（ERROR ログ）は呼び出し側（lambda_handler）の責務。
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config

from .daily_reporter import JST
from .timeline_monitor import Tweet

logger = logging.getLogger(__name__)

DEFAULT_REGION = "ap-northeast-1"
DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 30
SESSION_ID_PREFIX = "oshi-"
CLIENT_TOKEN_PREFIX = "oshi-"
EVENT_ROLE = "USER"


def parse_created_at(created_at: Optional[str]) -> Optional[datetime]:
    """X API の created_at（ISO 8601、末尾 Z）を aware datetime にする。解釈できなければ None"""
    if not created_at:
        return None
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def session_id_for(posted_at: datetime) -> str:
    """推しの 1 日（JST）を 1 セッションにする: oshi-YYYY-MM-DD"""
    return f"{SESSION_ID_PREFIX}{posted_at.astimezone(JST).strftime('%Y-%m-%d')}"


def build_event_text(tweet: Tweet, username: str, posted_at: datetime) -> str:
    """
    記憶に残す本文。日付を頭に付けて「9/13 にライブ」のような事実が日付付きで抽出されるようにする。
    引用ポストは本文に推しのコメントしか無いので、その旨を見出しに書く
    """
    kind = "の引用ポストへのコメント" if tweet.is_quote_tweet else "の投稿"
    stamp = posted_at.astimezone(JST).strftime("%Y-%m-%d %H:%M JST")
    return f"[推し @{username} {kind} {stamp}]\n{tweet.text}"


class OshiMemoryWriter:
    """推しの投稿 1 件を AgentCore Memory の 1 イベントとして記録する"""

    def __init__(
        self,
        memory_id: str,
        actor_id: str,
        region: str = DEFAULT_REGION,
        client: Optional[Any] = None,
    ):
        if not memory_id:
            raise ValueError("memory_id is required")
        if not actor_id:
            raise ValueError("actor_id is required")
        self._memory_id = memory_id
        self._actor_id = actor_id
        self._client = client or boto3.client(
            "bedrock-agentcore",
            region_name=region,
            config=Config(
                read_timeout=DEFAULT_READ_TIMEOUT,
                connect_timeout=DEFAULT_CONNECT_TIMEOUT,
                retries={"max_attempts": 1},
            ),
        )

    @property
    def memory_id(self) -> str:
        return self._memory_id

    @property
    def actor_id(self) -> str:
        return self._actor_id

    def record_post(self, tweet: Tweet) -> str:
        """
        推しの投稿をイベントとして書き込み、eventId を返す

        Raises:
            botocore の例外（呼び出し側で握りつぶす）
        """
        posted_at = parse_created_at(tweet.created_at) or datetime.now(timezone.utc)
        params: Dict[str, Any] = {
            "memoryId": self._memory_id,
            "actorId": self._actor_id,
            "sessionId": session_id_for(posted_at),
            "eventTimestamp": posted_at,
            "payload": [
                {
                    "conversational": {
                        "content": {"text": build_event_text(tweet, self._actor_id, posted_at)},
                        "role": EVENT_ROLE,
                    }
                }
            ],
            "clientToken": f"{CLIENT_TOKEN_PREFIX}{tweet.id}",
            "metadata": {
                "tweet_id": {"stringValue": tweet.id},
                "kind": {"stringValue": "quote" if tweet.is_quote_tweet else "original"},
            },
        }
        response = self._client.create_event(**params)
        event_id = response["event"]["eventId"]
        logger.info(
            "Oshi memory event recorded: tweet=%s session=%s event=%s",
            tweet.id,
            params["sessionId"],
            event_id,
        )
        return event_id
