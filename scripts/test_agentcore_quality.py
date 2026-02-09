#!/usr/bin/env python3
"""
AgentCore Runtime レスポンス品質改善 — 修正テストスクリプト

3つのリクエストタイプ（ego_search, youtube_search, translation）に対して
バリデーション改善が正しく機能しているかを検証する。

使い方:
    # 全テスト実行（各2回）
    python scripts/test_agentcore_quality.py

    # 特定タイプのみ
    python scripts/test_agentcore_quality.py --type ego_search

    # 試行回数を指定
    python scripts/test_agentcore_quality.py --runs 3
"""
import argparse
import os
import re
import sys
import textwrap
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from src.hokuhoku_imomaru_bot.services.daily_reporter import DailyReporter
from src.hokuhoku_imomaru_bot.utils.agentcore_runtime import invoke_agent_runtime
import src.hokuhoku_imomaru_bot.utils.agentcore_runtime as acr

AGENTCORE_RUNTIME_ARN = os.environ.get(
    "AGENTCORE_RUNTIME_ARN",
    "arn:aws:bedrock-agentcore:ap-northeast-1:353695163339:runtime/x_bot_supervisor-vA2jSJGGe0",
)
OSHI_USER_ID = os.environ.get("OSHI_USER_ID", "1746898546341908480")

# テンプレートプレースホルダーのパターン
PLACEHOLDER_PATTERNS = [
    r"（一言まとめ）",
    r"（英語翻訳）",
    r"（特に盛り上がった話題）",
    r"（数値情報）",
    r"（動画タイトル）",
    r"（YouTube URL）",
    r"（再生数や投稿日の情報）",
    r"○件",
    r"○回",
]

# Markdown記法パターン
MARKDOWN_PATTERNS = [
    r"\*\*.+?\*\*",
    r"^#{1,6}\s",
    r"^-\s",
    r"```",
]


def check_common(response_text: str) -> list[str]:
    """共通バリデーション"""
    issues = []

    if not response_text or not response_text.strip():
        issues.append("❌ レスポンスが空")
        return issues

    if "ｲﾓ🍠" not in response_text and "ｲﾓ～🍠" not in response_text:
        issues.append("❌ 語尾「ｲﾓ🍠」が含まれない")

    for pat in PLACEHOLDER_PATTERNS:
        if re.search(pat, response_text):
            issues.append(f"❌ プレースホルダー残存: {pat}")

    for pat in MARKDOWN_PATTERNS:
        if re.search(pat, response_text, re.MULTILINE):
            issues.append(f"❌ Markdown記法検出: {pat}")

    if "<think>" in response_text:
        issues.append("❌ <think>タグが残存")

    if len(response_text) > 120:
        issues.append(f"⚠️ 120文字超過 ({len(response_text)}文字) — Bot側で切り詰め対応")

    return issues


def check_ego_search(response_text: str) -> list[str]:
    """ego_search 固有バリデーション"""
    issues = check_common(response_text)
    if not response_text:
        return issues

    keywords = ["リプライ", "分析", "反応", "コメント"]
    if not any(kw in response_text for kw in keywords):
        issues.append(f"❌ キーワード不足: {keywords} のいずれも含まれない")

    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U0001f900-\U0001f9FF"
        "\U00002600-\U000026FF"
        "\u2764\ufe0f"
        "\u2728"
        "\u2B50"
        "\u270C"
        "]+",
        flags=re.UNICODE,
    )
    if not emoji_pattern.search(response_text):
        issues.append("❌ 絵文字が1つも含まれない")

    return issues


def check_youtube_search(response_text: str) -> list[str]:
    """youtube_search 固有バリデーション"""
    issues = check_common(response_text)
    if not response_text:
        return issues

    if "新着なし" in response_text:
        return ["ℹ️ 新着なし（バリデーションスキップ）"]

    if "youtu.be/" in response_text:
        pass  # OK
    elif "youtube.com/watch" in response_text:
        issues.append("❌ YouTube URLが長形式 (youtube.com/watch) — youtu.be/ 形式であるべき")
    else:
        issues.append("⚠️ YouTube URLが見つからない")

    return issues


def check_translation(response_text: str) -> list[str]:
    """translation 固有バリデーション"""
    issues = check_common(response_text)
    if not response_text:
        return issues

    ascii_chars = sum(1 for c in response_text if ord(c) < 128 and c.isalpha())
    if ascii_chars < 10:
        issues.append(f"❌ 英語テキスト不足 (ASCII英字{ascii_chars}文字)")

    keywords = ["いいね", "人気", "翻訳"]
    if not any(kw in response_text for kw in keywords):
        issues.append(f"⚠️ キーワード不足: {keywords} のいずれも含まれない")

    if "tan【EN】" in response_text or "tan[EN]" in response_text:
        issues.append("❌ 余計なテキスト「tan【EN】」が混入")

    return issues


