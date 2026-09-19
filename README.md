# ほくほくいも丸くん育成ボット 🍠

X（旧Twitter）育成ボット - AWSサーバーレスアーキテクチャ

推しアイドル（甘木ジュリさん @juri_bigangel）の投稿を監視し、AI生成された引用ポストでリアクションし、活動に基づいてXPを獲得し、ドラゴンクエストIIIの成長曲線に従ってレベルアップするボットです。

## 機能

- 🔍 **タイムライン監視**: コアタイム4回（10:00/13:00/18:00/21:00 JST ±ゆらぎ）で推し投稿を監視、日報時（23:58 JST）に全処理実行
- 🤖 **AI応答生成**: AgentCore Runtime「頭脳」（Strands ＋ Bedrock Kimi K2.5）でキャラクターに合った応答を生成。頭脳が落ちたら Bedrock Claude Haiku 4.5 直呼びにフォールバック
- 📮 **推し投稿への反応（半人力）**: AI応答をSESメールで素案通知しつつ、Buffer のキューに予約投入。Buffer のスロット時刻に自動投稿され、NG なら人間が Buffer から削除（X API 課金 $0）
- 🧠 **推しの記憶（書き込み）**: 検知した推しのオリジナル投稿（引用ポスト含む。RT・リプライ除外）を Amazon Bedrock AgentCore Memory `imomaru_oshi_memory` に Lambda から直接書き込む。事実・好み・エピソードへの長期記憶抽出は Memory 側が非同期に行う（頭脳からの読み出しは次フェーズ）
- 🎨 **感情別画像添付**: Buffer 予約投入時、AI応答の感情を分類してLINEスタンプ画像を添付（1日1回限定）
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
                          ├→ Buffer API (推し投稿への応答を予約投入 → Buffer が X に投稿)
                          ↓
                    DynamoDB (状態管理・許可ユーザー・処理済みリプライ)
                          ↓
                    AgentCore Runtime「頭脳」(Strands + Bedrock Kimi K2.5: 応答生成・感情分類)
                          └→ 失敗時は Lambda が Bedrock Haiku を直接呼ぶ（フォールバック）
                          ↓
                    AgentCore Memory「推しの記憶」(推し投稿を Lambda 直で書き込み。Semantic/UserPreference/Episodic で抽出)
                          ↓
                    S3 (画像アセット)
                          ↓
                    CloudWatch (監視・アラーム)
```

## 運用監視

### CloudWatchダッシュボード

`imomaru-bot-dashboard` でボットの稼働状況をリアルタイムに確認できます。

- **稼働率ゲージ**: 過去24時間の成功率を視覚的に表示
- **Lambda呼び出し回数**: 時間ごとの実行回数
- **Lambdaエラー数**: エラー発生状況
- **Lambda実行時間**: 平均・最大実行時間
- **Lambdaスロットリング**: スロットリング発生状況
- **DynamoDB消費キャパシティ**: 読み書きキャパシティの使用状況
- **アラーム状態**: 各アラームの現在の状態

### CloudWatchアラーム

以下のアラームが設定されており、SNSトピック経由でメール通知されます。

| アラーム名 | 条件 | 説明 |
|-----------|------|------|
| `imomaru-bot-lambda-errors` | エラー数 ≥ 1（5分間） | Lambda関数でエラーが発生 |
| `imomaru-bot-lambda-duration` | 実行時間 ≥ 150秒（5分間） | 実行時間が長すぎる（タイムアウト警告） |
| `imomaru-bot-app-errors` | `[ERROR]`/`[CRITICAL]` ログ ≥ 1（5分間） | try/except で捕捉されたアプリ内エラー（Lambda Errors メトリクスに乗らないもの）。頭脳の呼び出し失敗（`Brain failed …` → Haiku フォールバック）もここで検知 |

### ログの場所

| 対象 | ロググループ |
|------|-------------|
| Lambda | `/aws/lambda/imomaru-bot-handler` |
| 頭脳（AgentCore Runtime） | `/aws/bedrock-agentcore/runtimes/imomaru_brain-<id>-DEFAULT`（`brain task=… model=…` の 1 行と例外のスタックトレース） |
| 推しの記憶（AgentCore Memory） | Lambda のログに `Oshi memory event recorded: <tweet_id>`。失敗は `[ERROR] … oshi_memory_write`（アラーム対象） |

```bash
# 直近の実行で頭脳が使われたか（推し投稿が 0 件の回は頭脳を呼ばない）
# 正常: `Brain task=react model=… action=post|skip chars=…`。異常: `[ERROR] Brain failed …`（Haiku フォールバック、アラーム）
LS=$(aws logs describe-log-streams --log-group-name /aws/lambda/imomaru-bot-handler \
  --order-by LastEventTime --descending --limit 1 --query 'logStreams[0].logStreamName' --output text)
