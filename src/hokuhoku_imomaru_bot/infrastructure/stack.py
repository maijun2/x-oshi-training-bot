"""
AWS CDKスタック定義

DynamoDB、S3、Lambda、EventBridge、Secrets Manager、IAMロールを含む
サーバーレスアーキテクチャを定義します。
"""
from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    BundlingOptions,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct


class ImomaruBotStack(Stack):
    """
    ほくほくいも丸くん育成ボットのCDKスタック
    
    このスタックは以下のリソースを作成します：
    - DynamoDB テーブル（BotState、XPTable）
    - S3 バケット（画像アセット）
    - Secrets Manager シークレット（X API認証情報）
    - Lambda 関数（メインロジック）
    - EventBridge Scheduler（1日2回のトリガー）
    - IAM ロール（最小権限）
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # DynamoDB テーブル: BotState
        # ボットの状態（累積XP、現在レベル、最新Tweet ID、活動カウント）を保存
        self.bot_state_table = dynamodb.Table(
            self,
            "BotStateTable",
            table_name="imomaru-bot-state",
            partition_key=dynamodb.Attribute(
                name="state_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # オンデマンド課金
            encryption=dynamodb.TableEncryption.AWS_MANAGED,  # 保存時の暗号化
            removal_policy=RemovalPolicy.RETAIN,  # 本番環境では削除しない
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),  # ポイントインタイムリカバリを有効化
        )

        # DynamoDB テーブル: XPTable
        # DQ3勇者の経験値テーブル（レベル1〜99）を保存
        self.xp_table = dynamodb.Table(
            self,
            "XPTable",
            table_name="imomaru-bot-xp-table",
            partition_key=dynamodb.Attribute(
                name="level",
                type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # オンデマンド課金
            encryption=dynamodb.TableEncryption.AWS_MANAGED,  # 保存時の暗号化
            removal_policy=RemovalPolicy.RETAIN,  # 本番環境では削除しない
        )

        # S3 バケット: 画像アセット
        # プロフィール画像のベース画像とフォントファイルを保存
        self.assets_bucket = s3.Bucket(
            self,
            "AssetsBucket",
            bucket_name=f"imomaru-bot-assets-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,  # サーバーサイド暗号化（SSE-S3）
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,  # パブリックアクセスをブロック
            removal_policy=RemovalPolicy.RETAIN,  # 本番環境では削除しない
            versioned=False,  # バージョニングは不要
            enforce_ssl=True,  # SSL/TLS接続を強制
        )

        # Secrets Manager: X API認証情報
        # OAuth 1.0a（v1.1用）とBearer Token（v2用）を保存
        self.x_api_secret = secretsmanager.Secret(
            self,
            "XAPISecret",
            secret_name="imomaru-bot/x-api-credentials",
            description="X API認証情報（OAuth 1.0a + Bearer Token）",
            removal_policy=RemovalPolicy.RETAIN,  # 本番環境では削除しない
        )

        # Lambda実行ロール
        # 最小権限の原則に従い、必要な権限のみを付与
        self.lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Imomaru Bot Lambda Execution Role",
            managed_policies=[
                # CloudWatch Logsへの書き込み権限
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # DynamoDB読み書き権限を付与
        self.bot_state_table.grant_read_write_data(self.lambda_role)
        self.xp_table.grant_read_data(self.lambda_role)

        # S3読み取り権限を付与
        self.assets_bucket.grant_read(self.lambda_role)

        # Secrets Manager読み取り権限を付与
        self.x_api_secret.grant_read(self.lambda_role)

        # Bedrock呼び出し権限を付与
        # Claude Haiku 4.5はInference Profile経由でのみ呼び出し可能
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/jp.anthropic.claude-haiku-4-5-20251001-v1:0",
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
                    f"arn:aws:bedrock:ap-northeast-3::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
                ],
            )
        )

        # Lambda関数: メインロジック
        self.bot_lambda = lambda_.Function(
            self,
            "BotLambda",
            function_name="imomaru-bot-handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="hokuhoku_imomaru_bot.lambda_handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_package"),
            role=self.lambda_role,
            timeout=Duration.minutes(3),  # タイムアウト3分
            memory_size=256,
            environment={
                "STATE_TABLE_NAME": self.bot_state_table.table_name,
                "XP_TABLE_NAME": self.xp_table.table_name,
                "ASSETS_BUCKET_NAME": self.assets_bucket.bucket_name,
                "SECRET_NAME": self.x_api_secret.secret_name,
                "OSHI_USER_ID": "",  # デプロイ後に設定
                "GROUP_USER_ID": "",  # デプロイ後に設定
                "BOT_USER_ID": "1794035160897425408",  # ボットのユーザーID
            },
            description="Imomaru Bot - Main Handler",
        )

        # EventBridge Rule: 朝9時（JST）のスケジュール
        # cron(分 時 日 月 曜日 年) - UTCで指定するため、JST 9:00 = UTC 0:00
        self.morning_schedule = events.Rule(
            self,
            "MorningSchedule",
            rule_name="imomaru-bot-morning-schedule",
            schedule=events.Schedule.cron(
                minute="0",
                hour="0",  # UTC 0:00 = JST 9:00
                month="*",
                week_day="*",
                year="*",
            ),
            description="ほくほくいも丸くん - 朝9時（JST）のスケジュール",
        )
        self.morning_schedule.add_target(targets.LambdaFunction(self.bot_lambda))

        # EventBridge Rule: 夜21時（JST）のスケジュール
        # JST 21:00 = UTC 12:00
        self.evening_schedule = events.Rule(
            self,
            "EveningSchedule",
            rule_name="imomaru-bot-evening-schedule",
            schedule=events.Schedule.cron(
                minute="0",
                hour="12",  # UTC 12:00 = JST 21:00
                month="*",
                week_day="*",
                year="*",
            ),
            description="ほくほくいも丸くん - 夜21時（JST）のスケジュール",
        )
        self.evening_schedule.add_target(targets.LambdaFunction(self.bot_lambda))
