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
    description="ほくほくいも丸くん育成ボット - AWS Serverless Stack",
)

app.synth()