aws logs get-log-events --log-group-name /aws/lambda/imomaru-bot-handler --log-stream-name "$LS" \
  --query 'events[].message' --output text | grep -E "brain|Brain|Buffer post queued|ERROR"
```

ログストリームは実行ごとに 1 本（10:0x / 13:1x / 18:0x / 21:0x / 23:58 の 5 本/日）。

### アラーム通知の設定

デプロイ後、SNSトピックにメールアドレスをサブスクライブしてアラーム通知を受け取れます:

```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:ap-northeast-1:ACCOUNT_ID:imomaru-bot-alarms \
  --protocol email \
  --notification-endpoint your-email@example.com \
  --region ap-northeast-1
```

確認メールが届いたら、リンクをクリックして承認してください。

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

# 素案メールの宛先（SES で検証済みのアドレス）
NOTIFICATION_EMAIL=you@example.com

# 素案メールの送信ドメインと送信元（任意。設定手順は「デプロイ後の設定 1-c」）
SES_SENDER_DOMAIN=example.net
FROM_EMAIL=imomaru@example.net
```

**注意**: 
- これらはXのユーザーIDです。ユーザー名（@xxx）ではありません。
- `BOT_USER_ID` はボット自身の投稿へのエンゲージメント（いいね・リポスト）を追跡するために使用します。
- `FROM_EMAIL` が空なら `NOTIFICATION_EMAIL` から送ります（宛先＝送信元）。宛先が Gmail だと
  「自分のアカウントからの送信に見えるが確認できない」警告が出るため、独自ドメインからの送信を推奨します。
- `.env`ファイルは`.gitignore`で除外されているため、リポジトリにはコミットされません。

### 2. CDKブートストラップ（初回のみ）

```bash
# 東京リージョン（ap-northeast-1）にブートストラップ
uv run npx cdk bootstrap aws://ACCOUNT_ID/ap-northeast-1
```

### 3. CDKスタックのデプロイ

```bash
# 頭脳（AgentCore Runtime）のデプロイパッケージ dist/brain.zip を作る（arm64 wheel、Docker 不要）
bash scripts/build_agent_package.sh

# Lambda パッケージを src/ から同期する（CDK は lambda_package/ を見る）
bash scripts/sync_lambda_package.sh

# 変更差分を確認
uv run npx cdk diff

# デプロイ（.envの環境変数が自動的にLambdaに設定されます）
uv run npx cdk deploy
```

### 4. 頭脳（AgentCore Runtime）

推し投稿への反応とリプライ応答は、Lambda から Amazon Bedrock AgentCore Runtime `imomaru_brain`
（Strands Agent）に依頼して生成します（フェーズ2a、2026-09-12。2b-2-1 で `react` に統合、2026-09-16）。

| タスク | 入力 | 出力 |
|------|------|------|
| `react` | 投稿本文 ＋ 時刻情報（投稿時刻・現在時刻・公開予定＝次の Buffer 枠、JST） | JSON 提案 `{"action": "post"\|"skip", "text", "emotion_key", "reason"}`。`skip` なら Lambda は Buffer に入れず、理由をメールに載せる |
| `reply_response` | 許可ユーザーのリプライ本文・元投稿 | 応答文 |

「考える頭脳・実行する Lambda」（設計書 §10-11）: 頭脳は提案を返すだけで、140 字整形・感情キー検証・Buffer／メール・キャップは Lambda が決定論で行います。
時刻情報は Buffer 予約制で「検知 → 公開」に数時間のラグがあるため、公開時刻に合った挨拶・時制（「昨夜の〜」）にするためのものです。

