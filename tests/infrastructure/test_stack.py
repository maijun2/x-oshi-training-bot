"""
CDKスタックのユニットテスト

要件 9.1: CDKスタックに必要なリソースが含まれることを検証
"""
import aws_cdk as cdk
from aws_cdk import assertions
from src.hokuhoku_imomaru_bot.infrastructure.stack import ImomaruBotStack


def test_dynamodb_tables_created():
    """
    要件 7.1, 7.2, 11.2: DynamoDBテーブルが正しく作成されることを確認
    
    検証項目:
    - BotStateテーブルとXPTableテーブルが作成される
    - 両テーブルともオンデマンド課金モードが設定される
    - 保存時の暗号化が有効化される
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # DynamoDBテーブルが2つ作成されることを確認
    template.resource_count_is("AWS::DynamoDB::Table", 2)
    
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
        "Description": "ほくほくいも丸くんLambda実行ロール",
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
                    "Resource": assertions.Match.object_like({
                        "Fn::Join": assertions.Match.any_value()
                    })
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
        "Description": "ほくほくいも丸くん育成ボット - メインハンドラー",
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
    要件 9.4: EventBridgeスケジュールが正しく作成されることを確認
    
    検証項目:
    - 朝9時（JST）と夜21時（JST）の2つのスケジュールが作成される
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # EventBridge Ruleが2つ作成されることを確認
    template.resource_count_is("AWS::Events::Rule", 2)


def test_morning_schedule_configuration():
    """
    要件 9.4: 朝9時（JST）のスケジュールが正しく設定されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # 朝のスケジュール（UTC 0:00 = JST 9:00）
    # CDKのcron形式: cron(分 時 ? 月 曜日 *)
    template.has_resource_properties("AWS::Events::Rule", {
        "Name": "imomaru-bot-morning-schedule",
        "ScheduleExpression": "cron(0 0 ? * * *)",
        "Description": "ほくほくいも丸くん - 朝9時（JST）のスケジュール",
        "State": "ENABLED",
    })


def test_evening_schedule_configuration():
    """
    要件 9.4: 夜21時（JST）のスケジュールが正しく設定されることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # 夜のスケジュール（UTC 12:00 = JST 21:00）
    template.has_resource_properties("AWS::Events::Rule", {
        "Name": "imomaru-bot-evening-schedule",
        "ScheduleExpression": "cron(0 12 ? * * *)",
        "Description": "ほくほくいも丸くん - 夜21時（JST）のスケジュール",
        "State": "ENABLED",
    })


def test_eventbridge_targets_lambda():
    """
    要件 9.4: EventBridgeスケジュールがLambda関数をターゲットにすることを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # EventBridge RuleがLambda関数をターゲットにしていることを確認
    template.has_resource_properties("AWS::Events::Rule", {
        "Targets": assertions.Match.array_with([
            assertions.Match.object_like({
                "Arn": assertions.Match.object_like({
                    "Fn::GetAtt": assertions.Match.array_with([
                        assertions.Match.string_like_regexp("BotLambda.*"),
                        "Arn"
                    ])
                })
            })
        ])
    })


def test_lambda_permission_for_eventbridge():
    """
    EventBridgeがLambda関数を呼び出す権限を持つことを確認
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # Lambda Permission（EventBridgeからの呼び出し許可）が作成されることを確認
    template.resource_count_is("AWS::Lambda::Permission", 2)  # 朝と夜の2つ



# ============================================
# CDKスタック全体の統合テスト
# ============================================

def test_cdk_stack_all_resources():
    """
    要件 9.1: CDKスタックにすべての必要なリソースが含まれることを確認
    
    検証項目:
    - DynamoDBテーブル: 2つ
    - S3バケット: 1つ
    - Secrets Managerシークレット: 1つ
    - Lambda関数: 1つ
    - EventBridge Rule: 2つ
    - IAMロール: 1つ以上
    """
    app = cdk.App()
    stack = ImomaruBotStack(app, "test-stack")
    template = assertions.Template.from_stack(stack)
    
    # リソース数の確認
    template.resource_count_is("AWS::DynamoDB::Table", 2)
    template.resource_count_is("AWS::S3::Bucket", 1)
    template.resource_count_is("AWS::SecretsManager::Secret", 1)
    template.resource_count_is("AWS::Lambda::Function", 1)
    template.resource_count_is("AWS::Events::Rule", 2)


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
        "Description": "ほくほくいも丸くん育成ボット - メインハンドラー",
    })
    
    # Secrets Managerの説明
    template.has_resource_properties("AWS::SecretsManager::Secret", {
        "Description": "X API認証情報（OAuth 1.0a + Bearer Token）",
    })
