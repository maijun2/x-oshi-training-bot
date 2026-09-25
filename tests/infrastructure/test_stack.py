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
    
    # DynamoDBテーブルが6つ作成されることを確認
    template.resource_count_is("AWS::DynamoDB::Table", 6)
    
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
    
    # S3バケットが2つ作成されることを確認（アセット用 ＋ 感情画像の公開用）
    template.resource_count_is("AWS::S3::Bucket", 2)
    
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
    
    # Secrets Managerシークレットが2つ作成されることを確認（X API / Buffer API）
    template.resource_count_is("AWS::SecretsManager::Secret", 2)
    
    # シークレットの検証
    template.has_resource_properties("AWS::SecretsManager::Secret", {
        "Name": "imomaru-bot/x-api-credentials",
        "Description": "X API認証情報（OAuth 1.0a + Bearer Token）"
    })


def test_public_assets_bucket_created():
    """
    感情画像の公開バケット: emotions/* のみ匿名 GetObject を許可し、ACL は引き続きブロック。
    既存の assets バケットは BLOCK_ALL のまま
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::S3::Bucket", {
        "BucketName": {"Fn::Join": ["", assertions.Match.array_with(["imomaru-bot-public-assets-"])]},
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": False,
            "RestrictPublicBuckets": False,
        },
    })
    template.has_resource_properties("AWS::S3::Bucket", {
        "BucketName": {"Fn::Join": ["", assertions.Match.array_with(["imomaru-bot-assets-"])]},
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    })
    template.has_resource_properties("AWS::S3::BucketPolicy", {
        "Bucket": {"Ref": assertions.Match.string_like_regexp("PublicAssetsBucket.*")},
        "PolicyDocument": {
            "Statement": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Sid": "PublicReadEmotionImages",
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": "s3:GetObject",
                    "Resource": assertions.Match.object_like({
                        "Fn::Join": ["", assertions.Match.array_with([
                            assertions.Match.object_like({"Fn::GetAtt": [assertions.Match.string_like_regexp("PublicAssetsBucket.*"), "Arn"]}),
                            "/emotions/*",
                        ])]
                    }),
                })
            ])
        },
    })


def test_buffer_api_secret_created():
    """
    Buffer API認証情報用のシークレットが作成され、Lambdaから名前で参照できることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::SecretsManager::Secret", {
        "Name": "imomaru-bot/buffer-api",
        "Description": "Buffer API認証情報（Personal Access Token + channel ID）",
    })
    template.has_resource("AWS::SecretsManager::Secret", {
        "Properties": {"Name": "imomaru-bot/buffer-api"},
        "DeletionPolicy": "Retain",
    })
    template.has_resource_properties("AWS::Lambda::Function", {
        "Environment": {
            "Variables": assertions.Match.object_like({
                "BUFFER_SECRET_NAME": assertions.Match.any_value(),
                "BUFFER_RUN_CAP": "2",
                "BUFFER_DAILY_CAP": "7",
                "BUFFER_SLOT_TIMES_JST": "02:00,08:00,11:15,12:15,14:15,15:15,19:15,20:15,22:00",
                "PUBLIC_ASSETS_BUCKET_NAME": assertions.Match.any_value(),
            })
        }
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


def test_lambda_role_has_no_direct_bedrock_permissions():
    """
    2b-3: Haiku 直呼びを撤去したので、Lambda 実行ロールに bedrock:InvokeModel は付けない
    （モデル呼び出しは頭脳 Runtime のロールが持つ）
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    lambda_role_ids = {
        rid for rid, res in template.find_resources("AWS::IAM::Role").items()
        if any(
            st.get("Principal", {}).get("Service") == "lambda.amazonaws.com"
            for st in res["Properties"]["AssumeRolePolicyDocument"]["Statement"]
        )
    }
    assert lambda_role_ids
    for policy in template.find_resources("AWS::IAM::Policy").values():
        roles = {r.get("Ref") for r in policy["Properties"].get("Roles", [])}
        if not roles & lambda_role_ids:
            continue
        for st in policy["Properties"]["PolicyDocument"]["Statement"]:
            actions = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
            assert not any(a.startswith("bedrock:") for a in actions), st


def test_lambda_function_created():
    """
    要件 9.1: Lambda関数が正しく作成されることを確認
    
    検証項目:
    - Lambda関数が作成される
    - Python 3.12ランタイムが使用される
    - タイムアウトが5分に設定される
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
        "Timeout": 300,  # 5分 = 300秒（フェーズ2a で頭脳呼び出しを投稿ごとに行うため 3 分 → 5 分）
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
    - Core Time × 4 + Daily Report × 1 = 5つのScheduleが作成される
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::Scheduler::Schedule", 5)


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


def test_core_time_night_schedule_configuration():
    """
    夜21時（JST）のコアタイムスケジュール: 5 分ウィンドウ（22:00 の Buffer 枠まで猶予 55 分）、
    EventBridge 入力に autonomous_allowed=true を付ける（3b-1 の自律投稿用。日中の実行には付けない）
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::Scheduler::Schedule", {
        "ScheduleExpression": "cron(0 21 * * ? *)",
        "ScheduleExpressionTimezone": "Asia/Tokyo",
        "FlexibleTimeWindow": {
            "Mode": "FLEXIBLE",
            "MaximumWindowInMinutes": 5,
        },
        "Target": assertions.Match.object_like({
            "Input": assertions.Match.serialized_json({"execution_mode": "core_time", "autonomous_allowed": True}),
        }),
    })

    # 日中のコアタイムには autonomous_allowed を付けない
    for hour in (10, 13, 18):
        template.has_resource_properties("AWS::Scheduler::Schedule", {
            "ScheduleExpression": f"cron(0 {hour} * * ? *)",
            "Target": assertions.Match.object_like({
                "Input": assertions.Match.serialized_json({"execution_mode": "core_time"}),
            }),
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

    - Morning: 15分, Afternoon: 23分, Evening: 3分, Night: 5分, DailyReport: 1分
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
    for window_min in [15, 23, 3, 5, 1]:
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
    - DynamoDBテーブル: 6つ（BotState、XPTable、ProcessedTweets、EmotionImages、AllowedUsers、ProcessedReplies）
    - S3バケット: 1つ
    - Secrets Managerシークレット: 1つ
    - Lambda関数: 1つ
    - EventBridge Scheduler: 5つ
    - IAMロール: 1つ以上
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # リソース数の確認
    template.resource_count_is("AWS::DynamoDB::Table", 6)
    template.resource_count_is("AWS::S3::Bucket", 2)
    template.resource_count_is("AWS::SecretsManager::Secret", 2)
    template.resource_count_is("AWS::Lambda::Function", 1)
    template.resource_count_is("AWS::Scheduler::Schedule", 5)


def test_cdk_stack_lambda_timeout():
    """
    要件 9.5: Lambda関数のタイムアウトが5分に設定されることを確認（フェーズ2a で 3 分 → 5 分）
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    template.has_resource_properties("AWS::Lambda::Function", {
        "Timeout": 300,  # 5分 = 300秒（フェーズ2a で頭脳呼び出しを投稿ごとに行うため 3 分 → 5 分）
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
    
    # CloudWatchアラームが3つ作成されることを確認（エラー・実行時間・アプリ内エラー）
    template.resource_count_is("AWS::CloudWatch::Alarm", 3)
    
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


def test_app_error_metric_filter_created():
    """
    運用要件: try/except で捕捉されたエラーを拾うログメトリクスフィルタが作成されることを確認

    Lambda ランタイムが付与する [ERROR] / [CRITICAL] プレフィックスを term フィルタで検出する。
    （LogFormat=Text のため JSON フィルタ {$.level = "ERROR"} は使えない）
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::Logs::MetricFilter", 1)
    template.has_resource_properties("AWS::Logs::MetricFilter", {
        "LogGroupName": "/aws/lambda/imomaru-bot-handler",
        "FilterPattern": '?"[ERROR]" ?"[CRITICAL]"',
        "MetricTransformations": [
            assertions.Match.object_like({
                "MetricNamespace": "ImomaruBot",
                "MetricName": "AppErrors",
                "MetricValue": "1",
                "DefaultValue": 0,
            })
        ],
    })


def test_app_error_alarm_created():
    """
    運用要件: アプリ内エラーアラームがメトリクスフィルタのカスタムメトリクスを監視し、
    SNS トピックへ通知することを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::CloudWatch::Alarm", {
        "AlarmName": "imomaru-bot-app-errors",
        "Namespace": "ImomaruBot",
        "MetricName": "AppErrors",
        "Statistic": "Sum",
        "Period": 300,
        "EvaluationPeriods": 1,
        "Threshold": 1,
        "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        "TreatMissingData": "notBreaching",
        "AlarmActions": assertions.Match.array_with([
            assertions.Match.object_like({
                "Ref": assertions.Match.string_like_regexp("AlarmTopic.*")
            })
        ]),
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

    @given(schedule_index=st.integers(min_value=0, max_value=4))
    @settings(max_examples=100)
    def test_all_schedules_have_valid_execution_mode(self, schedule_index):
        """全スケジュールのターゲット入力に有効なexecution_modeが含まれる"""
        all_inputs = self._get_all_schedule_inputs()
        assert len(all_inputs) == 5, f"Expected 5 schedules, got {len(all_inputs)}"

        logical_id, parsed_input = all_inputs[schedule_index]
        assert "execution_mode" in parsed_input, (
            f"Schedule {logical_id} missing execution_mode in target input"
        )
        assert parsed_input["execution_mode"] in ("core_time", "daily_report"), (
            f"Schedule {logical_id} has invalid execution_mode: {parsed_input['execution_mode']}"
        )


def test_brain_runtime_created():
    """
    頭脳（AgentCore Runtime）が direct code deploy で作成され、Lambda が呼び出せることを確認（フェーズ2a）
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::BedrockAgentCore::Runtime", 1)
    template.has_resource_properties("AWS::BedrockAgentCore::Runtime", {
        "AgentRuntimeName": "imomaru_brain",
        "AgentRuntimeArtifact": {
            "CodeConfiguration": assertions.Match.object_like({
                "Runtime": "PYTHON_3_12",
                "EntryPoint": ["main.py"],
                "Code": {"S3": assertions.Match.object_like({"Bucket": assertions.Match.any_value()})},
            })
        },
        "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
        "ProtocolConfiguration": "HTTP",
        "LifecycleConfiguration": {"IdleRuntimeSessionTimeout": 300, "MaxLifetime": 1800},
        "EnvironmentVariables": {
            "BRAIN_MODEL_ID": "moonshotai.kimi-k2.5",
            "BEDROCK_REGION": assertions.Match.any_value(),
            # 3a-read: 推しの記憶を retrieve する Memory と actorId（Lambda の書き込みと同じ）
            "OSHI_MEMORY_ID": assertions.Match.any_value(),
            "OSHI_ACTOR_ID": assertions.Match.any_value(),
        },
    })

    # 実行ロール: AgentCore が assume でき、モデル呼び出し・zip 読み取り・ログ書き込みができる
    template.has_resource_properties("AWS::IAM::Role", {
        "RoleName": "imomaru-brain-runtime-role",
        "AssumeRolePolicyDocument": assertions.Match.object_like({
            "Statement": [assertions.Match.object_like({
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Condition": assertions.Match.object_like({"StringEquals": assertions.Match.any_value()}),
            })]
        }),
        "Policies": [assertions.Match.object_like({
            "PolicyDocument": assertions.Match.object_like({
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({"Sid": "GetAgentAccessToken"}),
                    assertions.Match.object_like({
                        "Sid": "BedrockModelInvocation",
                        "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                    }),
                    assertions.Match.object_like({
                        "Sid": "RecallOshiMemory",
                        "Action": "bedrock-agentcore:RetrieveMemoryRecords",
                    }),
                    assertions.Match.object_like({"Sid": "ReadDeploymentPackage"}),
                ])
            })
        })],
    })

    # Lambda: Runtime ARN を環境変数で受け取り、InvokeAgentRuntime できる。timeout は 5 分
    template.has_resource_properties("AWS::Lambda::Function", {
        "Timeout": 300,
        "Environment": {
            "Variables": assertions.Match.object_like({
                "BRAIN_RUNTIME_ARN": assertions.Match.any_value(),
            })
        },
    })
    template.has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": assertions.Match.object_like({
            "Statement": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Action": "bedrock-agentcore:InvokeAgentRuntime",
                    "Effect": "Allow",
                })
            ])
        })
    })


def test_oshi_memory_created():
    """
    フェーズ3a-write: 推しの記憶（AgentCore Memory）が作成され、Lambda から書き込めることを確認

    検証項目:
    - Memory が 1 つ、戦略は Semantic / User Preference / Episodic の 3 つ、削除時は保持
    - Lambda 環境変数 OSHI_MEMORY_ID が設定される
    - Lambda ロールに bedrock-agentcore:CreateEvent が付与される
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::BedrockAgentCore::Memory", 1)
    template.has_resource("AWS::BedrockAgentCore::Memory", {
        "Properties": {
            "Name": "imomaru_oshi_memory",
            "EventExpiryDuration": 365,
            "MemoryStrategies": [
                {"SemanticMemoryStrategy": assertions.Match.object_like({"Namespaces": ["/oshi/{actorId}/facts/"]})},
                {"UserPreferenceMemoryStrategy": assertions.Match.object_like({"Namespaces": ["/oshi/{actorId}/preferences/"]})},
                {"EpisodicMemoryStrategy": assertions.Match.object_like({
                    "Namespaces": ["/oshi/{actorId}/episodes/"],
                    "ReflectionConfiguration": {"Namespaces": ["/oshi/{actorId}/episodes/"]},
                })},
            ],
        },
        "DeletionPolicy": "Retain",
    })
    template.has_resource_properties("AWS::Lambda::Function", {
        "Environment": {
            "Variables": assertions.Match.object_like({
                "OSHI_MEMORY_ID": assertions.Match.any_value(),
            })
        }
    })
    template.has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": {
            "Statement": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Action": "bedrock-agentcore:CreateEvent",
                    "Effect": "Allow",
                })
            ])
        }
    })