| 項目 | 内容 |
|------|------|
| デプロイ方式 | direct code deploy（`dist/brain.zip`、`PYTHON_3_12`、arm64）。`agent/` 配下のコードと `agent/requirements.txt` を `scripts/build_agent_package.sh` が zip 化し、CDK が S3 アセットとして配置 |
| モデル | Runtime の環境変数 `BRAIN_MODEL_ID`（`stack.py` の `BRAIN_MODEL_ID`）。既定 `moonshotai.kimi-k2.5`（東京 In-Region）。差し替えは値を変えて `cdk deploy` するだけ。Grok 4.6 はこのアカウントでは提供制限（`AccessDeniedException … not available for this account`）のため未使用 |
| 呼び出し | Lambda の `AIGenerator` → `utils/brain_client.py`（`bedrock-agentcore:InvokeAgentRuntime`）。Lambda 1 回の実行で 1 セッションを使い回す。Runtime 側の Agent はリクエストごとに使い捨て |
| フォールバック | 頭脳の呼び出しに失敗（JSON 提案の形が崩れた場合も含む）すると `[ERROR] Brain failed …` を出して（アラーム発火）Bedrock Haiku 4.5 直呼び（応答生成 → 感情分類の 2 段）に切り替える。`BRAIN_RUNTIME_ARN` が空なら直呼びのみ |
| 公開予定時刻 | Lambda env `BUFFER_SLOT_TIMES_JST`（Buffer UI のスロット時刻の写し、既定 `08:00,11:15,12:15,14:15,15:15,19:15,20:15,22:00`）から現在時刻の次の枠を算出して頭脳に渡す。Buffer UI で枠を変えたらこの値も合わせる |
| プロンプト | `src/hokuhoku_imomaru_bot/prompts.py` が単一ソース（`agent/prompts.py` はそのシンボリックリンク）。キャラクター定義は system prompt、反応対象は user message |
| 本文の体裁 | 1 文 1 行 ＋ 空行 ＋ ハッシュタグ（最終行）。プロンプトで指示しつつ、Lambda 側 `AIGenerator.format_post_text` が文末「ｲﾓ🍠」を境に機械的に整える（モデルが 1 行で返しても保証）。整形後に改行込みで 140 字に切り詰める（2026-09-15） |
| ログ | `/aws/bedrock-agentcore/runtimes/imomaru_brain-*` |

```bash
# ローカルで頭脳を起動して確認（Bedrock を実際に呼びます）
uv run python agent/main.py
curl -X POST localhost:8080/invocations -H 'Content-Type: application/json' \
  -d '{"task":"react","input":{"post_content":"今日はライブでした！","post_type":"oshi","posted_at":"2026-09-16(水) 01:42 JST","now":"2026-09-16(水) 10:07 JST","publish_at":"2026-09-16(水) 11:15 JST"}}'

# deploy 後の本番疎通確認（2 タスクを 1 回ずつ invoke）
uv run python scripts/test_brain_invoke.py
# react の JSON 提案の安定性（パース成功率・action の分布）
uv run python scripts/test_brain_invoke.py --task react --runs 5
```

**クレジット相殺の確認**（モデルカードに Marketplace 文言がない ＝ AWS 販売 ＝ クレジット対象。**Kimi K2.5 は 2026-09-19 に実請求で確認済み**:
09-12〜18 の `APN1-moonshotai.kimi-k2.5-{input,output}-tokens` は Usage $0.064 に対し Credit −$0.064 で全額相殺）:

```bash
# Kimi の USAGE_TYPE を Usage / Credit に分けて見る（Credit が Usage と同額の負数なら相殺されている）
aws ce get-cost-and-usage --region us-east-1 \
  --time-period Start=2026-09-12,End=2026-09-19 --granularity MONTHLY --metrics UnblendedCost \
  --filter '{"Dimensions":{"Key":"USAGE_TYPE","Values":["APN1-moonshotai.kimi-k2.5-input-tokens","APN1-moonshotai.kimi-k2.5-output-tokens"]}}' \
  --group-by Type=DIMENSION,Key=RECORD_TYPE
```

