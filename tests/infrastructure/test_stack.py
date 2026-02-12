"""
CDKスタックのユニットテスト

要件 9.1: CDKスタックに必要なリソースが含まれることを検証
"""
import json
import aws_cdk as cdk
from aws_cdk import assertions
from hypothesis import given, settings
from hypothesis import strategies as st
from src.hokuhoku_imomaru_bot.infrastructure.stack import ImomaruBotStack


def test_dynamodb_tables_created():
    """
    要件 7.1, 7.2, 11.2: DynamoDBテーブルが正しく作成されることを確認
    
    検証項目:
    - BotStateテーブル、XPTableテーブル、ProcessedTweetsテーブル、EmotionImagesテーブルが作成される
    - すべてのテーブルがオンデマンド課金モードを使用
    - 保存時の暗号化が有効化される
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # DynamoDBテーブルが4つ作成されることを確認
    template.resource_count_is("AWS::DynamoDB::Table", 4)
    
    # BotStateテーブルの検証
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "TableName": "imomaru-bot-state",
        "KeySchema": [
            {
                "AttributeName": "state_id",
                "KeyType": "HASH"
            }
        ],
        "AttributeDefinitions": [
            {
                "AttributeName": "state_id",
                "AttributeType": "S"
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
        "SSESpecification": {
            "SSEEnabled": True
        },
        "PointInTimeRecoverySpecification": {
            "PointInTimeRecoveryEnabled": True
        }
    })
    
    # XPTableテーブルの検証
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "TableName": "imomaru-bot-xp-table",
        "KeySchema": [
            {
                "AttributeName": "level",
                "KeyType": "HASH"
            }
        ],
        "AttributeDefinitions": [
            {
                "AttributeName": "level",
                "AttributeType": "N"
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
        "SSESpecification": {
            "SSEEnabled": True
        }
    })
    
    # ProcessedTweetsテーブルの検証（冪等性制御用）
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "TableName": "imomaru-bot-processed-tweets",
        "KeySchema": [
            {
                "AttributeName": "tweet_id",
                "KeyType": "HASH"
            }
        ],
        "AttributeDefinitions": [
            {
                "AttributeName": "tweet_id",
                "AttributeType": "S"
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
        "SSESpecification": {
            "SSEEnabled": True
        },
        "TimeToLiveSpecification": {
            "AttributeName": "ttl",
            "Enabled": True
        }
    })


def test_dynamodb_tables_have_encryption():
    """
    セキュリティ要件: DynamoDBテーブルが暗号化されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # すべてのDynamoDBテーブルが暗号化されていることを確認
    template.all_resources_properties("AWS::DynamoDB::Table", {
        "SSESpecification": {
            "SSEEnabled": True
        }
    })


def test_dynamodb_tables_use_on_demand_billing():
    """
    要件 11.2: DynamoDBテーブルがオンデマンド課金モードを使用することを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # すべてのDynamoDBテーブルがオンデマンド課金を使用していることを確認
    template.all_resources_properties("AWS::DynamoDB::Table", {
        "BillingMode": "PAY_PER_REQUEST"
    })


def test_s3_bucket_created():
    """
    要件 5.1, 11.4: S3バケットが正しく作成されることを確認
    
    検証項目:
    - S3バケットが作成される
    - サーバーサイド暗号化（SSE-S3）が有効化される
    - パブリックアクセスがブロックされる
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # S3バケットが1つ作成されることを確認
    template.resource_count_is("AWS::S3::Bucket", 1)
    
    # S3バケットの検証
    template.has_resource_properties("AWS::S3::Bucket", {
        "BucketEncryption": {
            "ServerSideEncryptionConfiguration": [
                {
                    "ServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    }
                }
            ]
        },
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True
        }
    })


def test_s3_bucket_has_encryption():
    """
    セキュリティ要件: S3バケットが暗号化されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # S3バケットが暗号化されていることを確認
    template.has_resource_properties("AWS::S3::Bucket", {
        "BucketEncryption": {
            "ServerSideEncryptionConfiguration": assertions.Match.any_value()
        }
    })


def test_s3_bucket_blocks_public_access():
    """
    セキュリティ要件: S3バケットがパブリックアクセスをブロックすることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # S3バケットがパブリックアクセスをブロックしていることを確認
    template.has_resource_properties("AWS::S3::Bucket", {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True
        }
    })


