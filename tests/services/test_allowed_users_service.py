"""
AllowedUsersServiceクラスのユニットテスト
"""
import logging
import pytest
import boto3
from moto import mock_aws
from src.hokuhoku_imomaru_bot.services.allowed_users_service import AllowedUsersService


TABLE_NAME = "imomaru-bot-allowed-users"


def _create_table(dynamodb_client):
    """テスト用DynamoDBテーブルを作成"""
    dynamodb_client.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def _add_user(dynamodb_client, user_id, username="test_user"):
    """テスト用ユーザーを追加"""
    dynamodb_client.put_item(
        TableName=TABLE_NAME,
        Item={
            "user_id": {"S": user_id},
            "username": {"S": username},
            "added_date": {"S": "2026-01-15T10:00:00Z"},
        },
    )


class TestAllowedUsersServiceIsUserAllowed:
    """is_user_allowedメソッドのテスト"""

    @mock_aws
    def test_allowed_user_returns_true(self):
        """許可ユーザーの場合Trueを返すこと"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)
        _add_user(client, "12345")

        service = AllowedUsersService(dynamodb_client=client, table_name=TABLE_NAME)
        assert service.is_user_allowed("12345") is True

    @mock_aws
    def test_non_allowed_user_returns_false(self):
        """非許可ユーザーの場合Falseを返すこと"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        service = AllowedUsersService(dynamodb_client=client, table_name=TABLE_NAME)
        assert service.is_user_allowed("99999") is False

    @mock_aws
    def test_multiple_users_checked_independently(self):
        """複数ユーザーが独立して判定されること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)
        _add_user(client, "111")
        _add_user(client, "222")

        service = AllowedUsersService(dynamodb_client=client, table_name=TABLE_NAME)
        assert service.is_user_allowed("111") is True
        assert service.is_user_allowed("222") is True
        assert service.is_user_allowed("333") is False

    @mock_aws
    def test_dynamodb_error_returns_false(self):
        """DynamoDBアクセス失敗時にFalseを返すこと"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        # テーブルを作成しない → アクセスエラー

        service = AllowedUsersService(dynamodb_client=client, table_name=TABLE_NAME)
        assert service.is_user_allowed("12345") is False

    @mock_aws
    def test_dynamodb_error_logs_error(self, caplog):
        """DynamoDBアクセス失敗時にエラーログが出力されること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")

        service = AllowedUsersService(dynamodb_client=client, table_name=TABLE_NAME)
        with caplog.at_level(logging.ERROR):
            service.is_user_allowed("12345")

        assert "Failed to check allowed user" in caplog.text
        assert "user_id=12345" in caplog.text

    @mock_aws
    def test_allowed_user_logs_info(self, caplog):
        """許可ユーザーチェック時にINFOログが出力されること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)
        _add_user(client, "12345")

        service = AllowedUsersService(dynamodb_client=client, table_name=TABLE_NAME)
        with caplog.at_level(logging.INFO):
            service.is_user_allowed("12345")

        assert "user_id=12345" in caplog.text
        assert "allowed=True" in caplog.text

    @mock_aws
    def test_non_allowed_user_logs_info(self, caplog):
        """非許可ユーザーチェック時にINFOログが出力されること"""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        service = AllowedUsersService(dynamodb_client=client, table_name=TABLE_NAME)
        with caplog.at_level(logging.INFO):
            service.is_user_allowed("99999")

        assert "user_id=99999" in caplog.text
        assert "allowed=False" in caplog.text

    @mock_aws
    def test_custom_table_name(self):
        """カスタムテーブル名が使用できること"""
        custom_table = "custom-allowed-users"
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        client.create_table(
            TableName=custom_table,
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.put_item(
            TableName=custom_table,
            Item={"user_id": {"S": "111"}},
        )

        service = AllowedUsersService(dynamodb_client=client, table_name=custom_table)
        assert service.is_user_allowed("111") is True