### 5. 推しの記憶（AgentCore Memory）

検知した推しの投稿を Amazon Bedrock AgentCore Memory `imomaru_oshi_memory` に書き込みます（フェーズ3a-write、2026-09-13）。
いも丸が「推しのことを覚える」ための記憶で、いも丸自身の人格（システムプロンプト）とは分離しています。

| 項目 | 内容 |
|------|------|
| リソース | CDK `CfnMemory`（`stack.py` の `_create_oshi_memory`）。削除時は保持（RETAIN）。イベント保持 365 日 |
| 戦略 | Semantic `/oshi/{actorId}/facts/`（事実）／ User Preference `/oshi/{actorId}/preferences/`（好み・口調）／ Episodic `/oshi/{actorId}/episodes/`（1 日 1 セッションのエピソード＋reflection） |
| 書き込み | `services/oshi_memory_writer.py`。actorId = 推しの X ユーザー名、sessionId = `oshi-YYYY-MM-DD`（JST）、role = USER、`clientToken` = tweet_id（冪等）。対象は `filter_original_posts` 後の推し投稿（引用ポスト含む） |
| 失敗時 | `[ERROR]` ログ（`imomaru-bot-app-errors` で検知）を出して握りつぶし、XP・Buffer・日報は続行。`OSHI_MEMORY_ID` が空なら書き込みなし |

```bash
MEM=$(aws cloudformation describe-stacks --stack-name ImomaruBotStack \
  --query "Stacks[0].Outputs[?OutputKey=='OshiMemoryId'].OutputValue" --output text)

# 今日書き込まれた推しの投稿（短期記憶）
aws bedrock-agentcore list-events --memory-id "$MEM" --actor-id juri_bigangel \
  --session-id "oshi-$(TZ=Asia/Tokyo date +%F)" --query 'events[].payload[0].conversational.content.text' --output text

# 抽出された長期記憶（事実／好み／エピソード）
for ns in facts preferences episodes; do
  aws bedrock-agentcore list-memory-records --memory-id "$MEM" --namespace "/oshi/juri_bigangel/$ns/" \
    --query 'memoryRecordSummaries[].content.text' --output text
done
```

運用上の注意（2026-09-13 の稼働初日に確認）:

- **イベントは削除・再投入しない**。長期記憶レコードと元イベントを削除して同じ sessionId に再投入しても再抽出されない（セッションごとに処理済み位置を持つと推定）。見出しや本文の形式を変えるときは、変更後の新しい投稿から効くものと考える
- **イベント本文の見出しは「本人の投稿」と書く**。`[推し @xxx の投稿]` のように書くと抽出器が USER ＝ 推しについて語るファンと解釈し、facts が「ユーザーの推し @xxx は…」、preferences が「ユーザーは @xxx を推している」のようにファン側の記憶として残る。現在の形式は `[@juri_bigangel（甘木ジュリ）本人の投稿 YYYY-MM-DD HH:MM JST]`
- **Episodic は会話タスク向けの抽出器**。推しの投稿だけを USER ロールで入れると「ユーザーが指示なしに投稿を貼り付けた」というエージェント視点の reflection になる。推しの記憶として読むのは facts / preferences を主にする
- 長期記憶戦略は Memory 作成時に全部入れておく。後から追加した戦略は追加前のイベントを処理しない
- **ファン視点のレコードが混ざる**（2026-09-14〜18 の実績）。本文がリンク主体の投稿（TikTok 共有）が入るたびに facts の「ユーザーは @juri_bigangel … を運営しており」が統合・更新され、preferences にも「ユーザーは … 閲覧・引用・転載」形式が出る。本人視点の facts（「甘木ジュリ（@juri_bigangel）は…」）は安定して抽出される。読み出し（3a-read）では「ユーザーは」で始まり「閲覧」「転載」「運営」を含むレコードを除外する前提

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

### 1-b. Buffer API認証情報の設定