def test_secrets_manager_secret_created():
    """
    要件 8.1: Secrets Managerシークレットが作成されることを確認
    
    検証項目:
    - X API認証情報用のシークレットが作成される
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # Secrets Managerシークレットが1つ作成されることを確認
    template.resource_count_is("AWS::SecretsManager::Secret", 1)
    
    # シークレットの検証
    template.has_resource_properties("AWS::SecretsManager::Secret", {
        "Name": "imomaru-bot/x-api-credentials",
        "Description": "X API認証情報（OAuth 1.0a + Bearer Token）"
    })


def test_lambda_execution_role_created():
    """
    要件 9.3: Lambda実行ロールが作成されることを確認
    
    検証項目:
    - Lambda実行ロールが作成される
    - Lambda サービスプリンシパルが信頼される
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # IAMロールが作成されることを確認
    template.has_resource_properties("AWS::IAM::Role", {
        "AssumeRolePolicyDocument": {
            "Statement": [
                {
                    "Action": "sts:AssumeRole",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "lambda.amazonaws.com"
                    }
                }
            ]
        },
        "Description": "Imomaru Bot Lambda Execution Role",
        "ManagedPolicyArns": assertions.Match.array_with([
            assertions.Match.object_like({
                "Fn::Join": assertions.Match.any_value()
            })
        ])
    })


def test_lambda_role_has_dynamodb_permissions():
    """
    要件 9.3: Lambda実行ロールがDynamoDB読み書き権限を持つことを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # DynamoDB読み書き権限のポリシーが存在することを確認
    template.has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": {
            "Statement": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Action": assertions.Match.array_with([
                        "dynamodb:BatchGetItem",
                        "dynamodb:GetItem",
                        "dynamodb:Scan"
                    ]),
                    "Effect": "Allow"
                })
            ])
        }
    })


def test_lambda_role_has_s3_read_permissions():
    """
    要件 9.3: Lambda実行ロールがS3読み取り権限を持つことを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # S3読み取り権限のポリシーが存在することを確認
    template.has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": {
            "Statement": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Action": assertions.Match.array_with([
                        "s3:GetObject*",
                        "s3:GetBucket*",
                        "s3:List*"
                    ]),
                    "Effect": "Allow"
                })
            ])
        }
    })


def test_lambda_role_has_secrets_manager_permissions():
    """
    要件 9.3: Lambda実行ロールがSecrets Manager読み取り権限を持つことを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # Secrets Manager読み取り権限のポリシーが存在することを確認
    template.has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": {
            "Statement": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Action": assertions.Match.array_with([
                        "secretsmanager:GetSecretValue",
                        "secretsmanager:DescribeSecret"
                    ]),
                    "Effect": "Allow"
                })
            ])
        }
    })


def test_lambda_role_has_bedrock_permissions():
    """
    要件 9.3: Lambda実行ロールがBedrock呼び出し権限を持つことを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # Bedrock呼び出し権限のポリシーが存在することを確認
    template.has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": {
            "Statement": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Action": "bedrock:InvokeModel",
                    "Effect": "Allow",
                    "Resource": assertions.Match.any_value()
                })
            ])
        }
    })


def test_lambda_function_created():
    """
    要件 9.1: Lambda関数が正しく作成されることを確認
    
    検証項目:
    - Lambda関数が作成される
    - Python 3.12ランタイムが使用される
    - タイムアウトが3分に設定される
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # Lambda関数が1つ作成されることを確認
    template.resource_count_is("AWS::Lambda::Function", 1)
    
    # Lambda関数の検証
    template.has_resource_properties("AWS::Lambda::Function", {
        "FunctionName": "imomaru-bot-handler",
        "Runtime": "python3.12",
        "Handler": "hokuhoku_imomaru_bot.lambda_handler.lambda_handler",
        "Timeout": 180,  # 3分 = 180秒
        "MemorySize": 256,
        "Description": "Imomaru Bot - Main Handler",
    })


def test_lambda_function_has_environment_variables():
    """
    要件 9.5: Lambda関数に環境変数が設定されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # 環境変数が設定されていることを確認（CDKはRefを使用するため、キーの存在のみ確認）
    template.has_resource_properties("AWS::Lambda::Function", {
        "Environment": {
            "Variables": assertions.Match.object_like({
                "STATE_TABLE_NAME": assertions.Match.any_value(),
                "XP_TABLE_NAME": assertions.Match.any_value(),
                "SECRET_NAME": assertions.Match.any_value(),
                "ASSETS_BUCKET_NAME": assertions.Match.any_value(),
                "OSHI_USER_ID": assertions.Match.any_value(),
                "GROUP_USER_ID": assertions.Match.any_value(),
            })
        }
    })


