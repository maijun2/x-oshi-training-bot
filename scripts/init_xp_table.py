#!/usr/bin/env python3
"""
DQ3経験値テーブルをDynamoDBに投入するスクリプト

使用方法:
    uv run python scripts/init_xp_table.py [--table-name TABLE_NAME] [--region REGION]

オプション:
    --table-name: DynamoDBテーブル名（デフォルト: imomaru-bot-xp-table）
    --region: AWSリージョン（デフォルト: ap-northeast-1）
    --dry-run: 実際には投入せず、投入予定のデータを表示
"""
import argparse
import json
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def load_xp_data(json_path: Path) -> list[dict]:
    """JSONファイルから経験値データを読み込む"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["levels"]


def batch_write_items(dynamodb_client, table_name: str, items: list[dict]) -> int:
    """
    DynamoDBにバッチ書き込み（25件ずつ）
    
    Returns:
        書き込んだアイテム数
    """
    written_count = 0
    batch_size = 25  # DynamoDBのバッチ書き込み上限
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        request_items = {
            table_name: [
                {
                    "PutRequest": {
                        "Item": {
                            "level": {"N": str(item["level"])},
                            "required_xp": {"N": str(item["required_xp"])},
                        }
                    }
                }
                for item in batch
            ]
        }
        
        response = dynamodb_client.batch_write_item(RequestItems=request_items)
        
        # 未処理アイテムの再試行
        unprocessed = response.get("UnprocessedItems", {})
        retry_count = 0
        while unprocessed and retry_count < 3:
            response = dynamodb_client.batch_write_item(RequestItems=unprocessed)
            unprocessed = response.get("UnprocessedItems", {})
            retry_count += 1
        
        if unprocessed:
            print(f"警告: {len(unprocessed.get(table_name, []))}件のアイテムが書き込めませんでした")
        
        written_count += len(batch)
        print(f"進捗: {written_count}/{len(items)} 件完了")
    
    return written_count


def main():
    parser = argparse.ArgumentParser(description="DQ3経験値テーブルをDynamoDBに投入")
    parser.add_argument(
        "--table-name",
        default="imomaru-bot-xp-table",
        help="DynamoDBテーブル名（デフォルト: imomaru-bot-xp-table）",
    )
    parser.add_argument(
        "--region",
        default="ap-northeast-1",
        help="AWSリージョン（デフォルト: ap-northeast-1）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際には投入せず、投入予定のデータを表示",
    )
    args = parser.parse_args()
    
    # JSONファイルのパス
    script_dir = Path(__file__).parent
    json_path = script_dir.parent / "data" / "dq3_xp_table.json"
    
    if not json_path.exists():
        print(f"エラー: {json_path} が見つかりません")
        sys.exit(1)
    
    # データ読み込み
    print(f"経験値データを読み込み中: {json_path}")
    xp_data = load_xp_data(json_path)
    print(f"読み込んだレベル数: {len(xp_data)}")
    
    if args.dry_run:
        print("\n=== ドライラン: 投入予定のデータ ===")
        for item in xp_data[:5]:
            print(f"  Level {item['level']}: {item['required_xp']} XP")
        print(f"  ... (他 {len(xp_data) - 5} 件)")
        print(f"\nテーブル名: {args.table_name}")
        print(f"リージョン: {args.region}")
        return
    
    # DynamoDBクライアント作成
    print(f"\nDynamoDBに接続中（リージョン: {args.region}）...")
    dynamodb = boto3.client("dynamodb", region_name=args.region)
    
    # テーブル存在確認
    try:
        dynamodb.describe_table(TableName=args.table_name)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print(f"エラー: テーブル '{args.table_name}' が存在しません")
            print("先にCDKでスタックをデプロイしてください")
            sys.exit(1)
        raise
    
    # データ投入
    print(f"\nテーブル '{args.table_name}' にデータを投入中...")
    written = batch_write_items(dynamodb, args.table_name, xp_data)
    
    print(f"\n完了: {written} 件のレベルデータを投入しました")


if __name__ == "__main__":
    main()
