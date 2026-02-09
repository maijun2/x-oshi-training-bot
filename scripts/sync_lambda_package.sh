#!/bin/bash
# lambda_package 同期スクリプト
# src/hokuhoku_imomaru_bot/ → lambda_package/hokuhoku_imomaru_bot/ を同期
# infrastructure/ は Lambda に不要なため除外

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

SRC_DIR="$PROJECT_ROOT/src/hokuhoku_imomaru_bot"
DEST_DIR="$PROJECT_ROOT/lambda_package/hokuhoku_imomaru_bot"

if [ ! -d "$SRC_DIR" ]; then
    echo "❌ ソースディレクトリが見つかりません: $SRC_DIR"
    exit 1
fi

# rsync で同期（infrastructure/ と __pycache__ を除外）
rsync -av --delete \
    --exclude='infrastructure/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "$SRC_DIR/" "$DEST_DIR/"

echo ""
echo "✅ lambda_package 同期完了ｲﾓ🍠"
