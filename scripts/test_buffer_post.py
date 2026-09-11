#!/usr/bin/env python3
"""
Buffer 予約投入の実機確認スクリプト

本番の Buffer キューに 1 件投入し、返却された post id / 予約時刻 / 添付画像の URL を表示する。
初回導入時の確認項目:
  - createPost がスキーマどおりに通るか
  - 感情画像（公開バケットの URL）が添付されるか。Buffer は投稿公開時に URL を取りに来る（実測 2026-09-12）ので、
    公開後に X 側で画像が付いているかまで確認する
  - 公開後に元ツイート URL が埋め込みカードとして展開されるか（設計書 §9-11。公開まで残した場合）

使い方:
    # 画像なしで投入（キャップ・状態には触れない）
    python scripts/test_buffer_post.py --text "テストｲﾓ🍠" --tweet-id 1234567890

    # 感情画像付きで投入
    python scripts/test_buffer_post.py --text "テストｲﾓ🍠" --tweet-id 1234567890 --emotion cheer

    # 後片付け（キューから削除）
    python scripts/test_buffer_post.py --delete <post_id>

認証情報は Secrets Manager `imomaru-bot/buffer-api` から読む（トークンは表示しない）。
"""
import argparse
import os
import sys
from pathlib import Path

import boto3

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from hokuhoku_imomaru_bot.clients.buffer_client import BufferClient  # noqa: E402
from hokuhoku_imomaru_bot.services.state_store import StateStore  # noqa: E402
from hokuhoku_imomaru_bot.services.buffer_scheduler import (  # noqa: E402
    BufferScheduler,
    EMOTION_IMAGE_ALT_TEXT,
)

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
SECRET_NAME = os.environ.get("BUFFER_SECRET_NAME", "imomaru-bot/buffer-api")
PUBLIC_BUCKET_NAME = os.environ.get("PUBLIC_ASSETS_BUCKET_NAME", "imomaru-bot-public-assets-353695163339")
PUBLIC_BASE_URL = f"https://{PUBLIC_BUCKET_NAME}.s3.{REGION}.amazonaws.com"
OSHI_USERNAME = os.environ.get("OSHI_USERNAME", "juri_bigangel")


def main() -> int:
    parser = argparse.ArgumentParser(description="Buffer 予約投入の実機確認")
    parser.add_argument("--text", help="投稿本文（URL なし）")
    parser.add_argument("--tweet-id", help="元ツイート ID（本文末尾に x.com URL を付ける）")
    parser.add_argument("--emotion", help="感情キー（例: cheer）。指定時は S3 の画像を添付")
    parser.add_argument("--delete", metavar="POST_ID", help="指定 ID の投稿をキューから削除")
    args = parser.parse_args()

    secrets_client = boto3.client("secretsmanager", region_name=REGION)
    buffer_client = BufferClient(secrets_client=secrets_client, secret_name=SECRET_NAME)

    if args.delete:
        ok = buffer_client.delete_post(args.delete)
        print("🗑️  削除:", "成功" if ok else "失敗")
        return 0 if ok else 1

    if not args.text or not args.tweet_id:
        parser.error("--text と --tweet-id は必須です（--delete 以外）")

    state_store = StateStore(dynamodb_client=boto3.client("dynamodb", region_name=REGION))
    scheduler = BufferScheduler(
        buffer_client=buffer_client,
        state_store=state_store,
        public_image_base_url=PUBLIC_BASE_URL,
        oshi_username=OSHI_USERNAME,
        daily_cap=1,
    )

    text = scheduler.build_post_text(args.text, args.tweet_id)
    image_url = scheduler.build_emotion_image_url(args.emotion) if args.emotion else None
    if args.emotion and not image_url:
        print(f"❌ 感情キー {args.emotion} の画像 URL を作れませんでした")
        return 1

    print("📤 Buffer に投入します")
    print("   本文:\n" + "\n".join(f"     {line}" for line in text.splitlines()))
    print(f"   画像: {image_url if image_url else 'なし'}")

    post = buffer_client.add_to_queue(
        text=text,
        image_url=image_url,
        alt_text=EMOTION_IMAGE_ALT_TEXT if image_url else None,
    )

    print("✅ 投入完了")
    print(f"   post id : {post.id}")
    print(f"   dueAt   : {post.due_at} (UTC)")
    if post.due_at:
        from datetime import timedelta, timezone

        print(f"   予約 JST: {post.due_at.astimezone(timezone(timedelta(hours=9)))}")
    if image_url:
        if post.asset_urls:
            print(f"   assets  : {post.asset_urls[0][:120]}")
        else:
            print("   ⚠️ assets が空で返りました（画像は添付されていません）")
    print(f"\n後片付け: python scripts/test_buffer_post.py --delete {post.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