def test_eventbridge_schedules_created():
    """
    要件 9.4: EventBridge Schedulerが正しく作成されることを確認

    検証項目:
    - Core Time × 3 + Daily Report × 1 = 4つのScheduleが作成される
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::Scheduler::Schedule", 4)


def test_core_time_morning_schedule_configuration():
    """
    要件 1.1, 1.3: 朝10時（JST）のコアタイムスケジュールが正しく設定されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::Scheduler::Schedule", {
        "ScheduleExpression": "cron(0 10 * * ? *)",
        "ScheduleExpressionTimezone": "Asia/Tokyo",
        "FlexibleTimeWindow": {
            "Mode": "FLEXIBLE",
            "MaximumWindowInMinutes": 15,
        },
    })


def test_core_time_afternoon_schedule_configuration():
    """
    要件 1.1, 1.3: 昼13時（JST）のコアタイムスケジュールが正しく設定されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::Scheduler::Schedule", {
        "ScheduleExpression": "cron(0 13 * * ? *)",
        "ScheduleExpressionTimezone": "Asia/Tokyo",
        "FlexibleTimeWindow": {
            "Mode": "FLEXIBLE",
            "MaximumWindowInMinutes": 23,
        },
    })


def test_core_time_evening_schedule_configuration():
    """
    要件 1.1, 1.3: 夕方18時（JST）のコアタイムスケジュールが正しく設定されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::Scheduler::Schedule", {
        "ScheduleExpression": "cron(0 18 * * ? *)",
        "ScheduleExpressionTimezone": "Asia/Tokyo",
        "FlexibleTimeWindow": {
            "Mode": "FLEXIBLE",
            "MaximumWindowInMinutes": 3,
        },
    })


def test_daily_report_schedule_configuration():
    """
    要件 1.2, 1.4: 日報スケジュール（23:58 JST）が正しく設定されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::Scheduler::Schedule", {
        "ScheduleExpression": "cron(58 23 * * ? *)",
        "ScheduleExpressionTimezone": "Asia/Tokyo",
        "FlexibleTimeWindow": {
            "Mode": "FLEXIBLE",
            "MaximumWindowInMinutes": 1,
        },
    })


def test_scheduler_targets_lambda():
    """
    要件 1.5: 全スケジュールがLambda関数をターゲットにすることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    # 全Scheduler::ScheduleリソースのターゲットARNがLambdaを指すことを確認
    template.all_resources_properties("AWS::Scheduler::Schedule", {
        "Target": assertions.Match.object_like({
            "Arn": assertions.Match.object_like({
                "Fn::GetAtt": assertions.Match.array_with([
                    assertions.Match.string_like_regexp("BotLambda.*"),
                    "Arn",
                ])
            }),
        }),
    })


def test_scheduler_role_created():
    """
    要件 1.5: Scheduler用IAMロールが作成されLambda invoke権限を持つことを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::IAM::Role", {
        "AssumeRolePolicyDocument": {
            "Statement": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Action": "sts:AssumeRole",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "scheduler.amazonaws.com",
                    },
                })
            ])
        },
        "Description": "EventBridge Scheduler Role for Imomaru Bot",
    })


def test_flexible_time_window_values():
    """
    要件 1.3, 1.4: FlexibleTimeWindowの設定値が正しいことを確認

    - Morning: 15分, Afternoon: 23分, Evening: 3分, DailyReport: 1分
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    # 全スケジュールがFLEXIBLEモードであることを確認
    template.all_resources_properties("AWS::Scheduler::Schedule", {
        "FlexibleTimeWindow": assertions.Match.object_like({
            "Mode": "FLEXIBLE",
        }),
    })

    # 各ウィンドウ値が存在することを確認
    for window_min in [15, 23, 3, 1]:
        template.has_resource_properties("AWS::Scheduler::Schedule", {
            "FlexibleTimeWindow": {
                "Mode": "FLEXIBLE",
                "MaximumWindowInMinutes": window_min,
            },
        })



