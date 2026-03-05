#!/usr/bin/env python3
"""
プロフィール更新機能のテストスクリプト

OAuth 1.0a署名の修正が正しく動作するかテストします。
実際のX APIを呼び出してプロフィール名とバナー画像を更新します。
"""
import os
import sys
import json
import boto3
import base64
from pathlib import Path
from io import BytesIO

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from hokuhoku_imomaru_bot.clients.x_api_client import XAPIClient
from hokuhoku_imomaru_bot.services.image_compositor import ImageCompositor


def main():
    """プロフィール更新をテスト"""
    print("=" * 60)
    print("プロフィール更新テスト")
    print("=" * 60)
    
    # AWS認証情報を設定
    region = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")
    
    # AWS クライアントを作成
    secrets_client = boto3.client("secretsmanager", region_name=region)
    s3_client = boto3.client("s3", region_name=region)
    
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
    
    # テスト2: プロフィールバナー画像の更新
    print("\n[3] プロフィールバナー画像の更新をテスト...")
    print("   S3からベース画像を取得してレベル表示を合成中...")
    print("   設定: フォントサイズ96px、右から80px、下から80px")
    
    try:
        # ImageCompositorを使用してレベル表示を合成
        # バケット名にアカウントIDが付いている
        account_id = "353695163339"
        bucket_name = f"imomaru-bot-assets-{account_id}"
        
        # 確定した設定でImageCompositorを作成
        compositor = ImageCompositor(
            s3_client=s3_client,
            bucket_name=bucket_name,
            base_image_key="imomaru-banner-base.png",
            font_size=96,  # 確定したフォントサイズ
            padding=80,    # 確定したパディング（右から80px、下から80px）
        )
        
        # レベル13の画像を合成
        image_data = compositor.composite_level_image(13)
        
        # デバッグ用：生成された画像をローカルに保存
        debug_path = project_root / "test_banner_output.png"
        image_data.seek(0)
        with open(debug_path, "wb") as f:
            f.write(image_data.read())
        print(f"   デバッグ: 生成された画像を保存しました → {debug_path}")
        
        # Base64エンコード
        image_data.seek(0)
        image_bytes = image_data.read()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        
        print(f"   画像サイズ: {len(image_bytes)} bytes")
        
        # バナー画像を更新
        result = api_client.update_profile_banner(image_base64)
        print(f"✅ プロフィールバナー画像の更新に成功しました！")
        print(f"   バナーURL: {result.get('profile_banner_url', 'N/A')}")
        
    except Exception as e:
        print(f"❌ プロフィールバナー画像の更新に失敗しました")
        print(f"   エラー: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "=" * 60)
    print("✅ 全てのテストが成功しました！")
    print("=" * 60)
    print("\n確認:")
    print("  1. プロフィール名が「ほくほくいも丸くん🍠Lv.13」になっているか")
    print("  2. トップバナー画像の右下に「Lv.13」が表示されているか")
    print("  3. プロフィールアイコン（丸い画像）は変更されていないか")
    return 0


if __name__ == "__main__":
    sys.exit(main())
