"""
ReplyProcessorクラス

リプライ処理を管理するサービスです。
冪等性制御、AI応答生成、リプライ投稿、処理済みリプライの記録を行います。
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from ..models import Reply

logger = logging.getLogger(__name__)


class ReplyProcessor:
    """
    リプライ処理を管理するクラス

    冪等性制御（30日チェック + Processed Replies Tableチェック）、
    AI応答生成、リプライ投稿、処理済みリプライの記録を行います。
    """

    def __init__(
        self,
        dynamodb_client,
        processed_replies_table_name: str = "imomaru-bot-processed-replies",
    ):
        """
        ReplyProcessorを初期化

        Args:
            dynamodb_client: boto3 DynamoDBクライアント
            processed_replies_table_name: Processed Replies Tableのテーブル名
        """
        self.dynamodb_client = dynamodb_client
        self.processed_replies_table_name = processed_replies_table_name
        self.max_tweet_age_days = 30
        self.ttl_days = 60

    def process_reply(
        self,
        reply: Reply,
        ai_generator,
        x_api_client,
    ) -> bool:
        """
        リプライを処理

        1. ボット投稿の日時チェック（30日以内）
        2. 処理済みチェック（冪等性制御）
        3. リプライ対象ボット投稿を取得
        4. AI応答生成
        5. リプライ投稿
        6. 処理済みリプライを記録

        Args:
            reply: 処理するリプライ
            ai_generator: AIGeneratorインスタンス
            x_api_client: XAPIClientインスタンス

        Returns:
            処理成功の可否
        """
        # 1. ボット投稿の日時チェック（30日以内）
        if not self._is_tweet_recent(reply.in_reply_to_tweet_id, x_api_client):
            logger.info(f"Reply to old tweet (>30 days), skipping: {reply.id}")
            return False

        # 2. 処理済みチェック
        if self._is_reply_processed(reply.id):
            logger.info(f"Reply already processed, skipping: {reply.id}")
            return False

        try:
            # 3. リプライ対象ボット投稿を取得
            bot_tweet = x_api_client.get_tweet(reply.in_reply_to_tweet_id)

            # 4. AI応答生成
            response_text = ai_generator.generate_reply_response(
                reply_text=reply.text,
                reply_username=reply.author_username,
                bot_tweet_text=bot_tweet.get("text", ""),
            )

            # 5. リプライ投稿
            result = x_api_client.post_tweet(
                text=response_text,
                reply_to_tweet_id=reply.id,
            )

            bot_reply_id = result.get("data", {}).get("id", "")

            # 6. 処理済みリプライを記録
            self._record_processed_reply(
                reply_id=reply.id,
                user_id=reply.author_id,
                bot_reply_id=bot_reply_id,
            )

            logger.info(
                f"Reply processed successfully: {reply.id} -> {bot_reply_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to process reply {reply.id}: {e}")
            return False

    def _is_tweet_recent(
        self,
        tweet_id: str,
        x_api_client,
    ) -> bool:
        """
        ツイートが30日以内かチェック

        Args:
            tweet_id: チェックするツイートID
            x_api_client: XAPIClientインスタンス

        Returns:
            30日以内の場合True
        """
        try:
            tweet = x_api_client.get_tweet(tweet_id)
            created_at_str = tweet.get("created_at", "")
            if not created_at_str:
                logger.error(f"Tweet {tweet_id} has no created_at field")
                return False
            created_at = datetime.fromisoformat(
                created_at_str.replace("Z", "+00:00")
            )
            age = datetime.now(timezone.utc) - created_at
            return age.days < self.max_tweet_age_days
        except Exception as e:
            logger.error(f"Failed to check tweet age for {tweet_id}: {e}")
            return False

    def _is_reply_processed(self, reply_id: str) -> bool:
        """
        リプライが処理済みかチェック

        Args:
            reply_id: チェックするリプライID

        Returns:
            処理済みの場合True
        """
        try:
            response = self.dynamodb_client.get_item(
                TableName=self.processed_replies_table_name,
                Key={"tweet_id": {"S": reply_id}},
            )
            return "Item" in response
        except Exception as e:
            logger.error(f"Failed to check processed reply {reply_id}: {e}")
            return False

    def _record_processed_reply(
        self,
        reply_id: str,
        user_id: str,
        bot_reply_id: str,
    ) -> None:
        """
        処理済みリプライを記録

        Args:
            reply_id: リプライツイートID
            user_id: リプライ元ユーザーID
            bot_reply_id: ボットが投稿したリプライのツイートID
        """
        ttl = int(time.time()) + (self.ttl_days * 24 * 60 * 60)
        self.dynamodb_client.put_item(
            TableName=self.processed_replies_table_name,
            Item={
                "tweet_id": {"S": reply_id},
                "replied_at": {"S": datetime.now(timezone.utc).isoformat()},
                "user_id": {"S": user_id},
                "bot_reply_id": {"S": bot_reply_id},
                "ttl": {"N": str(ttl)},
            },
        )
        logger.info(
            f"Recorded processed reply: {reply_id}, ttl={ttl}"
        )