Buffer の Settings → API → Personal Access で発行した Personal Access Token と、投稿先チャンネルの ID を
`imomaru-bot/buffer-api` シークレットに格納します（値はチャット・ログ・リポジトリに出さないこと）。

```bash
# 値はファイル経由で渡す（シェル履歴に残さない）
cat > /tmp/buffer-secret.json <<'JSON'
{
  "access_token": "YOUR_BUFFER_PERSONAL_ACCESS_TOKEN",
  "channel_id": "YOUR_CHANNEL_ID",
  "organization_id": "YOUR_ORGANIZATION_ID"
}
JSON
aws secretsmanager put-secret-value \
  --secret-id imomaru-bot/buffer-api \
  --secret-string file:///tmp/buffer-secret.json \
  --region ap-northeast-1
rm /tmp/buffer-secret.json
```

`channel_id` / `organization_id` は Buffer GraphQL API（`POST https://api.buffer.com`、
`Authorization: Bearer <token>`）で `account { organizations { id } }` →
`channels(input: {organizationId: ...}) { id name service }` を実行して取得します。
参考: https://developers.buffer.com/guides/getting-started.html

**運用パラメータ（Lambda 環境変数、`stack.py` で設定）**

| 変数 | 初期値 | 意味 |
|------|--------|------|
| `BUFFER_RUN_CAP` | `1` | **主キャップ**。Lambda 1 回の実行で Buffer へ予約投入する上限件数。超えた分はメール素案のみ（X Intent リンクから手動投稿可）。各実行の検知分が均等に Buffer に載るよう「1日合計」ではなく「実行ごと」で数える |
| `BUFFER_DAILY_CAP` | `7` | **安全弁**。1日の投入上限。スロット数/日（8）より小さくしてキューが必ず毎日減るようにし、Buffer 無料枠（キュー 10 件）を溢れさせない。`BUFFER_RUN_CAP` を上げるときはこの値とスロット数も見直す |
| `FROM_EMAIL` | `NOTIFICATION_EMAIL` と同じ | 素案メールの送信元。独自ドメインの認証後に `.env` で設定する（「デプロイ後の設定 1-c」） |
| `BUFFER_SLOT_TIMES_JST` | `08:00,11:15,12:15,14:15,15:15,19:15,20:15,22:00` | Buffer UI のスロット時刻（JST）の**名目値**。頭脳に渡す「公開予定時刻」（現在時刻の次の枠）の見込み計算にだけ使い、実際の予約時刻は Buffer が決める。実スロットは曜日ごとに名目値から ±数分ずらしてある（最大 12 分差）ので完全一致はしない。UI で枠の時間帯そのものを変えたら合わせる |
| `PUBLIC_ASSETS_BUCKET_NAME` | CDK が設定 | 感情画像の公開バケット（`imomaru-bot-public-assets-<account>`）。Buffer は**投稿公開時**に画像 URL を取りに来るため、署名付き URL ではなく公開 URL が必要 |

**Buffer 側のスロット設定（予約時刻は Buffer に任せる）**

- 投稿時刻はボット側で計算せず、Buffer チャンネルの posting schedule（スロット）に `addToQueue` で載せます。
  スロットは Buffer の Settings → Posting Schedule で変更でき、deploy 不要です
