"""
AllowedUsersServiceクラス

許可ユーザーリストを管理するサービスです。
DynamoDB Allowed Users Tableから許可ユーザーを検索し、
リプライ処理の対象ユーザーかどうかを判定します。
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AllowedUsersService:
    """
    許可ユーザーリストを管理するクラス

    DynamoDB Allowed Users Tableを使用して、
    リプライ処理の対象となる許可ユーザーを管理します。
    """

    def __init__(
        self,
        dynamodb_client,
        table_name: str = "imomaru-bot-allowed-users",
    ):
        """
        AllowedUsersServiceを初期化

        Args:
            dynamodb_client: boto3 DynamoDBクライアント
            table_name: Allowed Users Tableのテーブル名
        """
        self.dynamodb_client = dynamodb_client
        self.table_name = table_name

    def is_user_allowed(self, user_id: str) -> bool:
        """
        ユーザーが許可リストに含まれているか確認

        Args:
            user_id: チェックするユーザーID

        Returns:
            許可されている場合True、非許可またはエラー時False
        """
        try:
            response = self.dynamodb_client.get_item(
                TableName=self.table_name,
                Key={"user_id": {"S": user_id}},
            )
            is_allowed = "Item" in response
            logger.info(
                f"User allowed check: user_id={user_id}, allowed={is_allowed}"
            )
            return is_allowed
        except Exception as e:
            logger.error(
                f"Failed to check allowed user: user_id={user_id}, error={e}"
            )
            return False