# テストケース定義
TEST_CASES = {
    "ego_search": {
        "label": "🔍 エゴサ分析",
        "prompt": (
            f"推しのXアカウント(user_id: {OSHI_USER_ID})のリプライを分析してください。"
            f"latest_post_id は 0 で。"
        ),
        "context": {
            "source": "imomaru-bot-handler",
            "request_type": "ego_search",
            "user_id": OSHI_USER_ID,
            "latest_post_id": "0",
        },
        "checker": check_ego_search,
    },
    "youtube_search": {
        "label": "🎬 YouTube検索",
        "prompt": "「いもまる」の最新YouTube動画を3件検索してください",
        "context": {
            "source": "imomaru-bot-handler",
            "request_type": "youtube_search",
            "user_id": OSHI_USER_ID,
        },
        "checker": check_youtube_search,
    },
    "translation": {
        "label": "🌎 翻訳",
        "prompt": (
            "「今日のライブ最高だった！みんなの声援が力になったよ」を英語に翻訳してください。"
            "元気なアイドルの口調で。"
        ),
        "context": {
            "source": "imomaru-bot-handler",
            "request_type": "translation",
            "user_id": OSHI_USER_ID,
            "latest_post_id": "0",
        },
        "checker": check_translation,
    },
}


def run_single_test(request_type: str, run_num: int) -> dict:
    """1回のテスト実行"""
    tc = TEST_CASES[request_type]
    print(f"\n{'─' * 60}")
    print(f"{tc['label']} — 試行 {run_num}")
    print(f"{'─' * 60}")

    start = time.time()
    result = invoke_agent_runtime(
        prompt=tc["prompt"],
        context=tc["context"],
        timeout=120,
    )
    elapsed = time.time() - start

    print(f"  success: {result['success']}  ({elapsed:.1f}s)")

    if result["error"]:
        print(f"  error: {result['error']}")

    if not result["success"]:
        return {"pass": False, "issues": ["❌ success=False"], "elapsed": elapsed}

    # Bot側の後処理を通す（フォールバック確認）
    raw = result["response"]
    cleaned = DailyReporter._extract_analysis_text(raw)

    print(f"  raw length: {len(raw)}文字")
    print(f"  cleaned length: {len(cleaned)}文字")
    print(f"  response:")
    print(textwrap.indent(cleaned[:300] if len(cleaned) > 300 else cleaned, "    "))

    # バリデーション
    issues = tc["checker"](cleaned)

    has_validation_warning = (
        result["error"] is not None
        and "validation_warnings" in str(result["error"])
    )
    if has_validation_warning:
        issues.append("⚠️ validation_warnings あり（全リトライ失敗後のクリーンアップ）")

    errors = [i for i in issues if i.startswith("❌")]
    warnings = [i for i in issues if i.startswith("⚠️")]
    infos = [i for i in issues if i.startswith("ℹ️")]

    if issues:
        print(f"\n  検証結果:")
        for issue in issues:
            print(f"    {issue}")
    else:
        print(f"\n  ✅ 全検証パス")

    passed = len(errors) == 0
    return {"pass": passed, "issues": issues, "elapsed": elapsed}


def main():
    parser = argparse.ArgumentParser(description="AgentCore Runtime レスポンス品質テスト")
    parser.add_argument(
        "--type",
        choices=["ego_search", "youtube_search", "translation"],
        help="テストするリクエストタイプ（省略時は全タイプ）",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="各タイプの試行回数（デフォルト: 2）",
    )
    args = parser.parse_args()

    # ARN設定
    os.environ["AGENTCORE_RUNTIME_ARN"] = AGENTCORE_RUNTIME_ARN
    acr.AGENTCORE_RUNTIME_ARN = AGENTCORE_RUNTIME_ARN

    types = [args.type] if args.type else list(TEST_CASES.keys())

    print("=" * 60)
    print("AgentCore Runtime レスポンス品質テスト")
    print(f"対象: {', '.join(types)}  |  試行回数: {args.runs}")
    print(f"ARN: {AGENTCORE_RUNTIME_ARN}")
    print("=" * 60)

    all_results = {}
    for rt in types:
        all_results[rt] = []
        for run in range(1, args.runs + 1):
            r = run_single_test(rt, run)
            all_results[rt].append(r)

    # サマリー
    print(f"\n{'=' * 60}")
    print("📊 テストサマリー")
    print(f"{'=' * 60}")

    total_pass = 0
    total_fail = 0
    total_warn = 0

    for rt, results in all_results.items():
        tc = TEST_CASES[rt]
        passes = sum(1 for r in results if r["pass"])
        fails = len(results) - passes
        avg_time = sum(r["elapsed"] for r in results) / len(results)

        total_pass += passes
        total_fail += fails

        status = "✅" if fails == 0 else "❌"
        print(f"\n  {status} {tc['label']}: {passes}/{len(results)} パス  (平均 {avg_time:.1f}s)")

        for i, r in enumerate(results, 1):
            warnings = [iss for iss in r["issues"] if iss.startswith("⚠️")]
            errors = [iss for iss in r["issues"] if iss.startswith("❌")]
            total_warn += len(warnings)
            if errors or warnings:
                for iss in errors + warnings:
                    print(f"      試行{i}: {iss}")

    print(f"\n{'─' * 60}")
    total = total_pass + total_fail
    print(f"  合計: {total_pass}/{total} パス, {total_fail} 失敗, {total_warn} 警告")

    if total_fail == 0:
        print("  🎉 全テストパス！レスポンス品質改善が正常に機能しています。")
    else:
        print("  ⚠️ 一部テストが失敗しました。詳細を確認してください。")

    print(f"{'=' * 60}")
    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