- レビュー猶予はスロットまでの時間です。スロットは**全曜日 8 枠**、名目値 `08:00 11:15 12:15 14:15 15:15 19:15 20:15 22:00` JST
  （2026-09-12 設定、2026-09-19 に 21:15 → 22:00。夜の実行 21:00 の追加に合わせた）。
  実際の UI 設定は機械的に見えないよう曜日ごとに名目値から ±数分ずらしてある（2026-09-19、下表）。設計原則は次の 2 つ:
  1. 各 Lambda 実行（10:00 / 13:00 / 18:00 / 21:00、flexible window はそれぞれ +15 / +23 / +3 / +5 分）の後、
     最初のスロットまで **レビュー猶予 50 分以上** を空ける
  2. 各実行の後、**当日中に `BUFFER_RUN_CAP`（1）枠以上**残す → 日中に検知した分が翌日に繰り越さない
     （23:58 実行の検知分だけは構造上、翌 08:00 になる）

  | Lambda 実行（最遅） | 当日の残りスロット（名目） | 猶予（最悪ケース。実スロットの最短で計算） |
  |---|---|---|
  | 23:58 | 翌 08:00〜 | 一晩 |
  | 10:00（10:15） | 11:15 12:15 14:15 15:15 19:15 20:15 22:00 | 57 分（Mon 11:12） |
  | 13:00（13:23） | 14:15 15:15 19:15 20:15 22:00 | 54 分（Wed/Sat 14:17） |
  | 18:00（18:03） | 19:15 20:15 22:00 | 70 分（Fri 19:13） |
  | 21:00（21:05） | 22:00 | 56 分（Thu 22:01） |

  実スロット（Buffer UI、JST。名目値の行に対応）:

  | 名目 | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
  |---|---|---|---|---|---|---|---|
  | 08:00 | 08:03 | 08:01 | 08:02 | 08:03 | 08:01 | 08:03 | 08:05 |
  | 11:15 | 11:12 | 11:20 | 11:14 | 11:23 | 11:17 | 11:19 | 11:16 |
  | 12:15 | 12:17 | 12:16 | 12:14 | 12:11 | 12:05 | 12:08 | 12:21 |
  | 14:15 | 14:21 | 14:24 | 14:17 | 14:20 | 14:18 | 14:17 | 14:20 |
  | 15:15 | 15:18 | 15:17 | 15:16 | 15:12 | 15:20 | 15:03 | 15:07 |
  | 19:15 | 19:16 | 19:18 | 19:17 | 19:14 | 19:13 | 19:20 | 19:18 |
  | 20:15 | 20:17 | 20:16 | 20:15 | 20:21 | 20:10 | 20:07 | 20:05 |
  | 22:00 | 22:04 | 22:02 | 22:03 | 22:01 | 22:04 | 22:02 | 22:05 |

  スロットをずらすときの上限: 原則 1 を守るため、11:xx は 11:05 より、14:xx は 14:13 より、19:xx は 18:53 より、22:xx は 21:55 より早くしない。
  `BUFFER_SLOT_TIMES_JST` は曜日別の値を持てないので名目値のまま。頭脳に渡す見込み時刻は最大 12 分ずれるが「HH:MM 頃」表現なので実害なし
  （名目値と実スロットの隙間に Lambda 実行時刻帯が掛からないことも確認済み）。

  Buffer はキューが空のスロットを素通りし、投入された投稿は「投入時点より後の最初の空き枠」に先着順で入ります。
  日報とレベルアップ告知は X API 直投稿で Buffer を通りません。Buffer に載るのは推し投稿への引用だけです
- スロット数/日（8）> `BUFFER_DAILY_CAP`（7）にしておくとキューが滞留しません（この不等式は崩さないこと）
- 実測（2026-08-13〜09-12 の 30 日）: 推しのオリジナル投稿は平均 6.6 件/日。実行別の平均は 10:00 → 2.3、13:00 → 1.0、
  18:00 → 0.7、23:58 → 2.7 件。`BUFFER_RUN_CAP=1` で実効 3 件/日程度。夜の実行 21:00 は 2026-09-19 に追加済み（18:00→23:58 の検知空白を埋める）。増やすなら `BUFFER_RUN_CAP=2` が次の段階（当日中に残り枠 ≥ キャップ、8 枠 > 日次キャップの不等式は維持）
- スロットは Buffer の公開 API では変更できません（GraphQL は `Channel.postingSchedule` の読み取りのみ。
  旧 REST API は Public API トークンを拒否）。変更は Buffer の Web UI で行い、API で読み直して検証します。
  読み出しは `BufferClient._graphql` に次のクエリを投げる（`channel_id` はシークレットの値）:
  スロット `channel(input:{id}){postingSchedule{day times paused}}`（`times` は `"HH:MM"` の配列）、
  投稿の状態 `post(input:{id}){id status dueAt sentAt text}`（`status` は `sent` / `scheduled` 等。id はログの `Buffer post queued: id=…`）