# ============================================
# CDKスタック全体の統合テスト
# ============================================

def test_cdk_stack_all_resources():
    """
    要件 9.1: CDKスタックにすべての必要なリソースが含まれることを確認
    
    検証項目:
    - DynamoDBテーブル: 4つ（BotState、XPTable、ProcessedTweets、EmotionImages）
    - S3バケット: 1つ
    - Secrets Managerシークレット: 1つ
    - Lambda関数: 1つ
    - EventBridge Scheduler: 4つ
    - IAMロール: 1つ以上
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # リソース数の確認
    template.resource_count_is("AWS::DynamoDB::Table", 4)
    template.resource_count_is("AWS::S3::Bucket", 1)
    template.resource_count_is("AWS::SecretsManager::Secret", 1)
    template.resource_count_is("AWS::Lambda::Function", 1)
    template.resource_count_is("AWS::Scheduler::Schedule", 4)


def test_cdk_stack_lambda_timeout():
    """
    要件 9.5: Lambda関数のタイムアウトが3分に設定されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    template.has_resource_properties("AWS::Lambda::Function", {
        "Timeout": 180,  # 3分 = 180秒
    })


def test_cdk_stack_lambda_memory():
    """
    Lambda関数のメモリサイズが適切に設定されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    template.has_resource_properties("AWS::Lambda::Function", {
        "MemorySize": 256,
    })


def test_cdk_stack_s3_ssl_enforced():
    """
    セキュリティ要件: S3バケットがSSL/TLS接続を強制することを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # BucketPolicyでSSLが強制されていることを確認
    template.has_resource_properties("AWS::S3::BucketPolicy", {
        "PolicyDocument": {
            "Statement": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Action": "s3:*",
                    "Condition": {
                        "Bool": {
                            "aws:SecureTransport": "false"
                        }
                    },
                    "Effect": "Deny",
                })
            ])
        }
    })


def test_cdk_stack_resources_have_descriptions():
    """
    リソースに適切な説明が設定されていることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # Lambda関数の説明
    template.has_resource_properties("AWS::Lambda::Function", {
        "Description": "Imomaru Bot - Main Handler",
    })
    
    # Secrets Managerの説明
    template.has_resource_properties("AWS::SecretsManager::Secret", {
        "Description": "X API認証情報（OAuth 1.0a + Bearer Token）",
    })


# ============================================
# CloudWatch ダッシュボード & アラームのテスト
# ============================================

def test_cloudwatch_dashboard_created():
    """
    運用要件: CloudWatchダッシュボードが作成されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # CloudWatchダッシュボードが1つ作成されることを確認
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)
    
    # ダッシュボード名の検証
    template.has_resource_properties("AWS::CloudWatch::Dashboard", {
        "DashboardName": "imomaru-bot-dashboard",
    })


def test_cloudwatch_dashboard_has_widgets():
    """
    運用要件: CloudWatchダッシュボードにウィジェットが含まれることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # ダッシュボードにDashboardBodyが設定されていることを確認
    template.has_resource_properties("AWS::CloudWatch::Dashboard", {
        "DashboardBody": assertions.Match.any_value(),
    })


def test_sns_alarm_topic_created():
    """
    運用要件: アラーム通知用のSNSトピックが作成されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # SNSトピックが1つ作成されることを確認
    template.resource_count_is("AWS::SNS::Topic", 1)
    
    # SNSトピックの検証
    template.has_resource_properties("AWS::SNS::Topic", {
        "TopicName": "imomaru-bot-alarms",
        "DisplayName": "Imomaru Bot Alarms",
    })


