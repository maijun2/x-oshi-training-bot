"""
AWS CDKスタック定義

DynamoDB、S3、Lambda、EventBridge、Secrets Manager、IAMロールを含む
サーバーレスアーキテクチャを定義します。
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import json
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
    aws_scheduler as scheduler,
    aws_cloudwatch as cloudwatch,
    aws_logs as logs,
    aws_sns as sns,
    aws_cloudwatch_actions as cw_actions,
    aws_s3_assets as s3_assets,
    aws_bedrockagentcore as agentcore,
    CfnOutput,
)
from constructs import Construct

# 頭脳（AgentCore Runtime）の設定
BRAIN_RUNTIME_NAME = "imomaru_brain"
# 既定モデル。Grok 4.6 はこのアカウントでは提供制限（AccessDenied）のため Kimi K2.5（東京 In-Region）。
# 差し替えは Runtime の環境変数 BRAIN_MODEL_ID を変えて deploy するだけ
BRAIN_MODEL_ID = "moonshotai.kimi-k2.5"
BRAIN_PACKAGE_PATH = "dist/brain.zip"  # scripts/build_agent_package.sh が生成


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

        # .envファイルから環境変数を読み込む
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        load_dotenv(env_path)
        
        # XアカウントユーザーIDを環境変数から取得
        oshi_user_id = os.getenv("OSHI_USER_ID", "")
        oshi_username = os.getenv("OSHI_USERNAME", "")
        group_user_id = os.getenv("GROUP_USER_ID", "")
        bot_user_id = os.getenv("BOT_USER_ID", "")
        notification_email = os.getenv("NOTIFICATION_EMAIL", "")

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

        # DynamoDB テーブル: ProcessedTweets（冪等性制御用）
        # 処理済みツイートIDを保存し、二重処理を防止
        self.processed_tweets_table = dynamodb.Table(
            self,
            "ProcessedTweetsTable",
            table_name="imomaru-bot-processed-tweets",
            partition_key=dynamodb.Attribute(
                name="tweet_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # オンデマンド課金
            encryption=dynamodb.TableEncryption.AWS_MANAGED,  # 保存時の暗号化
            removal_policy=RemovalPolicy.RETAIN,  # 本番環境では削除しない
            time_to_live_attribute="ttl",  # TTL属性を有効化（24時間後に自動削除）
        )

        # DynamoDB テーブル: EmotionImages（感情別画像マスタ）
        # 感情キーと対応する画像ファイル名を保存
        self.emotion_images_table = dynamodb.Table(
            self,
            "EmotionImagesTable",
            table_name="imomaru-bot-emotion-images",
            partition_key=dynamodb.Attribute(
                name="emotion_key",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # オンデマンド課金
            encryption=dynamodb.TableEncryption.AWS_MANAGED,  # 保存時の暗号化
            removal_policy=RemovalPolicy.RETAIN,  # 本番環境では削除しない
        )

        # DynamoDB テーブル: AllowedUsers（許可ユーザーリスト）
        # リプライ機能の対象ユーザーを管理
        self.allowed_users_table = dynamodb.Table(
            self,
            "AllowedUsersTable",
            table_name="imomaru-bot-allowed-users",
            partition_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # オンデマンド課金
            encryption=dynamodb.TableEncryption.AWS_MANAGED,  # 保存時の暗号化
            removal_policy=RemovalPolicy.RETAIN,  # 本番環境では削除しない
        )

        # DynamoDB テーブル: ProcessedReplies（処理済みリプライ）
        # リプライの冪等性制御用（TTL: 60日）
        self.processed_replies_table = dynamodb.Table(
            self,
            "ProcessedRepliesTable",
            table_name="imomaru-bot-processed-replies",
            partition_key=dynamodb.Attribute(
                name="tweet_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # オンデマンド課金
            encryption=dynamodb.TableEncryption.AWS_MANAGED,  # 保存時の暗号化
            removal_policy=RemovalPolicy.RETAIN,  # 本番環境では削除しない
            time_to_live_attribute="ttl",  # TTL属性を有効化（60日後に自動削除）
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

        # S3 バケット: 公開アセット（感情画像）
        # Buffer は投稿公開時に画像 URL を取りに来るため、署名なしで読める公開 URL が必要。
        # 公開するのはスタンプ画像だけなので専用バケットに分離し、assets_bucket は BLOCK_ALL のまま維持する
        self.public_assets_bucket = s3.Bucket(
            self,
            "PublicAssetsBucket",
            bucket_name=f"imomaru-bot-public-assets-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ACLS_ONLY,  # バケットポリシーによる公開読み取りのみ許可
            removal_policy=RemovalPolicy.RETAIN,
            versioned=False,
            enforce_ssl=True,
        )
        self.public_assets_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="PublicReadEmotionImages",
                effect=iam.Effect.ALLOW,
                principals=[iam.AnyPrincipal()],
                actions=["s3:GetObject"],
                resources=[self.public_assets_bucket.arn_for_objects("emotions/*")],
            )
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

        # Secrets Manager: Buffer API認証情報
        # Personal Access Token と投稿先チャンネルID を保存（値は put-secret-value で手動投入）
        self.buffer_api_secret = secretsmanager.Secret(
            self,
            "BufferAPISecret",
            secret_name="imomaru-bot/buffer-api",
            description="Buffer API認証情報（Personal Access Token + channel ID）",
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
        self.processed_tweets_table.grant_read_write_data(self.lambda_role)
        self.emotion_images_table.grant_read_data(self.lambda_role)
        self.allowed_users_table.grant_read_data(self.lambda_role)  # 許可ユーザーテーブル読み取り
        self.processed_replies_table.grant_read_write_data(self.lambda_role)  # 処理済みリプライテーブル読み書き

        # S3読み取り権限を付与
        self.assets_bucket.grant_read(self.lambda_role)

        # Secrets Manager読み取り権限を付与
        self.x_api_secret.grant_read(self.lambda_role)
        self.buffer_api_secret.grant_read(self.lambda_role)

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

        # SES 送信権限を付与（検証済みメールアドレスへの送信のみ許可）
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=[
                    f"arn:aws:ses:{self.region}:{self.account}:identity/{notification_email}",
                ],
            )
        )

        # 頭脳: AgentCore Runtime（direct code deploy）
        self.brain_runtime = self._create_brain_runtime()
        brain_runtime_arn = self.brain_runtime.attr_agent_runtime_arn
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=[brain_runtime_arn, f"{brain_runtime_arn}/runtime-endpoint/*"],
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
            timeout=Duration.minutes(5),  # 頭脳（Runtime）呼び出しを投稿ごとに行うため 3 分 → 5 分
            memory_size=256,
            environment={
                "STATE_TABLE_NAME": self.bot_state_table.table_name,
                "XP_TABLE_NAME": self.xp_table.table_name,
                "PROCESSED_TWEETS_TABLE_NAME": self.processed_tweets_table.table_name,
                "EMOTION_IMAGES_TABLE_NAME": self.emotion_images_table.table_name,
                "ALLOWED_USERS_TABLE_NAME": self.allowed_users_table.table_name,
                "PROCESSED_REPLIES_TABLE_NAME": self.processed_replies_table.table_name,
                "ASSETS_BUCKET_NAME": self.assets_bucket.bucket_name,
                "SECRET_NAME": self.x_api_secret.secret_name,
                "BUFFER_SECRET_NAME": self.buffer_api_secret.secret_name,
                "BUFFER_RUN_CAP": "1",  # 1回の実行あたりの Buffer 予約投入件数の上限（主キャップ）
                "BUFFER_DAILY_CAP": "7",  # 1日の上限（安全弁。スロット 8 枠/日より小さくして無料枠10件を溢れさせない）
                "PUBLIC_ASSETS_BUCKET_NAME": self.public_assets_bucket.bucket_name,
                "BRAIN_RUNTIME_ARN": brain_runtime_arn,  # 頭脳。空なら Bedrock 直呼びのみ
                "OSHI_USER_ID": oshi_user_id,
                "OSHI_USERNAME": oshi_username,
                "GROUP_USER_ID": group_user_id,
                "BOT_USER_ID": bot_user_id,
                "NOTIFICATION_EMAIL": notification_email,
                "FROM_EMAIL": notification_email,
            },
            description="Imomaru Bot - Main Handler",
        )

        # EventBridge Scheduler用IAMロール
        self.scheduler_role = iam.Role(
            self,
            "SchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
            description="EventBridge Scheduler Role for Imomaru Bot",
        )
        self.bot_lambda.grant_invoke(self.scheduler_role)

        # Core Time Schedules（3つ）: 推しタイムライン監視に集中
        core_time_configs = [
            ("Morning", 10, 15),    # 10:00 JST, 15分ウィンドウ
            ("Afternoon", 13, 23),  # 13:00 JST, 23分ウィンドウ
            ("Evening", 18, 3),     # 18:00 JST, 3分ウィンドウ
        ]
        for name, hour_jst, window_min in core_time_configs:
            scheduler.CfnSchedule(
                self,
                f"CoreTime{name}Schedule",
                schedule_expression=f"cron(0 {hour_jst} * * ? *)",
                schedule_expression_timezone="Asia/Tokyo",
                flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                    mode="FLEXIBLE",
                    maximum_window_in_minutes=window_min,
                ),
                target=scheduler.CfnSchedule.TargetProperty(
                    arn=self.bot_lambda.function_arn,
                    role_arn=self.scheduler_role.role_arn,
                    input=json.dumps({"execution_mode": "core_time"}),
                ),
                description=f"ほくほくいも丸くん - コアタイム{name}（{hour_jst}:00 JST ±{window_min}分）",
            )

        # Daily Report Schedule（1つ）: 23:58 JST固定、全処理実行
        scheduler.CfnSchedule(
            self,
            "DailyReportSchedule",
            schedule_expression="cron(58 23 * * ? *)",
            schedule_expression_timezone="Asia/Tokyo",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                mode="FLEXIBLE",
                maximum_window_in_minutes=1,
            ),
            target=scheduler.CfnSchedule.TargetProperty(
                arn=self.bot_lambda.function_arn,
                role_arn=self.scheduler_role.role_arn,
                input=json.dumps({"execution_mode": "daily_report"}),
            ),
            description="ほくほくいも丸くん - 日報（23:58 JST）",
        )

        # ========================================
        # CloudWatch ダッシュボード & アラーム
        # ========================================

        # SNSトピック: アラーム通知用
        self.alarm_topic = sns.Topic(
            self,
            "AlarmTopic",
            topic_name="imomaru-bot-alarms",
            display_name="Imomaru Bot Alarms",
        )

        # Lambda エラーアラーム
        self.lambda_error_alarm = cloudwatch.Alarm(
            self,
            "LambdaErrorAlarm",
            alarm_name="imomaru-bot-lambda-errors",
            alarm_description="Lambda関数でエラーが発生しました",
            metric=self.bot_lambda.metric_errors(
                period=Duration.minutes(5),
                statistic="Sum",
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        self.lambda_error_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        # Lambda タイムアウトアラーム（実行時間が2分30秒を超えた場合）
        self.lambda_duration_alarm = cloudwatch.Alarm(
            self,
            "LambdaDurationAlarm",
            alarm_name="imomaru-bot-lambda-duration",
            alarm_description="Lambda関数の実行時間が長すぎます",
            metric=self.bot_lambda.metric_duration(
                period=Duration.minutes(5),
                statistic="Maximum",
            ),
            threshold=150000,  # 150秒（2分30秒）
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        self.lambda_duration_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        # アプリ内エラーアラーム（ログベース）
        # try/except で捕捉したエラーは Lambda の Errors メトリクスに乗らないため、
        # ランタイムが付与する [ERROR] / [CRITICAL] プレフィックスをメトリクスフィルタで拾う。
        # ロググループは Lambda が自動作成するものを参照する（bot_lambda.log_group は
        # LogRetention カスタムリソースを生やすため使わない）
        bot_lambda_log_group = logs.LogGroup.from_log_group_name(
            self,
            "BotLambdaLogGroup",
            "/aws/lambda/imomaru-bot-handler",
        )
        self.app_error_metric_filter = logs.MetricFilter(
            self,
            "AppErrorMetricFilter",
            log_group=bot_lambda_log_group,
            metric_namespace="ImomaruBot",
            metric_name="AppErrors",
            filter_pattern=logs.FilterPattern.any_term("[ERROR]", "[CRITICAL]"),
            metric_value="1",
            default_value=0,
        )
        self.app_error_alarm = cloudwatch.Alarm(
            self,
            "AppErrorAlarm",
            alarm_name="imomaru-bot-app-errors",
            alarm_description="アプリケーション内で捕捉されたエラーがログに記録されました",
            metric=self.app_error_metric_filter.metric(
                period=Duration.minutes(5),
                statistic="Sum",
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        self.app_error_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        # CloudWatch ダッシュボード
        self.dashboard = cloudwatch.Dashboard(
            self,
            "BotDashboard",
            dashboard_name="imomaru-bot-dashboard",
        )

        # 稼働率ゲージウィジェット（成功率を表示）- 左側に大きく配置
        # MathExpressionを使用して成功率を計算: (呼び出し数 - エラー数) / 呼び出し数 * 100
        success_rate_widget = cloudwatch.GaugeWidget(
            title="稼働率 (過去24時間)",
            metrics=[
                cloudwatch.MathExpression(
                    expression="IF(invocations > 0, (invocations - errors) / invocations * 100, 100)",
                    using_metrics={
                        "invocations": self.bot_lambda.metric_invocations(
                            period=Duration.seconds(300),
                            statistic="Sum",
                        ),
                        "errors": self.bot_lambda.metric_errors(
                            period=Duration.seconds(300),
                            statistic="Sum",
                        ),
                    },
                    label="成功率 (%)",
                ),
            ],
            left_y_axis=cloudwatch.YAxisProps(
                min=0,
                max=100,
            ),
            width=8,
            height=12,
        )

        # アラームステータスウィジェット - 右上
        alarm_status_widget = cloudwatch.AlarmStatusWidget(
            title="アラーム状態",
            alarms=[
                self.lambda_error_alarm,
                self.lambda_duration_alarm,
                self.app_error_alarm,
            ],
            width=16,
            height=3,
        )

        # Lambda メトリクスウィジェット - 右側に配置
        lambda_invocations_widget = cloudwatch.GraphWidget(
            title="Lambda 呼び出し回数",
            left=[
                self.bot_lambda.metric_invocations(
                    period=Duration.hours(1),
                    statistic="Sum",
                ),
            ],
            width=8,
            height=4,
        )

        lambda_errors_widget = cloudwatch.GraphWidget(
            title="Lambda エラー数",
            left=[
                self.bot_lambda.metric_errors(
                    period=Duration.hours(1),
                    statistic="Sum",
                ),
            ],
            width=8,
            height=4,
        )

        lambda_duration_widget = cloudwatch.GraphWidget(
            title="Lambda 実行時間 (ms)",
            left=[
                self.bot_lambda.metric_duration(
                    period=Duration.hours(1),
                    statistic="Average",
                ),
                self.bot_lambda.metric_duration(
                    period=Duration.hours(1),
                    statistic="Maximum",
                ),
            ],
            width=8,
            height=5,
        )

        lambda_throttles_widget = cloudwatch.GraphWidget(
            title="Lambda スロットリング",
            left=[
                self.bot_lambda.metric_throttles(
                    period=Duration.hours(1),
                    statistic="Sum",
                ),
            ],
            width=8,
            height=5,
        )

        # DynamoDB メトリクスウィジェット - 下段
        dynamodb_consumed_widget = cloudwatch.GraphWidget(
            title="DynamoDB 消費キャパシティ (BotState)",
            left=[
                self.bot_state_table.metric_consumed_read_capacity_units(
                    period=Duration.hours(1),
                    statistic="Sum",
                ),
                self.bot_state_table.metric_consumed_write_capacity_units(
                    period=Duration.hours(1),
                    statistic="Sum",
                ),
            ],
            width=24,
            height=5,
        )

        # ダッシュボードにウィジェットを追加
        # 1行目: 稼働率ゲージ(左) + アラーム状態(右上)
        self.dashboard.add_widgets(
            cloudwatch.Column(success_rate_widget),
            cloudwatch.Column(
                alarm_status_widget,
                cloudwatch.Row(lambda_invocations_widget, lambda_errors_widget),
                cloudwatch.Row(lambda_duration_widget, lambda_throttles_widget),
            ),
        )
        # 2行目: DynamoDBメトリクス
        self.dashboard.add_widgets(dynamodb_consumed_widget)

    def _create_brain_runtime(self) -> agentcore.CfnRuntime:
        """
        頭脳: AgentCore Runtime を direct code deploy（zip）で構築する

        - コードは scripts/build_agent_package.sh が作る dist/brain.zip（arm64 wheel 同梱）
        - 実行ロールは公式「direct deploy execution role」＋ モデル呼び出し ＋ zip の読み取り
          https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html
        - Lambda 側は attr_agent_runtime_arn を BRAIN_RUNTIME_ARN として受け取る
        """
        brain_code = s3_assets.Asset(self, "BrainCode", path=BRAIN_PACKAGE_PATH)

        runtime_log_group_arn = (
            f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/*"
        )
        brain_role = iam.Role(
            self,
            "BrainRuntimeRole",
            role_name="imomaru-brain-runtime-role",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:*"},
                },
            ),
            description="Execution role for the imomaru brain (AgentCore Runtime)",
            # inline にして Role リソース単体で権限が揃うようにする（Runtime 作成時の依存を単純化）
            inline_policies={
                "BrainRuntimePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["logs:DescribeLogStreams", "logs:CreateLogGroup"],
                            resources=[runtime_log_group_arn],
                        ),
                        iam.PolicyStatement(
                            actions=["logs:PutResourcePolicy"],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/{BRAIN_RUNTIME_NAME}-*"
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=["logs:DescribeLogGroups"],
                            resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:*"],
                        ),
                        iam.PolicyStatement(
                            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                            resources=[f"{runtime_log_group_arn}:log-stream:*"],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "xray:PutTraceSegments",
                                "xray:PutTelemetryRecords",
                                "xray:GetSamplingRules",
                                "xray:GetSamplingTargets",
                            ],
                            resources=["*"],
                        ),
                        iam.PolicyStatement(
                            actions=["cloudwatch:PutMetricData"],
                            resources=["*"],
                            conditions={"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}},
                        ),
                        iam.PolicyStatement(
                            sid="GetAgentAccessToken",
                            actions=[
                                "bedrock-agentcore:GetWorkloadAccessToken",
                                "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                                "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
                            ],
                            resources=[
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/default",
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/default/workload-identity/{BRAIN_RUNTIME_NAME}-*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="BedrockModelInvocation",
                            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                            resources=[
                                # In-Region モデル、CRIS 用の inference profile、モデルによって要求される default project
                                "arn:aws:bedrock:*::foundation-model/*",
                                f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/*",
                                f"arn:aws:bedrock:{self.region}:{self.account}:project/default",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="ReadDeploymentPackage",
                            actions=["s3:GetObject", "s3:GetObjectVersion"],
                            resources=[f"arn:aws:s3:::{brain_code.s3_bucket_name}/{brain_code.s3_object_key}"],
                        ),
                    ]
                )
            },
        )

        runtime = agentcore.CfnRuntime(
            self,
            "BrainRuntime",
            agent_runtime_name=BRAIN_RUNTIME_NAME,
            description="Imomaru brain: Strands agent generating responses (phase 2a)",
            role_arn=brain_role.role_arn,
            agent_runtime_artifact=agentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                code_configuration=agentcore.CfnRuntime.CodeConfigurationProperty(
                    code=agentcore.CfnRuntime.CodeProperty(
                        s3=agentcore.CfnRuntime.S3LocationProperty(
                            bucket=brain_code.s3_bucket_name,
                            prefix=brain_code.s3_object_key,
                        )
                    ),
                    runtime="PYTHON_3_12",
                    entry_point=["main.py"],
                )
            ),
            network_configuration=agentcore.CfnRuntime.NetworkConfigurationProperty(network_mode="PUBLIC"),
            protocol_configuration="HTTP",
            lifecycle_configuration=agentcore.CfnRuntime.LifecycleConfigurationProperty(
                idle_runtime_session_timeout=300,  # Lambda 1 回分の複数タスクをウォームで捌ければ十分
                max_lifetime=1800,
            ),
            environment_variables={
                "BRAIN_MODEL_ID": BRAIN_MODEL_ID,
                "BEDROCK_REGION": self.region,
            },
        )
        runtime.node.add_dependency(brain_role)

        CfnOutput(self, "BrainRuntimeArn", value=runtime.attr_agent_runtime_arn)
        return runtime

