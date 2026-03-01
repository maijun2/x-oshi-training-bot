"""
リプライ機能インフラストラクチャのプロパティベーステスト

Task 1.2: インフラストラクチャのプロパティテスト
Property: DynamoDBテーブル定義の正確性
Validates: Requirements 11.1-11.10
"""
import aws_cdk as cdk
from aws_cdk import assertions
from hypothesis import given, settings
from hypothesis import strategies as st
from src.hokuhoku_imomaru_bot.infrastructure.stack import ImomaruBotStack


# ============================================
# Property-Based Tests for Reply Feature Infrastructure
# ============================================

class TestPropertyDynamoDBTableDefinitions:
    """
    **Property: DynamoDBテーブル定義の正確性**
    
    For any DynamoDB table created for the reply feature (Allowed Users Table, Processed Replies Table),
    the table SHALL be correctly defined with:
    - Correct table name
    - Correct partition key
    - On-demand billing mode (PAY_PER_REQUEST)
    - AWS managed encryption (SSE enabled)
    - Deletion protection (RemovalPolicy.RETAIN)
    - TTL configuration (for Processed Replies Table only)
    
    **Validates: Requirements 11.1-11.10**
    """
    
    def _get_stack_template(self):
        """CDKスタックからテンプレートを取得"""
        app = cdk.App()
        stack = ImomaruBotStack(app, "test-stack")
        return assertions.Template.from_stack(stack)
    
    def _get_all_dynamodb_tables(self):
        """全DynamoDBテーブルリソースを取得"""
        template = self._get_stack_template()
        return template.find_resources("AWS::DynamoDB::Table")
    
    @given(table_name=st.sampled_from([
        "imomaru-bot-allowed-users",
        "imomaru-bot-processed-replies"
    ]))
    @settings(max_examples=100, deadline=None)
    def test_reply_feature_tables_exist(self, table_name):
        """
        リプライ機能用のDynamoDBテーブルが存在することを確認
        
        **Validates: Requirements 11.1, 11.5**
        """
        template = self._get_stack_template()
        
        # テーブルが存在することを確認
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": table_name
        })
    
    @given(table_name=st.sampled_from([
        "imomaru-bot-allowed-users",
        "imomaru-bot-processed-replies"
    ]))
    @settings(max_examples=100, deadline=None)
    def test_reply_feature_tables_use_on_demand_billing(self, table_name):
        """
        リプライ機能用のDynamoDBテーブルがオンデマンド課金モードを使用することを確認
        
        **Validates: Requirements 11.2, 11.6**
        """
        template = self._get_stack_template()
        
        # オンデマンド課金モードを使用していることを確認
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": table_name,
            "BillingMode": "PAY_PER_REQUEST"
        })
    
    @given(table_name=st.sampled_from([
        "imomaru-bot-allowed-users",
        "imomaru-bot-processed-replies"
    ]))
    @settings(max_examples=100, deadline=None)
    def test_reply_feature_tables_have_encryption(self, table_name):
        """
        リプライ機能用のDynamoDBテーブルがAWS管理の暗号化を使用することを確認
        
        **Validates: Requirements 11.3, 11.7**
        """
        template = self._get_stack_template()
        
        # AWS管理の暗号化が有効化されていることを確認
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": table_name,
            "SSESpecification": {
                "SSEEnabled": True
            }
        })
    
    @given(table_name=st.sampled_from([
        "imomaru-bot-allowed-users",
        "imomaru-bot-processed-replies"
    ]))
    @settings(max_examples=100, deadline=None)
    def test_reply_feature_tables_have_deletion_protection(self, table_name):
        """
        リプライ機能用のDynamoDBテーブルが削除保護を有効にすることを確認
        
        **Validates: Requirements 11.4, 11.8**
        """
        template = self._get_stack_template()
        
        # 削除保護（RemovalPolicy.RETAIN）が設定されていることを確認
        # CDKはUpdateReplacePolicyとDeletionPolicyの両方を設定する
        all_tables = self._get_all_dynamodb_tables()
        
        matching_table = None
        for logical_id, resource in all_tables.items():
            if resource["Properties"]["TableName"] == table_name:
                matching_table = resource
                break
        
        assert matching_table is not None, f"Table {table_name} not found"
        assert matching_table.get("UpdateReplacePolicy") == "Retain", (
            f"Table {table_name} should have UpdateReplacePolicy=Retain"
        )
        assert matching_table.get("DeletionPolicy") == "Retain", (
            f"Table {table_name} should have DeletionPolicy=Retain"
        )
    
    def test_allowed_users_table_has_correct_partition_key(self):
        """
        Allowed Users Tableが正しいパーティションキー（user_id）を持つことを確認
        
        **Validates: Requirements 2.2**
        """
        template = self._get_stack_template()
        
        # パーティションキーがuser_id（String型）であることを確認
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "imomaru-bot-allowed-users",
            "KeySchema": [
                {
                    "AttributeName": "user_id",
                    "KeyType": "HASH"
                }
            ],
            "AttributeDefinitions": [
                {
                    "AttributeName": "user_id",
                    "AttributeType": "S"
                }
            ]
        })
    
    def test_processed_replies_table_has_correct_partition_key(self):
        """
        Processed Replies Tableが正しいパーティションキー（tweet_id）を持つことを確認
        
        **Validates: Requirements 5.2**
        """
        template = self._get_stack_template()
        
        # パーティションキーがtweet_id（String型）であることを確認
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "imomaru-bot-processed-replies",
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
            ]
        })
    
    def test_processed_replies_table_has_ttl_enabled(self):
        """
        Processed Replies TableがTTL属性（ttl）を有効にすることを確認
        
        **Validates: Requirements 11.9, 5.6**
        """
        template = self._get_stack_template()
        
        # TTL属性が有効化されていることを確認
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "imomaru-bot-processed-replies",
            "TimeToLiveSpecification": {
                "AttributeName": "ttl",
                "Enabled": True
            }
        })
    
    def test_allowed_users_table_does_not_have_ttl(self):
        """
        Allowed Users TableがTTLを持たないことを確認
        
        Allowed Users Tableは永続的なデータを保存するため、TTLは不要
        """
        template = self._get_stack_template()
        all_tables = self._get_all_dynamodb_tables()
        
        # Allowed Users Tableを見つける
        allowed_users_table = None
        for logical_id, resource in all_tables.items():
            if resource["Properties"]["TableName"] == "imomaru-bot-allowed-users":
                allowed_users_table = resource
                break
        
        assert allowed_users_table is not None, "Allowed Users Table not found"
        
        # TTL設定が存在しないか、Enabledがfalseであることを確認
        ttl_spec = allowed_users_table["Properties"].get("TimeToLiveSpecification")
        if ttl_spec is not None:
            assert ttl_spec.get("Enabled") is False, (
                "Allowed Users Table should not have TTL enabled"
            )


