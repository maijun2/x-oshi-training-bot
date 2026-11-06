# 運用監視

[← README に戻る](../README.md)

## CloudWatchダッシュボード

`imomaru-bot-dashboard` でボットの稼働状況をリアルタイムに確認できます。

- **稼働率ゲージ**: 過去24時間の成功率を視覚的に表示
- **Lambda呼び出し回数**: 時間ごとの実行回数
- **Lambdaエラー数**: エラー発生状況
- **Lambda実行時間**: 平均・最大実行時間
- **Lambdaスロットリング**: スロットリング発生状況
- **DynamoDB消費キャパシティ**: 読み書きキャパシティの使用状況
- **アラーム状態**: 各アラームの現在の状態

## CloudWatchアラーム

以下のアラームが設定されており、SNSトピック経由でメール通知されます。

| アラーム名 | 条件 | 説明 |
|-----------|------|------|
| `imomaru-bot-lambda-errors` | エラー数 ≥ 1（5分間） | Lambda関数でエラーが発生 |
| `imomaru-bot-lambda-duration` | 実行時間 ≥ 150秒（5分間） | 実行時間が長すぎる（タイムアウト警告） |
| `imomaru-bot-app-errors` | `[ERROR]`/`[CRITICAL]` ログ ≥ 1（5分間） | try/except で捕捉されたアプリ内エラー（Lambda Errors メトリクスに乗らないもの）。頭脳の呼び出し失敗（`Brain failed …` / `Brain not configured …`）もここで検知 |

## ログの場所

| 対象 | ロググループ |
|------|-------------|
| Lambda | `/aws/lambda/imomaru-bot-handler` |
| 頭脳（AgentCore Runtime） | `/aws/bedrock-agentcore/runtimes/imomaru_brain-<id>-DEFAULT`（`brain task=… model=…` の 1 行と例外のスタックトレース） |
| 推しの記憶（AgentCore Memory） | 書き込みは Lambda のログに `Oshi memory event recorded: <tweet_id>`（失敗は `[ERROR] … oshi_memory_write`）。読み出しは `Brain task=react … memories=N`（N = 頭脳に渡した記憶の件数。失敗は `memories=-1` と `[ERROR] Brain memory recall failed …`）。どちらもアラーム対象 |

```bash
# 直近の実行で頭脳が使われたか（推し投稿が 0 件の回は頭脳を呼ばない）
# 正常: `Brain task=react model=… action=post|skip chars=… memories=N`。
# 異常: `[ERROR] Brain failed …`（反応は skip・素案メールのみ、アラーム）／`[ERROR] Brain memory recall failed …`（記憶なしで反応は続行、アラーム）
LS=$(aws logs describe-log-streams --log-group-name /aws/lambda/imomaru-bot-handler \
  --order-by LastEventTime --descending --limit 1 --query 'logStreams[0].logStreamName' --output text)
aws logs get-log-events --log-group-name /aws/lambda/imomaru-bot-handler --log-stream-name "$LS" \
  --query 'events[].message' --output text | grep -E "brain|Brain|Buffer post queued|ERROR"
```

ログストリームは実行ごとに 1 本（10:0x / 13:1x / 18:0x / 21:0x / 23:58 の 5 本/日）。

## アラーム通知の設定

デプロイ後、SNSトピックにメールアドレスをサブスクライブしてアラーム通知を受け取れます:

```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:ap-northeast-1:ACCOUNT_ID:imomaru-bot-alarms \
  --protocol email \
  --notification-endpoint your-email@example.com \
  --region ap-northeast-1
```

確認メールが届いたら、リンクをクリックして承認してください。
