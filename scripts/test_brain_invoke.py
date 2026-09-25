#!/usr/bin/env python3
"""
頭脳（AgentCore Runtime）の本番疎通確認

deploy 後に Runtime を invoke し、3 タスク（react / autonomous / reply_response）の応答と所要時間を表示する。
Lambda と同じ BrainClient を使うので、Lambda 側の経路（セッション ID・レスポンス解釈）も同時に確認できる。

使い方:
    uv run python scripts/test_brain_invoke.py                # ARN は CloudFormation Output から取得
    uv run python scripts/test_brain_invoke.py --arn <arn>    # ARN を直接指定
    uv run python scripts/test_brain_invoke.py --task react --text "今日は撮影！"
    uv run python scripts/test_brain_invoke.py --task react --runs 5   # JSON 提案の安定性（パース成功率・action 分布）
    uv run python scripts/test_brain_invoke.py --task autonomous --runs 5   # 独り言（3b-1）。サンプルは生誕祭のカウントダウン
"""
import argparse
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from hokuhoku_imomaru_bot.services.ai_generator import format_jst  # noqa: E402
from hokuhoku_imomaru_bot.utils.brain_client import BrainClient, BrainError  # noqa: E402

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
STACK_NAME = os.environ.get("STACK_NAME", "ImomaruBotStack")

# 深夜の投稿を朝に検知し、次の枠で公開される想定（時刻依存の挨拶が公開時刻に合うかを見る）
_NOW = datetime.now(timezone.utc)
SAMPLE_TASKS = [
    ("react", {
        "post_content": "今日は生誕祭ライブでした！みんな来てくれてありがとう🍠 おやすみ〜",
        "post_type": "oshi",
        "posted_at": format_jst(_NOW - timedelta(hours=8)),
        "now": format_jst(_NOW),
        "publish_at": format_jst(_NOW + timedelta(hours=1)),
    }),
    # 21:01 回に推し投稿がなく、facts の未来イベント（タイプ A）から独り言を作る想定（本番 Memory の実レコード由来）
    ("autonomous", {
        "kind": "A",
        "candidates": [{
            "id": "mem-83432411-dd1e-4a5e-a05d-129e27862093",
            "text": "甘木ジュリは2026年9月28日に生誕祭を開催予定。2026年9月25日時点でもチケットがまだ販売中で、"
                    "ご試食チケットは1000円。特典会の時間が変更になった。",
            "created_at": "2026-09-25 23:59 JST",
        }],
        "now": format_jst(_NOW),
        "publish_at": format_jst(_NOW + timedelta(hours=1)),
        "days_left": 2,
        "event_date": "2026-09-28(月)",
        "recent_texts": [],
    }),
    ("reply_response", {"reply_text": "いも丸くん今日もかわいいね", "reply_username": "fan_taro",
                        "bot_tweet_text": "ジュリちゃんのライブ最高だったｲﾓ🍠 #さつまいもの民 #びっくえんじぇる"}),
]


def resolve_runtime_arn() -> str:
    cfn = boto3.client("cloudformation", region_name=REGION)
    outputs = cfn.describe_stacks(StackName=STACK_NAME)["Stacks"][0].get("Outputs", [])
    for o in outputs:
        if o["OutputKey"] == "BrainRuntimeArn":
            return o["OutputValue"]
    raise SystemExit(f"Output BrainRuntimeArn not found in stack {STACK_NAME}")


def main() -> int:
    parser = argparse.ArgumentParser(description="頭脳 Runtime の疎通確認")
    parser.add_argument("--arn", help="Runtime ARN（省略時は CloudFormation Output から取得）")
    parser.add_argument("--task", choices=[t for t, _ in SAMPLE_TASKS], help="1 タスクだけ実行")
    parser.add_argument("--text", help="--task と併用。react の post_content / reply_response の reply_text（autonomous は未対応）")
    parser.add_argument("--runs", type=int, default=1, help="各タスクの実行回数（react の JSON 安定性確認用）")
    args = parser.parse_args()

    arn = args.arn or resolve_runtime_arn()
    print(f"Runtime: {arn}")
    client = BrainClient(runtime_arn=arn, region=REGION)
    print(f"Session: {client.session_id}\n")

    tasks = SAMPLE_TASKS
    if args.task:
        task_input = dict(next(i for t, i in SAMPLE_TASKS if t == args.task))
        if args.text and args.task != "autonomous":
            task_input["post_content" if args.task == "react" else "reply_text"] = args.text
        tasks = [(args.task, task_input)]

    failed = 0
    actions: Counter = Counter()
    for task, task_input in tasks:
        for _ in range(args.runs):
            started = time.time()
            try:
                if task in ("react", "autonomous"):
                    result = client.invoke_json(task, task_input)
                    actions[result["action"]] += 1
                    sources = f" sources={result['sources']}" if "sources" in result else ""
                    print(
                        f"✅ {task} ({time.time() - started:.1f}s) action={result['action']} "
                        f"emotion={result['emotion_key']} memories={result.get('memory_count')}{sources} "
                        f"reason={result['reason']}\n"
                        + "\n".join(f"   {line}" for line in result["text"].splitlines()) + "\n"
                    )
                else:
                    text = client.invoke(task, task_input)
                    print(f"✅ {task} ({time.time() - started:.1f}s, {len(text)} chars)\n   {text}\n")
            except BrainError as e:
                failed += 1
                print(f"❌ {task} ({time.time() - started:.1f}s)\n   {e}\n")

    if args.runs > 1 and actions:
        total = sum(actions.values())
        print(f"JSON tasks: parsed {total}/{total + failed}, actions={dict(actions)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
