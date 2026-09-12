#!/bin/bash
# 頭脳（AgentCore Runtime）のデプロイパッケージ dist/brain.zip を作る
#
# AgentCore Runtime の direct code deploy は Linux arm64 の wheel を要求する。Docker なしで
# クロスプラットフォームに解決するため uv pip install --python-platform を使う。
#   https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html
#
# 出力: dist/brain.zip（stack.py の BRAIN_PACKAGE_PATH。cdk synth 前に必ず実行する）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
AGENT_DIR="$PROJECT_ROOT/agent"
PACKAGE_DIR="$PROJECT_ROOT/agent_package"
DIST_DIR="$PROJECT_ROOT/dist"
ZIP_PATH="$DIST_DIR/brain.zip"
PYTHON_VERSION="3.12"   # stack.py の runtime="PYTHON_3_12" と揃える

rm -rf "$PACKAGE_DIR" "$ZIP_PATH"
mkdir -p "$PACKAGE_DIR" "$DIST_DIR"

echo "📦 依存関係を arm64 wheel で解決中..."
uv pip install \
  --python-platform aarch64-manylinux2014 \
  --python-version "$PYTHON_VERSION" \
  --only-binary=:all: \
  --target "$PACKAGE_DIR" \
  --quiet \
  -r "$AGENT_DIR/requirements.txt"

echo "📄 エージェントコードをコピー中（prompts.py はシンボリックリンクを実体化）..."
cp -L "$AGENT_DIR"/*.py "$PACKAGE_DIR/"

# 別 OS/アーキで生成された bytecode と不要物を除去
find "$PACKAGE_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} +
rm -rf "$PACKAGE_DIR/bin"

# Runtime が要求するパーミッション（ファイル 644 / ディレクトリ 755）
find "$PACKAGE_DIR" -type d -exec chmod 755 {} +
find "$PACKAGE_DIR" -type f -exec chmod 644 {} +

echo "🗜  zip 化中..."
(cd "$PACKAGE_DIR" && zip -qr "$ZIP_PATH" .)

echo ""
echo "✅ 頭脳パッケージ作成完了ｲﾓ🍠: $ZIP_PATH ($(du -h "$ZIP_PATH" | cut -f1)、展開後 $(du -sh "$PACKAGE_DIR" | cut -f1)、上限 250MB / 750MB)"
