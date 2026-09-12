"""
AgentCore Runtime のエントリポイント（direct code deploy: entryPoint=["main.py"]）

POST /invocations にペイロードを受け取り brain.handle() に渡す。GET /ping は SDK が提供する。
ローカル確認:
    uv run python agent/main.py
    curl -X POST localhost:8080/invocations -H 'Content-Type: application/json' \
      -d '{"task":"oshi_response","input":{"post_content":"今日はライブでした！","post_type":"oshi"}}'
"""
import logging
import os
import sys

# デプロイパッケージでは brain.py / prompts.py が main.py と同じ階層に置かれる
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402

import brain  # noqa: E402

logging.basicConfig(level=logging.INFO)

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    return brain.handle(payload)


if __name__ == "__main__":
    app.run()
