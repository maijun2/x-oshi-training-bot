# ほくほくいも丸くん育成ボット 🍠

X（旧Twitter）育成ボット - AWSサーバーレスアーキテクチャ

推しアイドル（甘木ジュリさん @juri_bigangel）の投稿を監視し、AI生成された引用ポストでリアクションし、活動に基づいてXPを獲得し、ドラゴンクエストIIIの成長曲線に従ってレベルアップするボットです。

## 機能

- 🔍 **タイムライン監視**: 1日2回（9:00/21:00 JST）推しとグループの投稿をチェック
- 🤖 **AI応答生成**: Amazon Bedrock（Claude Haiku 4.5）でキャラクターに合った応答を生成
- 🎨 **感情別画像添付**: 推し投稿への引用ポスト時、AI応答の感情を分類してLINEスタンプ画像を添付（1日1回限定）
- ⭐ **XP獲得**: 活動に応じてXPを獲得（推し投稿: 5.0 XP、グループ投稿: 2.0 XP、いいね: 0.1 XP、リポスト: 0.5 XP）
- 📈 **レベルアップ**: DQ3勇者の経験値テーブルに基づいてレベルアップ
- 🖼️ **プロフィール更新**: レベルアップ時にプロフィール画像と名前を自動更新、レベルアップ投稿に画像添付
- 📊 **日報投稿**: 毎日21:00 JST以降に活動報告を投稿

## アーキテクチャ

```
EventBridge Scheduler → Lambda → X API
                          ↓
                    DynamoDB (状態管理)
                          ↓
                    Bedrock (AI生成)
                          ↓
                    S3 (画像アセット)
```

## 前提条件

- macOS / Linux
- Python 3.12
- Node.js 20以上
- AWS CLI（設定済み）
- uv（Python パッケージマネージャー）

## ローカル開発環境のセットアップ

### 1. uvのインストール

```bash
# macOS (Homebrew)
brew install uv

# または pip
pip install uv
```

### 2. Python仮想環境の作成

```bash
# Python 3.12の仮想環境を作成
uv venv --python 3.12

# 仮想環境をアクティベート
source .venv/bin/activate
```

### 3. 依存関係のインストール

```bash
# pyproject.tomlから依存関係をインストール
uv pip install -e ".[dev]"
```

### 4. テストの実行

```bash
# すべてのテストを実行
uv run pytest

# カバレッジ付きで実行
uv run pytest --cov

# 特定のテストを実行
uv run pytest tests/services/test_xp_calculator.py -v
```

## AWSへのデプロイ

### 1. 環境変数の設定

`.env.example`をコピーして`.env`ファイルを作成し、XアカウントのユーザーIDを設定:

```bash
cp .env.example .env
```

`.env`ファイルを編集:

```bash
# 推しのXアカウントユーザーID
OSHI_USER_ID=1234567890123456789

# グループ/ユニットのXアカウントユーザーID
GROUP_USER_ID=9876543210987654321

# ボット自身のXアカウントユーザーID
BOT_USER_ID=1111111111111111111
```

**注意**: 
- これらはXのユーザーIDです。ユーザー名（@xxx）ではありません。
- `BOT_USER_ID` はボット自身の投稿へのエンゲージメント（いいね・リポスト）を追跡するために使用します。
- `.env`ファイルは`.gitignore`で除外されているため、リポジトリにはコミットされません。

### 2. CDKブートストラップ（初回のみ）

```bash
# 東京リージョン（ap-northeast-1）にブートストラップ
uv run npx cdk bootstrap aws://ACCOUNT_ID/ap-northeast-1
```

### 3. CDKスタックのデプロイ

```bash
# スタックをsynthesizeして確認
uv run npx cdk synth

# デプロイ（.envの環境変数が自動的にLambdaに設定されます）
uv run npx cdk deploy

# 変更差分を確認
uv run npx cdk diff
```

## デプロイ後の設定

### 1. X API認証情報の設定

AWS Secrets Managerで `imomaru-bot/x-api-credentials` シークレットを更新:

```bash
aws secretsmanager put-secret-value \
  --secret-id imomaru-bot/x-api-credentials \
  --secret-string '{
    "api_key": "YOUR_API_KEY",
    "api_key_secret": "YOUR_API_KEY_SECRET",
    "access_token": "YOUR_ACCESS_TOKEN",
    "access_token_secret": "YOUR_ACCESS_TOKEN_SECRET",
    "bearer_token": "YOUR_BEARER_TOKEN"
  }' \
  --region ap-northeast-1
```

### 2. S3へのベース画像アップロード

```bash
aws s3 cp base_profile.png s3://imomaru-bot-assets-ACCOUNT_ID/base_profile.png --region ap-northeast-1
```

### 3. DQ3経験値テーブルの初期化

```bash
AWS_DEFAULT_REGION=ap-northeast-1 uv run python scripts/init_xp_table.py
```

### 4. 感情画像マスタの初期化

```bash
AWS_DEFAULT_REGION=ap-northeast-1 uv run python scripts/init_emotion_images.py
```

### 5. S3への感情画像アップロード

感情別画像を`emotions/`プレフィックス内にアップロード:

```bash
aws s3 cp emotions/ s3://imomaru-bot-assets-ACCOUNT_ID/emotions/ --recursive --region ap-northeast-1
```

## プロジェクト構造

```
.
├── app.py                          # CDKアプリケーションエントリーポイント
├── cdk.json                        # CDK設定
├── pyproject.toml                  # Python依存関係
├── data/
│   └── dq3_xp_table.json          # DQ3経験値テーブルデータ
├── scripts/
│   ├── init_xp_table.py           # 経験値テーブル初期化スクリプト
│   └── init_emotion_images.py     # 感情画像マスタ初期化スクリプト
├── src/
│   └── hokuhoku_imomaru_bot/
│       ├── __init__.py
│       ├── lambda_handler.py      # Lambdaメインハンドラー
│       ├── clients/               # 外部APIクライアント
│       ├── infrastructure/        # CDKスタック定義
│       ├── models/                # データモデル
│       ├── services/              # ビジネスロジック
│       └── utils/                 # ユーティリティ
└── tests/                         # テストコード
```

## XPレートと投稿ルール

| 活動タイプ | XP | 引用ポスト |
|-----------|-----|-----------|
| 推しオリジナル投稿 | 5.0 | AI生成応答（感情画像添付あり※） |
| 推し引用リポスト | 5.0 | AI生成応答（感情画像添付あり※） |
| 推しリツイート | 0.5 | なし（XP加算のみ） |
| グループオリジナル投稿 | 2.0 | AI生成応答 |
| グループ引用リポスト | 2.0 | AI生成応答 |
| グループリツイート | 0.5 | なし（XP加算のみ） |
| ボット投稿へのリポスト | 0.5 | なし |
| ボット投稿へのいいね | 0.1 | なし |

※感情画像添付は1日1回限定

## ライセンス

MIT License