class TestPropertyLambdaIAMPermissions:
    """
    **Property: Lambda実行ロールの権限**
    
    For the Lambda execution role,
    the role SHALL have:
    - Read permissions for Allowed Users Table
    - Read and write permissions for Processed Replies Table
    
    **Validates: Requirements 12.1, 12.2**
    """
    
    def _get_stack_template(self):
        """CDKスタックからテンプレートを取得"""
        app = cdk.App()
        stack = ImomaruBotStack(app, "test-stack")
        return assertions.Template.from_stack(stack)
    
    def test_lambda_role_has_allowed_users_table_read_permissions(self):
        """
        Lambda実行ロールがAllowed Users Tableへの読み取り権限を持つことを確認
        
        **Validates: Requirements 12.1, 2.6**
        """
        template = self._get_stack_template()
        
        # DynamoDB読み取り権限のポリシーが存在することを確認
        template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Action": assertions.Match.array_with([
                            "dynamodb:BatchGetItem",
                            "dynamodb:GetItem",
                        ]),
                        "Effect": "Allow",
                        "Resource": {
                            "Fn::GetAtt": assertions.Match.array_with([
                                assertions.Match.string_like_regexp("AllowedUsersTable.*"),
                                "Arn"
                            ])
                        }
                    })
                ])
            }
        })
    
    def test_lambda_role_has_processed_replies_table_read_write_permissions(self):
        """
        Lambda実行ロールがProcessed Replies Tableへの読み書き権限を持つことを確認
        
        **Validates: Requirements 12.2**
        """
        template = self._get_stack_template()
        
        # DynamoDB読み書き権限のポリシーが存在することを確認
        # 読み取り権限
        template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Action": assertions.Match.array_with([
                            "dynamodb:BatchGetItem",
                            "dynamodb:GetItem",
                        ]),
                        "Effect": "Allow",
                        "Resource": {
                            "Fn::GetAtt": assertions.Match.array_with([
                                assertions.Match.string_like_regexp("ProcessedRepliesTable.*"),
                                "Arn"
                            ])
                        }
                    })
                ])
            }
        })
        
        # 書き込み権限
        template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Action": assertions.Match.array_with([
                            "dynamodb:BatchWriteItem",
                            "dynamodb:PutItem",
                        ]),
                        "Effect": "Allow",
                        "Resource": {
                            "Fn::GetAtt": assertions.Match.array_with([
                                assertions.Match.string_like_regexp("ProcessedRepliesTable.*"),
                                "Arn"
                            ])
                        }
                    })
                ])
            }
        })


class TestPropertyLambdaEnvironmentVariables:
    """
    **Property: Lambda環境変数**
    
    For the Lambda function,
    the environment variables SHALL include:
    - ALLOWED_USERS_TABLE_NAME
    - PROCESSED_REPLIES_TABLE_NAME
    
    **Validates: Requirements 11.1-11.10**
    """
    
    def _get_stack_template(self):
        """CDKスタックからテンプレートを取得"""
        app = cdk.App()
        stack = ImomaruBotStack(app, "test-stack")
        return assertions.Template.from_stack(stack)
    
    @given(env_var=st.sampled_from([
        "ALLOWED_USERS_TABLE_NAME",
        "PROCESSED_REPLIES_TABLE_NAME"
    ]))
    @settings(max_examples=100, deadline=None)
    def test_lambda_has_reply_feature_environment_variables(self, env_var):
        """
        Lambda関数がリプライ機能用の環境変数を持つことを確認
        
        **Validates: Requirements 11.1-11.10**
        """
        template = self._get_stack_template()
        
        # 環境変数が設定されていることを確認
        template.has_resource_properties("AWS::Lambda::Function", {
            "Environment": {
                "Variables": assertions.Match.object_like({
                    env_var: assertions.Match.any_value()
                })
            }
        })


class TestPropertyTableCount:
    """
    **Property: DynamoDBテーブル数**
    
    For the CDK stack,
    the total number of DynamoDB tables SHALL be 6:
    - BotState
    - XPTable
    - ProcessedTweets
    - EmotionImages
    - AllowedUsers (new)
    - ProcessedReplies (new)
    
    **Validates: Requirements 11.1, 11.5**
    """
    
    def test_total_dynamodb_table_count(self):
        """
        DynamoDBテーブルの総数が6つであることを確認
        
        **Validates: Requirements 11.1, 11.5**
        """
        app = cdk.App()
        stack = ImomaruBotStack(app, "test-stack")
        template = assertions.Template.from_stack(stack)
        
        # DynamoDBテーブルが6つ作成されることを確認
        template.resource_count_is("AWS::DynamoDB::Table", 6)
