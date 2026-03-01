"""
ReplyMonitorクラス

ボット投稿へのリプライを検出するサービスです。
User Mentions Timeline APIを使用してメンションを取得し、
ボット投稿へのリプライをフィルタリングします。
"""
import logging
from typing import List, Optional

from ..clients import XAPIClient
from ..models import Reply

logger = logging.getLogger(__name__)


class ReplyMonitor:
    """
    ボット投稿へのリプライを検出するクラス

    User Mentions Timeline APIを使用してメンションを取得し、
    in_reply_to_user_idがボットのユーザーIDと一致するものを
    リプライとしてフィルタリングします。
    """

    def __init__(self, api_client: XAPIClient, bot_user_id: str):
        """
        ReplyMonitorを初期化

        Args:
            api_client: XAPIClientインスタンス
            bot_user_id: ボットのユーザーID
        """
        self.api_client = api_client
        self.bot_user_id = bot_user_id

    def detect_replies(
        self,
        since_tweet_id: Optional[str] = None,
        max_results: int = 100,
    ) -> List[Reply]:
        """
        ボット投稿へのリプライを検出

        User Mentions Timeline APIを使用してメンションを取得し、
        ボット投稿へのリプライのみをフィルタリングして返します。

        Args:
            since_tweet_id: 前回チェックした最新のTweet ID
            max_results: 最大取得件数

        Returns:
            リプライのリスト
        """
        try:
            response = self.api_client.get_user_mentions(
                user_id=self.bot_user_id,
                since_id=since_tweet_id,
                max_results=max_results,
            )
        except Exception as e:
            logger.error(f"Failed to get user mentions: {e}")
            return []

        mentions = response.get("data", [])
        includes = response.get("includes", {})

        if not mentions:
            logger.info("No new mentions found")
            return []

        # ボット投稿へのリプライをフィルタリング
        replies = []
        for mention in mentions:
            if mention.get("in_reply_to_user_id") == self.bot_user_id:
                reply = Reply.from_api_response(mention, includes)
                replies.append(reply)

        logger.info(
            f"Detected {len(replies)} replies out of {len(mentions)} mentions"
        )
        return replies
