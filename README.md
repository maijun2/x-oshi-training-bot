# ほくほくいも丸くん育成ボット 🍠

X（旧Twitter）育成ボット - AWSサーバーレスアーキテクチャ

推しアイドル（甘木ジュリちゃん @juri_bigangel）の投稿を監視し、AI生成された引用ポストでリアクションし、活動に基づいてXPを獲得し、ドラゴンクエストIIIの成長曲線に従ってレベルアップするボットです。

## 機能

- 🔍 **タイムライン監視**: コアタイム4回（10:00/13:00/18:00/21:00 JST ±ゆらぎ）で推し投稿を監視、日報時（23:58 JST）に全処理実行
- 🤖 **AI応答生成**: AgentCore Runtime「頭脳」（Strands ＋ Bedrock Kimi K2.5）でキャラクターに合った応答を生成。頭脳が落ちたら反応は見送り（素案メールのみ）、リプライは固定文
- 📮 **推し投稿への反応（半人力）**: AI応答をSESメールで素案通知しつつ、Buffer のキューに予約投入。Buffer のスロット時刻に自動投稿され、NG なら人間が Buffer から削除（X API 課金 $0）
- 🧠 **推しの記憶**: 検知した推しのオリジナル投稿（引用ポスト含む。RT・リプライ除外）を Amazon Bedrock AgentCore Memory `imomaru_oshi_memory` に Lambda から直接書き込む。事実・好み・エピソードへの長期記憶抽出は Memory 側が非同期に行う。頭脳は反応を作るたびに関連する記憶（事実・好み）を読み出して判断材料にする（2026-09-25〜）
- 🍠 **独り言（自律投稿）**: コアタイムの回に推しの投稿へ反応しなかったら、推しの記憶（近づくイベントのカウントダウン、直近のイベント、これからの活動、推しの好きなもの）から独り言をつくって Buffer に予約投入し（1 日 2 件まで）、根拠にした記憶と一緒に素案メールで通知（2026-09-26〜、全実行は 2026-09-28〜）
- 🎨 **感情別画像添付**: Buffer 予約投入時、頭脳が反応と一緒に返す感情キーに対応するLINEスタンプ画像を添付（1日1回限定）
- ⭐ **XP獲得**: 活動に応じてXPを獲得（推し投稿: 5.0 XP、グループ投稿: 2.0 XP、いいね: 0.1 XP、リポスト: 0.5 XP）
- 📈 **レベルアップ**: DQ3勇者の経験値テーブルに基づいてレベルアップ
- 🖼️ **プロフィール更新**: レベルアップ時にプロフィール画像と名前を自動更新、レベルアップ投稿に画像添付
- 📊 **日報投稿**: 毎日23:58 JST以降に活動報告を投稿
- 💬 **リプライ機能**: 許可ユーザーからボット投稿へのリプライに対してAIが自動応答（冪等性制御・3日チェック付き）
- 💰 **APIコスト最適化**: グループオリジナル投稿の引用ポスト停止（XP加算のみ継続）、エンゲージメントチェックを1日1回に制限

## アーキテクチャ

```
EventBridge Scheduler → Lambda → X API (日報・レベルアップ・リプライ)
                          ├→ SES (推し投稿への応答素案メール)
                          ├→ Buffer API (推し投稿への応答・独り言を予約投入 → Buffer が X に投稿)
                          ↓
                    DynamoDB (状態管理・許可ユーザー・処理済みリプライ・独り言の投稿履歴)
                          ↓
                    AgentCore Runtime「頭脳」(Strands + Bedrock Kimi K2.5: 反応の提案〔本文・感情キー・post/skip〕・独り言の提案・リプライ応答)
                          └→ 失敗時は反応を見送り（Buffer に入れず素案メールのみ）、アラーム
                          ↓
                    AgentCore Memory「推しの記憶」(推し投稿を Lambda 直で書き込み。Semantic/UserPreference/Episodic で抽出。頭脳が react ごとに retrieve、独り言は Lambda が facts / preferences を一覧して材料を選ぶ)
                          ↓
                    S3 (画像アセット)
                          ↓
                    CloudWatch (監視・アラーム)
```

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [セットアップ](docs/setup.md) | AWS へのデプロイ、X API・SES・画像・マスタの初期設定 |
| [Buffer](docs/buffer.md) | Buffer の認証情報、スロット、キャップ、予約投稿の運用 |
| [頭脳・独り言・記憶](docs/brain.md) | AgentCore Runtime、独り言、AgentCore Memory |
| [運用監視](docs/operations.md) | ダッシュボード、アラーム、ログの場所 |
| [投稿ルール](docs/bot-rules.md) | スケジュール、投稿パターン、XP レート |

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

## プロジェクト構造

```
.
├── app.py                          # CDKアプリケーションエントリーポイント
├── cdk.json                        # CDK設定
├── pyproject.toml                  # Python依存関係
├── docs/                           # 詳細ドキュメント
├── data/
│   └── dq3_xp_table.json          # DQ3経験値テーブルデータ
├── agent/                          # 頭脳（AgentCore Runtime）のコード
│   ├── main.py                    # エントリポイント（BedrockAgentCoreApp）
│   ├── brain.py                   # Strands Agent による 3 タスク（react / autonomous / reply_response）＋ 推しの記憶の retrieve
│   ├── prompts.py                 # → src/hokuhoku_imomaru_bot/prompts.py へのシンボリックリンク
│   ├── memory_filters.py          # → src/hokuhoku_imomaru_bot/memory_filters.py へのシンボリックリンク
│   └── requirements.txt           # Runtime の依存（strands-agents / bedrock-agentcore）
├── scripts/
│   ├── init_xp_table.py           # 経験値テーブル初期化スクリプト
│   ├── init_emotion_images.py     # 感情画像マスタ初期化スクリプト
│   ├── build_agent_package.sh     # 頭脳のデプロイパッケージ（dist/brain.zip）作成
│   ├── sync_lambda_package.sh     # Lambda パッケージ同期スクリプト
│   ├── test_brain_invoke.py       # 頭脳の本番疎通確認
│   ├── autonomous_candidates.py   # 独り言の材料選びの確認（読み取り専用、--brain でローカル頭脳）
│   ├── test_buffer_post.py        # Buffer キューへの投入・削除の動作確認
│   └── buffer_status.py           # Buffer の予約投稿（状態・本文）とスロットの確認（読み取り専用）
├── src/
│   └── hokuhoku_imomaru_bot/
│       ├── __init__.py
│       ├── lambda_handler.py      # Lambdaメインハンドラー
│       ├── prompts.py             # プロンプト定義（Lambda と頭脳の単一ソース）
│       ├── memory_filters.py      # 推しの記憶の除外語・イベント語・日付抽出（Lambda と頭脳の単一ソース）
│       ├── clients/               # 外部APIクライアント
│       ├── infrastructure/        # CDKスタック定義
│       ├── models/                # データモデル
│       ├── services/              # ビジネスロジック
│       └── utils/                 # ユーティリティ
└── tests/                         # テストコード
```
