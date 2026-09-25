#!/usr/bin/env python3
"""
Buffer の予約投稿・スロットの確認スクリプト（読み取り専用）

日次確認で Buffer に載った投稿の状態（scheduled / sent）と本文、Posting Schedule を見る。
Buffer の公開 API ではスロットを変更できないので、UI で変えたあとの検証にも使う。

使い方:
    # Lambda ログ（直近 24 時間）の `Buffer post queued: id=…` から投稿を拾って表示
    python scripts/buffer_status.py --from-logs 24

    # post id を指定して表示
    python scripts/buffer_status.py 6ab5c94d4be54730309fadbd 6ab5f624cbe818dd4ff893e7

    # 曜日ごとのスロット（JST）を表示
    python scripts/buffer_status.py --slots

認証情報は Secrets Manager `imomaru-bot/buffer-api` から読む（トークンは表示しない）。
"""
import argparse
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import boto3

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from hokuhoku_imomaru_bot.clients.buffer_client import BufferClient  # noqa: E402

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
SECRET_NAME = os.environ.get("BUFFER_SECRET_NAME", "imomaru-bot/buffer-api")
LOG_GROUP = os.environ.get("LOG_GROUP_NAME", "/aws/lambda/imomaru-bot-handler")
JST = timezone(timedelta(hours=9))

_POST_QUERY = "query($id: PostId!){post(input:{id:$id}){id status dueAt sentAt text}}"
_SLOTS_QUERY = "query($id: ChannelId!){channel(input:{id:$id}){postingSchedule{day times paused}}}"
_QUEUED_ID = re.compile(r"Buffer post queued: id=(\w+)")


def to_jst(value: Optional[str]) -> str:
    """Buffer の ISO 8601（UTC）を JST 表記にする。未設定は "-" """
    if not value:
        return "-"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(JST).strftime("%m-%d %H:%M")


def post_ids_from_logs(hours: float) -> List[str]:
    """Lambda ログから直近 hours 時間に Buffer へ投入した post id を古い順に返す"""
    logs = boto3.client("logs", region_name=REGION)
    start_ms = int((time.time() - hours * 3600) * 1000)
    ids: List[str] = []
    for page in logs.get_paginator("filter_log_events").paginate(
        logGroupName=LOG_GROUP, startTime=start_ms, filterPattern='"Buffer post queued"',
    ):
        for event in page["events"]:
            match = _QUEUED_ID.search(event["message"])
            if match and match.group(1) not in ids:
                ids.append(match.group(1))
    return ids


def print_posts(client: BufferClient, post_ids: List[str]) -> None:
    for post_id in post_ids:
        post = client._graphql(_POST_QUERY, {"id": post_id})["post"]
        print(f"== {post['id']}  {post['status']}  due {to_jst(post['dueAt'])}  sent {to_jst(post['sentAt'])} (JST)")
        print(post["text"])
        print()


def print_slots(client: BufferClient) -> None:
    schedule = client._graphql(_SLOTS_QUERY, {"id": client.channel_id})["channel"]["postingSchedule"]
    for day in schedule:
        paused = "  (paused)" if day["paused"] else ""
        print(f"{day['day']}  {len(day['times'])} 枠  {' '.join(day['times'])}{paused}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Buffer の予約投稿・スロットの確認（読み取り専用）")
    parser.add_argument("post_ids", nargs="*", help="確認する post id")
    parser.add_argument("--from-logs", type=float, metavar="HOURS",
                        help="Lambda ログの直近 HOURS 時間から投入済みの post id を拾う")
    parser.add_argument("--slots", action="store_true", help="曜日ごとのスロット（JST）を表示")
    args = parser.parse_args()

    post_ids = list(args.post_ids)
    if args.from_logs:
        post_ids += [i for i in post_ids_from_logs(args.from_logs) if i not in post_ids]
        if not post_ids:
            print(f"直近 {args.from_logs:g} 時間に Buffer へ投入した投稿はありません")
    if not post_ids and not args.slots and not args.from_logs:
        parser.error("post id、--from-logs、--slots のいずれかを指定してください")

    client = BufferClient(secrets_client=boto3.client("secretsmanager", region_name=REGION), secret_name=SECRET_NAME)
    if post_ids:
        print_posts(client, post_ids)
    if args.slots:
        print_slots(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
