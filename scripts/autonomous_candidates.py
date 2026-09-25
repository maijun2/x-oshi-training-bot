#!/usr/bin/env python3
"""
独り言（自律投稿、3b-1）の材料選びを本番の推しの記憶で確認する（読み取り専用）

Lambda と同じ AutonomousSelector で facts を一覧し、除外理由・タイプ A/B の判定・選ばれる候補を表示する。
投稿履歴テーブル（imomaru-bot-post-history）の重複キーも読む（書き込みはしない）。
--brain を付けると、選ばれた候補でローカルの頭脳（agent/brain.py、Bedrock を直接呼ぶ）を実行して素案を表示する。
Buffer・メール・状態には触れない。

使い方:
    uv run python scripts/autonomous_candidates.py                          # 今の時刻で判定
    uv run python scripts/autonomous_candidates.py --at "2026-09-27 21:01"  # JST の時刻を指定
    uv run python scripts/autonomous_candidates.py --brain --runs 3         # ローカル頭脳で素案も作る
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from hokuhoku_imomaru_bot.memory_filters import (  # noqa: E402
    AUTONOMOUS_EXTRA_EXCLUDE_WORDS,
    extract_dates,
    is_event,
    is_fan_view,
    is_private_life,
)
from hokuhoku_imomaru_bot.services.ai_generator import format_jst  # noqa: E402
from hokuhoku_imomaru_bot.services.autonomous_selector import AutonomousSelector, select_from  # noqa: E402
from hokuhoku_imomaru_bot.services.buffer_scheduler import DEFAULT_SLOT_TIMES_JST, parse_slot_times  # noqa: E402
from hokuhoku_imomaru_bot.services.daily_reporter import JST  # noqa: E402
from hokuhoku_imomaru_bot.services.post_history_store import DEFAULT_TABLE_NAME, PostHistoryStore  # noqa: E402

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
STACK_NAME = os.environ.get("STACK_NAME", "ImomaruBotStack")
ACTOR_ID = os.environ.get("OSHI_ACTOR_ID", "juri_bigangel")


def resolve_memory_id() -> str:
    outputs = boto3.client("cloudformation", region_name=REGION).describe_stacks(
        StackName=STACK_NAME)["Stacks"][0].get("Outputs", [])
    for o in outputs:
        if o["OutputKey"] == "OshiMemoryId":
            return o["OutputValue"]
    raise SystemExit(f"Output OshiMemoryId not found in stack {STACK_NAME}")


def exclusion_reason(text: str) -> str:
    if is_fan_view(text):
        return "fan_view"
    if is_private_life(text):
        return "private_life"
    words = [w for w in AUTONOMOUS_EXTRA_EXCLUDE_WORDS if w in text]
    return f"extra({','.join(words)})" if words else ""


def next_slot(now: datetime) -> datetime:
    slots = parse_slot_times(",".join(DEFAULT_SLOT_TIMES_JST))
    now_jst = now.astimezone(JST)
    for slot in slots:
        candidate = datetime.combine(now_jst.date(), slot)
        if candidate > now_jst:
            return candidate
    return datetime.combine(now_jst.date() + timedelta(days=1), slots[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="独り言の材料選びの確認（読み取り専用）")
    parser.add_argument("--memory-id", help="Memory ID（省略時は CloudFormation Output から取得）")
    parser.add_argument("--at", help='判定する時刻（JST、"YYYY-MM-DD HH:MM"）。省略時は現在')
    parser.add_argument("--no-history", action="store_true", help="投稿履歴の重複キーを使わない")
    parser.add_argument("--brain", action="store_true", help="ローカルの頭脳で素案を作る（Bedrock を直接呼ぶ）")
    parser.add_argument("--runs", type=int, default=1, help="--brain の実行回数")
    args = parser.parse_args()

    now = (datetime.strptime(args.at, "%Y-%m-%d %H:%M").replace(tzinfo=JST) if args.at
           else datetime.now(timezone.utc))
    today = now.astimezone(JST).date()
    memory_id = args.memory_id or resolve_memory_id()

    records = AutonomousSelector(memory_id, ACTOR_ID, region=REGION).list_facts()
    print(f"now={format_jst(now)} facts={len(records)}\n")
    for r in sorted(records, key=lambda r: r.created_at, reverse=True):
        reason = exclusion_reason(r.text)
        dates = [d.isoformat() for d in extract_dates(r.text, r.created_at.astimezone(JST).year) if d >= today]
        tags = [t for t in (f"excluded:{reason}" if reason else "",
                            f"future:{','.join(dates)}" if dates else "",
                            "event" if is_event(r.text) else "") if t]
        print(f"{r.created_at.astimezone(JST):%m-%d %H:%M} {r.record_id[:16]} [{' '.join(tags)}] {r.text[:70]}")

    used_keys = set()
    recent_texts = []
    if not args.no_history:
        history_store = PostHistoryStore(table_name=os.environ.get("POST_HISTORY_TABLE_NAME", DEFAULT_TABLE_NAME))
        try:
            history = history_store.load_recent(today, 7)
            used_keys = history_store.used_keys(history)
            recent_texts = [e.text for e in history[:3]]
        except Exception as e:  # noqa: BLE001 — deploy 前はテーブルがない
            print(f"\n(history not available: {type(e).__name__})")
    print(f"\nused_keys={sorted(used_keys)}")

    selection = select_from(records, now, used_keys)
    if selection is None:
        print("selection: none (autonomous_skip reason=no_candidates)")
        return 0
    print(f"selection: kind={selection.kind} days_left={selection.days_left} event_date={selection.event_date}")
    for c in selection.candidates:
        print(f"  - {c.record_id} key={selection.keys[c.record_id]} {c.text[:80]}")

    if not args.brain:
        return 0

    sys.path.insert(0, str(project_root / "agent"))
    os.environ.setdefault("BEDROCK_REGION", REGION)
    import brain  # noqa: E402  （agent/brain.py。Memory の retrieve は autonomous では使わない）

    publish_at = next_slot(now)
    event_date = (f"{selection.event_date:%Y-%m-%d}" if selection.event_date else None)
    print(f"\npublish_at={format_jst(publish_at)}\n")
    for _ in range(args.runs):
        try:
            result = brain.autonomous(
                kind=selection.kind,
                candidates=[c.to_brain() for c in selection.candidates],
                now=format_jst(now),
                publish_at=format_jst(publish_at),
                days_left=selection.days_left,
                event_date=event_date,
                recent_texts=recent_texts,
            )
        except Exception as e:  # noqa: BLE001
            print(f"❌ {type(e).__name__}: {e}\n")
            continue
        print(f"✅ action={result['action']} emotion={result['emotion_key']} sources={result['sources']} "
              f"reason={result['reason']}")
        print("\n".join(f"   {line}" for line in result["text"].splitlines()) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