- 動作確認済み（2026-09-12）: Buffer 経由の投稿で感情画像が添付され、末尾の x.com URL は X 側で引用ポストとして展開される

**動作確認**

```bash
# 本番の Buffer キューに 1 件投入して post id / 予約時刻 / 画像コピー状況を表示
uv run python scripts/test_buffer_post.py --text "テストｲﾓ🍠" --tweet-id <推しの投稿ID> --emotion cheer
# 後片付け
uv run python scripts/test_buffer_post.py --delete <post_id>
```

### 1-c. SES 送信ドメインの認証（素案メールを独自ドメインから送る）

素案メールの From を `NOTIFICATION_EMAIL`（＝宛先）のままにすると、Gmail は「自分のアカウントから送信されたように
見えるが確認できない」警告を出します。gmail.com として SES を認証する手段はないので、保有ドメインを SES に登録し、
Easy DKIM とカスタム MAIL FROM で DMARC 整合させてから From を切り替えます。
DNS が Route53 外（例: mixhost）でも、既存ゾーンにレコードを **追加するだけ** で済みます（既存の SPF / DKIM / DMARC / MX は触らない）。

**手順は 2 段階**。ドメインの DMARC が `p=quarantine` 以上だと、認証が通る前に From を切り替えた時点でスパム行きになるため、順序を守ること。

1. `.env` に `SES_SENDER_DOMAIN=<domain>` を設定（`FROM_EMAIL` はまだ空のまま）して `cdk deploy`。
   Outputs に DNS 登録用の 5 レコードが出ます:

   | Output | 種別 | 名前 | 値 |
   |---|---|---|---|
   | `SesDkimCname1〜3` | CNAME | `<token>._domainkey.<domain>` | `<token>.dkim.amazonses.com` |
   | `SesMailFromMx` | MX | `ses.<domain>` | `10 feedback-smtp.ap-northeast-1.amazonses.com` |
   | `SesMailFromSpf` | TXT | `ses.<domain>` | `v=spf1 include:amazonses.com ~all` |

   MAIL FROM を `ses.<domain>` サブドメインにするのは、root の SPF に `include:amazonses.com` を足して
   lookup 数（上限 10）を消費しないため。DMARC が relaxed alignment（`aspf=r`、既定）ならサブドメインで整合します
2. 5 レコードを DNS に追加し、検証が通るのを待つ（数分〜1 時間）:

   ```bash
   aws sesv2 get-email-identity --email-identity <domain> --region ap-northeast-1 \
     --query '{dkim:DkimAttributes.Status,mailFrom:MailFromAttributes.MailFromDomainStatus,verified:VerifiedForSendingStatus}'
   # dkim: SUCCESS / mailFrom: SUCCESS / verified: true になるまで次へ進まない
   ```
3. `.env` に `FROM_EMAIL=<local-part>@<domain>` を設定して `cdk deploy`（Lambda 環境変数だけ変わる）。
   送信元アドレスの受信箱は不要（ドメイン Identity なのでアドレス個別の検証も不要）
4. 次のメールで Gmail の警告が消えていること、「メッセージのソースを表示」で SPF / DKIM / DMARC が PASS であることを確認

