"""
AllowedUsersServiceのプロパティテスト

Feature: group-quote-removal-and-reply-feature
Property 7: 許可ユーザー検証とリプライ処理
Validates: Requirements 4.1, 4.2, 4.3
"""
import boto3
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws
from src.hokuhoku_imomaru_bot.services.allowed_users_service import AllowedUsersService


TABLE_NAME = "imomaru-bot-allowed-users"

user_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Nd",)),
    min_size=1,
    max_size=20,
).filter(lambda x: x.isdigit())


def _setup_table(dynamodb_client, allowed_user_ids):
    """テーブルを作成し許可ユーザーを登録"""
    dynamodb_client.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    for uid in allowed_user_ids:
        dynamodb_client.put_item(
            TableName=TABLE_NAME,
            Item={"user_id": {"S": uid}},
        )


# Feature: group-quote-removal-and-reply-feature
# Property 7: 許可ユーザー検証とリプライ処理
# For any リプライが検出されたとき、システムはリプライ元ユーザーIDを
# Allowed_Users_Tableで検索し、許可ユーザーの場合のみリプライを処理対象とし、
# 非許可ユーザーの場合はスキップする
@settings(max_examples=100)
@given(
    allowed_ids=st.lists(user_id_st, min_size=0, max_size=10, unique=True),
    query_ids=st.lists(user_id_st, min_size=1, max_size=15),
)
@mock_aws
def test_property_7_allowed_user_verification(allowed_ids, query_ids):
    """
    Property 7: 許可ユーザー検証とリプライ処理

    任意の許可ユーザーリストとクエリユーザーリストに対して:
    - 許可リストに含まれるユーザーIDはTrueを返す
    - 許可リストに含まれないユーザーIDはFalseを返す
    """
    client = boto3.client("dynamodb", region_name="ap-northeast-1")
    _setup_table(client, allowed_ids)

    service = AllowedUsersService(dynamodb_client=client, table_name=TABLE_NAME)
    allowed_set = set(allowed_ids)

    for uid in query_ids:
        result = service.is_user_allowed(uid)
        if uid in allowed_set:
            assert result is True, f"User {uid} should be allowed but got False"
        else:
            assert result is False, f"User {uid} should not be allowed but got True"


# Property 7 補足: 空の許可リストでは全ユーザーが非許可
@settings(max_examples=100)
@given(query_ids=st.lists(user_id_st, min_size=1, max_size=10))
@mock_aws
def test_property_7_empty_allowed_list_rejects_all(query_ids):
    """
    Property 7 補足: 許可リストが空の場合、全ユーザーが非許可

    任意のユーザーIDに対して、許可リストが空なら
    全てFalseを返すこと。
    """
    client = boto3.client("dynamodb", region_name="ap-northeast-1")
    _setup_table(client, [])

    service = AllowedUsersService(dynamodb_client=client, table_name=TABLE_NAME)

    for uid in query_ids:
        assert service.is_user_allowed(uid) is False
