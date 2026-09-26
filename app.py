#!/usr/bin/env python3
"""
AWS CDK アプリケーションエントリーポイント
"""
import aws_cdk as cdk
from src.hokuhoku_imomaru_bot.infrastructure.stack import ImomaruBotStack


app = cdk.App()

ImomaruBotStack(
    app,
    "ImomaruBotStack",
    # CloudFormation の GetTemplate / DescribeStacks は非 ASCII を "?" にして返すため、スタックの説明は ASCII で書く
    description="Hokuhoku Imomaru-kun training bot - AWS Serverless Stack",
)

app.synth()
