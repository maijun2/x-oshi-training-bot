"""
StateStoreクラス

DynamoDBとの状態の読み書きを管理します。
"""
import logging
import time
from typing import Dict, Optional
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from ..models import BotState

logger = logging.getLogger(__name__)


class TweetAlreadyProcessedError(Exception):
    """ツイートが既に処理済みの場合に発生する例外"""
    pass


class StateStore:
    """
    DynamoDBとの状態の読み書きを管理するクラス
    
    Attributes:
        dynamodb_client: boto3 DynamoDBクライアント
        state_table_name: BotStateテーブル名
        xp_table_name: XPTableテーブル名
    """

    def __init__(
        self,
        dynamodb_client,
        state_table_name: str = "imomaru-bot-state",
        xp_table_name: str = "imomaru-bot-xp-table",
        processed_tweets_table_name: str = "imomaru-bot-processed-tweets",
    ):
        """
        StateStoreを初期化
        
        Args:
            dynamodb_client: boto3 DynamoDBクライアント
            state_table_name: BotStateテーブル名
            xp_table_name: XPTableテーブル名
            processed_tweets_table_name: 処理済みツイートテーブル名
        """
        self.dynamodb_client = dynamodb_client
        self.state_table_name = state_table_name
        self.xp_table_name = xp_table_name
        self.processed_tweets_table_name = processed_tweets_table_name
        # TTL: 24時間（秒）
        self.ttl_seconds = 24 * 60 * 60

    def load_state(self) -> BotState:
        """
        DynamoDBから現在の状態を読み込み
        
        Returns:
            BotStateインスタンス（存在しない場合はデフォルト値）
        """
        try:
            response = self.dynamodb_client.get_item(
                TableName=self.state_table_name,
                Key={"state_id": {"S": "current"}},
            )
            
            if "Item" in response:
                item = response["Item"]
                return BotState(
                    cumulative_xp=float(item.get("cumulative_xp", {}).get("N", 0)),
                    current_level=int(item.get("current_level", {}).get("N", 1)),
                    latest_tweet_id=item.get("latest_tweet_id", {}).get("S"),
                    last_updated=item.get("last_updated", {}).get("S", datetime.now(timezone.utc).isoformat()),
                    oshi_post_count=int(item.get("oshi_post_count", {}).get("N", 0)),
                    group_post_count=int(item.get("group_post_count", {}).get("N", 0)),
                    repost_count=int(item.get("repost_count", {}).get("N", 0)),
                    like_count=int(item.get("like_count", {}).get("N", 0)),
                    daily_oshi_count=int(item.get("daily_oshi_count", {}).get("N", 0)),
                    daily_group_count=int(item.get("daily_group_count", {}).get("N", 0)),
                    daily_repost_count=int(item.get("daily_repost_count", {}).get("N", 0)),
                    daily_like_count=int(item.get("daily_like_count", {}).get("N", 0)),
                    daily_xp=float(item.get("daily_xp", {}).get("N", 0)),
                    last_daily_report_date=item.get("last_daily_report_date", {}).get("S"),
                    last_profile_update_month=item.get("last_profile_update_month", {}).get("S"),
                    total_received_likes=int(item.get("total_received_likes", {}).get("N", 0)),
                    total_received_retweets=int(item.get("total_received_retweets", {}).get("N", 0)),
                )
            
            logger.info("No existing state found, returning default state")
            return BotState()
            
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            raise

    def save_state(self, state: BotState) -> bool:
        """
        状態をDynamoDBに保存
        
        Args:
            state: 保存するBotState
        
        Returns:
            保存成功の可否
        """
        try:
            # 最終更新日時を更新
            state.last_updated = datetime.now(timezone.utc).isoformat()
            
            item = {
                "state_id": {"S": "current"},
                "cumulative_xp": {"N": str(state.cumulative_xp)},
                "current_level": {"N": str(state.current_level)},
                "last_updated": {"S": state.last_updated},
                "oshi_post_count": {"N": str(state.oshi_post_count)},
                "group_post_count": {"N": str(state.group_post_count)},
                "repost_count": {"N": str(state.repost_count)},
                "like_count": {"N": str(state.like_count)},
                "daily_oshi_count": {"N": str(state.daily_oshi_count)},
                "daily_group_count": {"N": str(state.daily_group_count)},
                "daily_repost_count": {"N": str(state.daily_repost_count)},
                "daily_like_count": {"N": str(state.daily_like_count)},
                "daily_xp": {"N": str(state.daily_xp)},
                "total_received_likes": {"N": str(state.total_received_likes)},
                "total_received_retweets": {"N": str(state.total_received_retweets)},
            }
            
            # latest_tweet_idがNoneでない場合のみ追加
            if state.latest_tweet_id is not None:
                item["latest_tweet_id"] = {"S": state.latest_tweet_id}
            
            # last_daily_report_dateがNoneでない場合のみ追加
            if state.last_daily_report_date is not None:
                item["last_daily_report_date"] = {"S": state.last_daily_report_date}
            
            # last_profile_update_monthがNoneでない場合のみ追加
            if state.last_profile_update_month is not None:
                item["last_profile_update_month"] = {"S": state.last_profile_update_month}
            
            self.dynamodb_client.put_item(
                TableName=self.state_table_name,
                Item=item,
            )
            
            logger.info(f"State saved successfully: level={state.current_level}, xp={state.cumulative_xp}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            raise

    def load_xp_table(self) -> Dict[int, int]:
        """
        DQ3経験値テーブルをDynamoDBから読み込み
        
        Returns:
            レベルと必要経験値のマッピング {level: required_xp}
        """
        try:
            xp_table = {}
            
            response = self.dynamodb_client.scan(
                TableName=self.xp_table_name,
            )
            
            for item in response.get("Items", []):
                level = int(item.get("level", {}).get("N", 0))
                required_xp = int(item.get("required_xp", {}).get("N", 0))
                xp_table[level] = required_xp
            
            # ページネーション対応
            while "LastEvaluatedKey" in response:
                response = self.dynamodb_client.scan(
                    TableName=self.xp_table_name,
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                for item in response.get("Items", []):
                    level = int(item.get("level", {}).get("N", 0))
                    required_xp = int(item.get("required_xp", {}).get("N", 0))
                    xp_table[level] = required_xp
            
            logger.info(f"XP table loaded: {len(xp_table)} levels")
            return xp_table
            
        except Exception as e:
            logger.error(f"Failed to load XP table: {e}")
            raise

    def reset_daily_counts(self, state: BotState) -> BotState:
        """
        日次カウントをリセット
        
        Args:
            state: リセットするBotState
        
        Returns:
            リセット後のBotState
        """
        state.daily_oshi_count = 0
        state.daily_group_count = 0
        state.daily_repost_count = 0
        state.daily_like_count = 0
        state.daily_xp = 0.0
        return state


    def acquire_tweet_lock(self, tweet_id: str, action_type: str) -> bool:
        """
        ツイート処理のロックを取得（冪等性制御）
        
        条件付き書き込みを使用し、まだ処理されていない場合のみ成功する。
        既に処理済みの場合はTweetAlreadyProcessedErrorを発生させる。
        
        Args:
            tweet_id: 処理対象のツイートID
            action_type: 処理タイプ（"quote", "retweet_quote"など）
        
        Returns:
            ロック取得成功の可否
        
        Raises:
            TweetAlreadyProcessedError: ツイートが既に処理済みの場合
        """
        try:
            # TTLを計算（現在時刻 + 24時間）
            ttl = int(time.time()) + self.ttl_seconds
            
            self.dynamodb_client.put_item(
                TableName=self.processed_tweets_table_name,
                Item={
                    "tweet_id": {"S": tweet_id},
                    "action_type": {"S": action_type},
                    "processed_at": {"S": datetime.now(timezone.utc).isoformat()},
                    "ttl": {"N": str(ttl)},
                },
                # 条件: tweet_idが存在しない場合のみ書き込み成功
                ConditionExpression="attribute_not_exists(tweet_id)",
            )
            
            logger.info(f"Tweet lock acquired: tweet_id={tweet_id}, action_type={action_type}")
            return True
            
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(f"Tweet already processed (skipping): tweet_id={tweet_id}")
                raise TweetAlreadyProcessedError(f"Tweet {tweet_id} has already been processed")
            else:
                logger.error(f"Failed to acquire tweet lock: {e}")
                raise

    def is_tweet_processed(self, tweet_id: str) -> bool:
        """
        ツイートが既に処理済みかどうかを確認
        
        Args:
            tweet_id: 確認対象のツイートID
        
        Returns:
            処理済みの場合True
        """
        try:
            response = self.dynamodb_client.get_item(
                TableName=self.processed_tweets_table_name,
                Key={"tweet_id": {"S": tweet_id}},
            )
            return "Item" in response
            
        except Exception as e:
            logger.error(f"Failed to check tweet processed status: {e}")
            # エラー時は安全のため処理済みとみなさない
            return False