def test_ses_sender_domain_identity_created(monkeypatch):
    """
    SES_SENDER_DOMAIN を設定すると、Easy DKIM + カスタム MAIL FROM 付きのドメイン Identity が作られ、
    Lambda に送信権限が付き、DNS 登録用のレコードが Outputs に出ることを確認
    """
    monkeypatch.setenv("SES_SENDER_DOMAIN", "example.com")
    monkeypatch.setenv("FROM_EMAIL", "bot@example.com")
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::SES::EmailIdentity", 1)
    template.has_resource_properties("AWS::SES::EmailIdentity", {
        "EmailIdentity": "example.com",
        # DkimAttributes は既定（Easy DKIM、署名有効）なので CDK はテンプレートに出さない
        "MailFromAttributes": assertions.Match.object_like({
            "MailFromDomain": "ses.example.com",
        }),
    })
    template.has_resource_properties("AWS::Lambda::Function", {
        "Environment": {
            "Variables": assertions.Match.object_like({
                "FROM_EMAIL": "bot@example.com",
            })
        }
    })
    template.has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": {
            "Statement": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Action": ["ses:SendEmail", "ses:SendRawEmail"],
                    "Effect": "Allow",
                    "Resource": {
                        "Fn::Join": ["", assertions.Match.array_with([
                            ":identity/",
                            {"Ref": assertions.Match.string_like_regexp("^SenderDomainIdentity")},
                        ])]
                    },
                })
            ])
        }
    })
    outputs = template.find_outputs("*")
    assert {"SesDkimCname1", "SesDkimCname2", "SesDkimCname3", "SesMailFromMx", "SesMailFromSpf"} <= set(outputs)
    assert outputs["SesMailFromSpf"]["Value"] == 'ses.example.com TXT "v=spf1 include:amazonses.com ~all"'


def test_ses_sender_domain_absent_falls_back_to_notification_email(monkeypatch):
    """
    SES_SENDER_DOMAIN / FROM_EMAIL が未設定なら Identity は作られず、FROM_EMAIL は NOTIFICATION_EMAIL のまま
    """
    monkeypatch.delenv("SES_SENDER_DOMAIN", raising=False)
    monkeypatch.delenv("FROM_EMAIL", raising=False)
    monkeypatch.setenv("NOTIFICATION_EMAIL", "me@example.com")
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::SES::EmailIdentity", 0)
    template.has_resource_properties("AWS::Lambda::Function", {
        "Environment": {
            "Variables": assertions.Match.object_like({
                "FROM_EMAIL": "me@example.com",
            })
        }
    })
