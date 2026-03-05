#!/usr/bin/env python3
"""
プロフィール更新機能のテストスクリプト

OAuth 1.0a署名の修正が正しく動作するかテストします。
実際のX APIを呼び出してプロフィール名と画像を更新します。
"""
import os
import sys
import json
import boto3
import base64
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from hokuhoku_imomaru_bot.clients.x_api_client import XAPIClient


def main():
    """プロフィール更新をテスト"""
    print("=" * 60)
    print("プロフィール更新テスト")
    print("=" * 60)
    
    # AWS認証情報を設定
    region = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")
    
    # Secrets Managerクライアントを作成
    secrets_client = boto3.client("secretsmanager", region_name=region)
    
    # X API クライアントを初期化
    print("\n[1] X API クライアントを初期化中...")
    api_client = XAPIClient(secrets_client)
    
    # テスト1: プロフィール名の更新
    print("\n[2] プロフィール名の更新をテスト...")
    test_name = "ほくほくいも丸くん🍠Lv.13"  # 現在のレベル
    
    try:
        result = api_client.update_profile(name=test_name)
        print(f"✅ プロフィール名の更新に成功しました！")
        print(f"   更新後の名前: {result.get('name', 'N/A')}")
        
    except Exception as e:
        print(f"❌ プロフィール名の更新に失敗しました")
        print(f"   エラー: {e}")
        return 1
    
    # テスト2: プロフィール画像の更新
    print("\n[3] プロフィール画像の更新をテスト...")
    
    # 既存のプロフィール画像を使用（base_profile.png）
    image_path = project_root / "base_profile.png"
    
    if not image_path.exists():
        print(f"⚠️  テスト画像が見つかりません: {image_path}")
        print("   プロフィール画像のテストをスキップします")
    else:
        try:
            # 画像を読み込んでBase64エンコード
            with open(image_path, "rb") as f:
                image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")
            
            result = api_client.update_profile_image(image_base64)
            print(f"✅ プロフィール画像の更新に成功しました！")
            print(f"   画像URL: {result.get('profile_image_url_https', 'N/A')}")
            
        except Exception as e:
            print(f"❌ プロフィール画像の更新に失敗しました")
            print(f"   エラー: {e}")
            return 1
    
    print("\n" + "=" * 60)
    print("✅ 全てのテストが成功しました！")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
