# セットアップ

[← README に戻る](../README.md)

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

頭脳は [頭脳・独り言・記憶](brain.md) を参照してください。

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

手順は [Buffer の設定と運用](buffer.md) を参照してください。

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