ロールバックは `.env` の `FROM_EMAIL` を空にして `cdk deploy`（Identity は残してよい）。
参考: [Easy DKIM](https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dkim-easy.html) /
[カスタム MAIL FROM](https://docs.aws.amazon.com/ses/latest/dg/mail-from.html)

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

感情別画像を **公開バケット** の `emotions/` プレフィックス内にアップロード（Buffer が投稿公開時に取得する）:

```bash
aws s3 sync ./emotions/ s3://imomaru-bot-public-assets-ACCOUNT_ID/emotions/
```

※ 従来の `imomaru-bot-assets-ACCOUNT_ID/emotions/` は参照されなくなった（残っていても無害）。

### 6. 許可ユーザーリストの初期化

リプライ機能の対象ユーザーをDynamoDBに登録:

```bash
source .venv/bin/activate && python3 -c "
import boto3
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
table = dynamodb.Table('imomaru-bot-allowed-users')
table.put_item(Item={
    'user_id': 'USER_ID',
    'username': 'USERNAME',
    'added_date': '2026-03-01',
    'notes': 'メモ'
})
"
```

## プロジェクト構造

```
.
├── app.py                          # CDKアプリケーションエントリーポイント
├── cdk.json                        # CDK設定
├── pyproject.toml                  # Python依存関係
├── data/
│   └── dq3_xp_table.json          # DQ3経験値テーブルデータ
├── agent/                          # 頭脳（AgentCore Runtime）のコード
│   ├── main.py                    # エントリポイント（BedrockAgentCoreApp）
│   ├── brain.py                   # Strands Agent による 2 タスク（react / reply_response）
│   ├── prompts.py                 # → src/hokuhoku_imomaru_bot/prompts.py へのシンボリックリンク
│   └── requirements.txt           # Runtime の依存（strands-agents / bedrock-agentcore）
├── scripts/
│   ├── init_xp_table.py           # 経験値テーブル初期化スクリプト
│   ├── init_emotion_images.py     # 感情画像マスタ初期化スクリプト
│   ├── build_agent_package.sh     # 頭脳のデプロイパッケージ（dist/brain.zip）作成
│   ├── sync_lambda_package.sh     # Lambda パッケージ同期スクリプト
│   ├── test_brain_invoke.py       # 頭脳の本番疎通確認
│   └── test_buffer_post.py        # Buffer キューへの投入・削除の動作確認
├── src/
│   └── hokuhoku_imomaru_bot/
│       ├── __init__.py
│       ├── lambda_handler.py      # Lambdaメインハンドラー
│       ├── prompts.py             # プロンプト定義（Lambda と頭脳の単一ソース）
│       ├── clients/               # 外部APIクライアント
│       ├── infrastructure/        # CDKスタック定義
│       ├── models/                # データモデル
│       ├── services/              # ビジネスロジック
│       └── utils/                 # ユーティリティ
└── tests/                         # テストコード
```

## スケジュールと投稿パターン

| 時刻 | 実行モード | 投稿内容 | 条件 |
|------|-----------|---------|------|
| 朝10時（+0〜15分） | core_time | 推しタイムライン監視・応答素案メール＋Buffer予約投入・リプライ検出 | 毎日 |
| 昼13時（+0〜23分） | core_time | 推しタイムライン監視・応答素案メール＋Buffer予約投入・リプライ検出 | 毎日 |
| 夕方18時（+0〜3分） | core_time | 推しタイムライン監視・応答素案メール＋Buffer予約投入・リプライ検出 | 毎日 |
| 夜21時（+0〜5分） | core_time | 同上。EventBridge 入力に `autonomous_allowed: true` を付ける（推し投稿が無い夜に記憶から自律投稿する 3b-1 用。現時点の Lambda は未使用） | 毎日 |
| 23:58（+0〜1分） | daily_report | 全処理（推し+グループ監視・リプライ検出・エンゲージメント・日報） | 毎日（エンゲージメントは1日1回） |

## XPレートと投稿ルール

| 活動タイプ | XP | 引用ポスト |
|-----------|-----|-----------|
| 推しオリジナル投稿 | 5.0 | AI生成応答（感情画像添付あり※） |
| 推し引用リポスト | 5.0 | なし（XP加算のみ。引用元の文脈を AI が読めず応答がズレるため 2026-09-12 に停止） |
| 推しリプライ（他者宛・ツリー2件目以降） | 0.0 | なし（検知対象外） |
| 推しリツイート | 0.5 | なし（XP加算のみ） |
| グループオリジナル投稿 | 2.0 | なし（コスト削減のため停止） |
| グループ引用リポスト | 2.0 | なし（XP加算のみ） |
| グループリツイート | 0.5 | なし（XP加算のみ） |
| ボット投稿へのリポスト | 0.5 | なし |
| ボット投稿へのいいね | 0.1 | なし |
| 許可ユーザーからのリプライ | 0.0 | AI生成リプライ応答 |

※感情画像添付は1日1回限定（Buffer 予約投入に成功したときのみカウント）。推し投稿への応答は Buffer 経由で投稿されるため X API の Create 課金は発生しない