def test_lambda_error_alarm_created():
    """
    運用要件: Lambdaエラーアラームが作成されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # CloudWatchアラームが2つ作成されることを確認（エラーと実行時間）
    template.resource_count_is("AWS::CloudWatch::Alarm", 2)
    
    # Lambdaエラーアラームの検証
    template.has_resource_properties("AWS::CloudWatch::Alarm", {
        "AlarmName": "imomaru-bot-lambda-errors",
        "AlarmDescription": "Lambda関数でエラーが発生しました",
        "MetricName": "Errors",
        "Namespace": "AWS/Lambda",
        "Statistic": "Sum",
        "Period": 300,  # 5分
        "EvaluationPeriods": 1,
        "Threshold": 1,
        "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        "TreatMissingData": "notBreaching",
    })


def test_lambda_duration_alarm_created():
    """
    運用要件: Lambda実行時間アラームが作成されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # Lambda実行時間アラームの検証
    template.has_resource_properties("AWS::CloudWatch::Alarm", {
        "AlarmName": "imomaru-bot-lambda-duration",
        "AlarmDescription": "Lambda関数の実行時間が長すぎます",
        "MetricName": "Duration",
        "Namespace": "AWS/Lambda",
        "Statistic": "Maximum",
        "Period": 300,  # 5分
        "EvaluationPeriods": 1,
        "Threshold": 150000,  # 150秒（2分30秒）
        "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        "TreatMissingData": "notBreaching",
    })


def test_alarms_have_sns_action():
    """
    運用要件: アラームがSNSトピックに通知を送ることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # アラームにAlarmActionsが設定されていることを確認
    template.has_resource_properties("AWS::CloudWatch::Alarm", {
        "AlarmActions": assertions.Match.array_with([
            assertions.Match.object_like({
                "Ref": assertions.Match.string_like_regexp("AlarmTopic.*")
            })
        ])
    })


def test_alarms_monitor_correct_lambda():
    """
    運用要件: アラームが正しいLambda関数を監視することを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # アラームがBotLambdaのDimensionsを持つことを確認
    template.has_resource_properties("AWS::CloudWatch::Alarm", {
        "Dimensions": assertions.Match.array_with([
            assertions.Match.object_like({
                "Name": "FunctionName",
                "Value": assertions.Match.object_like({
                    "Ref": assertions.Match.string_like_regexp("BotLambda.*")
                })
            })
        ])
    })



# ============================================
# Property-Based Tests (スケジュール最適化)
# ============================================

class TestProperty1AllSchedulesHaveExecutionMode:
    """
    **Property 1: 全スケジュールにexecution_modeが含まれる**

    For any EventBridge Schedulerリソース in the synthesized CDK template,
    the target input payload SHALL contain a valid execution_mode field
    with value core_time or daily_report.

    **Validates: Requirements 1.6**
    """

    def _get_all_schedule_inputs(self):
        """CDKテンプレートから全Schedulerリソースのターゲット入力を取得"""
        app = cdk.App()
        stack = ImomaruBotStack(app, "test-stack")
        template = assertions.Template.from_stack(stack)
        schedules = template.find_resources("AWS::Scheduler::Schedule")
        inputs = []
        for logical_id, resource in schedules.items():
            target = resource["Properties"]["Target"]
            raw_input = target["Input"]
            parsed = json.loads(raw_input)
            inputs.append((logical_id, parsed))
        return inputs

    @given(schedule_index=st.integers(min_value=0, max_value=3))
    @settings(max_examples=100)
    def test_all_schedules_have_valid_execution_mode(self, schedule_index):
        """全スケジュールのターゲット入力に有効なexecution_modeが含まれる"""
        all_inputs = self._get_all_schedule_inputs()
        assert len(all_inputs) == 4, f"Expected 4 schedules, got {len(all_inputs)}"

        logical_id, parsed_input = all_inputs[schedule_index]
        assert "execution_mode" in parsed_input, (
            f"Schedule {logical_id} missing execution_mode in target input"
        )
        assert parsed_input["execution_mode"] in ("core_time", "daily_report"), (
            f"Schedule {logical_id} has invalid execution_mode: {parsed_input['execution_mode']}"
        )
