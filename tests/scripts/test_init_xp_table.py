"""
DQ3経験値テーブル初期化スクリプトのテスト
"""
import json
import pytest
import boto3
from moto import mock_aws
from pathlib import Path


def get_xp_data_path() -> Path:
    """経験値データJSONファイルのパスを取得"""
    return Path(__file__).parent.parent.parent / "data" / "dq3_xp_table.json"


class TestXPTableData:
    """経験値テーブルデータのテスト"""

    def test_xp_table_json_exists(self):
        """JSONファイルが存在することを確認"""
        json_path = get_xp_data_path()
        assert json_path.exists(), f"{json_path} が存在しません"

    def test_xp_table_has_99_levels(self):
        """99レベル分のデータが存在することを確認"""
        json_path = get_xp_data_path()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        assert len(data["levels"]) == 99

    def test_xp_table_levels_are_sequential(self):
        """レベルが1から99まで連続していることを確認"""
        json_path = get_xp_data_path()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        levels = [item["level"] for item in data["levels"]]
        assert levels == list(range(1, 100))

    def test_xp_table_level_1_requires_0_xp(self):
        """レベル1の必要経験値が0であることを確認"""
        json_path = get_xp_data_path()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        level_1 = next(item for item in data["levels"] if item["level"] == 1)
        assert level_1["required_xp"] == 0

    def test_xp_table_is_monotonically_increasing(self):
        """必要経験値が単調増加していることを確認"""
        json_path = get_xp_data_path()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        xp_values = [item["required_xp"] for item in data["levels"]]
        for i in range(1, len(xp_values)):
            assert xp_values[i] > xp_values[i - 1], \
                f"レベル{i + 1}の経験値({xp_values[i]})がレベル{i}({xp_values[i - 1]})より小さい"


class TestStateStoreLoadXPTable:
    """StateStore.load_xp_table()のテスト"""

    @mock_aws
    def test_load_xp_table_returns_correct_data(self):
        """DynamoDBから正しくデータが読み込まれることを確認"""
        from src.hokuhoku_imomaru_bot.services import StateStore
        
        # DynamoDBテーブルを作成
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        client.create_table(
            TableName="imomaru-bot-xp-table",
            KeySchema=[{"AttributeName": "level", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "level", "AttributeType": "N"}],
            BillingMode="PAY_PER_REQUEST",
        )
        
        # テストデータを投入
        test_data = [
            {"level": 1, "required_xp": 0},
            {"level": 2, "required_xp": 14},
            {"level": 3, "required_xp": 31},
        ]
        for item in test_data:
            client.put_item(
                TableName="imomaru-bot-xp-table",
                Item={
                    "level": {"N": str(item["level"])},
                    "required_xp": {"N": str(item["required_xp"])},
                },
            )
        
        # StateStoreでデータを読み込み
        store = StateStore(client)
        xp_table = store.load_xp_table()
        
        # 検証
        assert len(xp_table) == 3
        assert xp_table[1] == 0
        assert xp_table[2] == 14
        assert xp_table[3] == 31

    @mock_aws
    def test_load_xp_table_with_full_data(self):
        """全99レベルのデータが正しく読み込まれることを確認"""
        from src.hokuhoku_imomaru_bot.services import StateStore
        
        # DynamoDBテーブルを作成
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        client.create_table(
            TableName="imomaru-bot-xp-table",
            KeySchema=[{"AttributeName": "level", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "level", "AttributeType": "N"}],
            BillingMode="PAY_PER_REQUEST",
        )
        
        # JSONからデータを読み込んで投入
        json_path = get_xp_data_path()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        for item in data["levels"]:
            client.put_item(
                TableName="imomaru-bot-xp-table",
                Item={
                    "level": {"N": str(item["level"])},
                    "required_xp": {"N": str(item["required_xp"])},
                },
            )
        
        # StateStoreでデータを読み込み
        store = StateStore(client)
        xp_table = store.load_xp_table()
        
        # 検証
        assert len(xp_table) == 99
        assert xp_table[1] == 0
        assert xp_table[99] == 102093086
