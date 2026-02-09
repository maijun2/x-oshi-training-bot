#!/usr/bin/env python3
"""
朝コンテンツ（YouTube検索・翻訳）のドライランスクリプト

AgentCore Runtime のYouTube検索ツールと翻訳ツールの動作を確認する。

使い方:
    # YouTube検索のドライラン
    python scripts/test_morning_content.py youtube

    # 翻訳のドライラン
    python scripts/test_morning_content.py translate

    # 実際にX投稿する
    python scripts/test_morning_content.py youtube --post
    python scripts/test_morning_content.py translate --post

環境変数:
    AGENTCORE_RUNTIME_ARN: AgentCore Runtime の ARN
    SECRET_NAME: X API認証情報のシークレット名
    OSHI_USER_ID: 推しのXアカウントユーザーID
"""
import argparse
import json
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import boto3
from dotenv import load_dotenv

load_dotenv()

from src.hokuhoku_imomaru_bot.clients import XAPIClient
from src.hokuhoku_imomaru_bot.services.daily_reporter import (
    DailyReporter,
    YOUTUBE_PREFIX,
    TRANSLATION_PREFIX,
    MAX_TEXT_LENGTH,
)
from src.hokuhoku_imomaru_bot.utils.agentcore_runtime import invoke_agent_runtime
import src.hokuhoku_imomaru_bot.utils.agentcore_runtime as acr

AGENTCORE_RUNTIME_ARN = os.environ.get(
    "AGENTCORE_RUNTIME_ARN",
    "arn:aws:bedrock-agentcore:ap-northeast-1:353695163339:runtime/x_bot_supervisor-vA2jSJGGe0",
)
SECRET_NAME = os.environ.get("SECRET_NAME", "imomaru-bot/x-api-credentials")
OSHI_USER_ID = os.environ.get("OSHI_USER_ID", "1746898546341908480")


def get_x_api_client() -> XAPIClient:
    secrets_client = boto3.client("secretsmanager", region_name="ap-northeast-1")
    return XAPIClient(secrets_client=secrets_client, secret_name=SECRET_NAME)


def test_youtube_search(post: bool = False):
    """YouTube検索のドライラン/本番投稿"""
    print("🎬 YouTube検索テスト")
    print("=" * 50)

    # ARN設定
    os.environ["AGENTCORE_RUNTIME_ARN"] = AGENTCORE_RUNTIME_ARN
    acr.AGENTCORE_RUNTIME_ARN = AGENTCORE_RUNTIME_ARN

    prompt = (
        f"「甘木ジュリ」または「びっくえんじぇる」の最新YouTube動画を1件検索してください。"
        f"\n\n出力フォーマットの指定: "
        f"あなたは「ほくほくいも丸くん🍠」というキャラクターです。"
        f"語尾は必ず「◯◯ｲﾓ🍠」の形式にしてください。"
        f"回答は短い日本語プレーンテキストで改行区切りで出力してください。"
        f"Markdown記法は使わないでください。"
        f"YouTube動画のURL（https://youtu.be/動画ID の短縮形式）を必ず含めてください。"
        f"動画が見つからない場合は「新着なし」とだけ返してください。"
        f"以下のフォーマット例に従ってください:\n"
        f"じゅりちゃんの新着動画を見つけたｲﾓ🍠\n"
        f"📺 （動画タイトル）\n"
        f"🔗 （YouTube URL）\n"
        f"（再生数や投稿日の情報）ｲﾓ～🍠"
    )
    context = {
        "source": "imomaru-bot-handler",
        "request_type": "youtube_search",
        "user_id": OSHI_USER_ID,
    }

    print(f"\n📡 AgentCore Runtime 呼び出し中...")
    result = invoke_agent_runtime(prompt=prompt, context=context, timeout=120)

    print(f"\n📊 結果: success={result['success']}")
    if result["error"]:
        print(f"   Error: {result['error']}")
        return

    body = DailyReporter._extract_analysis_text(result["response"])
    print(f"\n📝 抽出テキスト ({len(body)}文字):")
    print(textwrap.indent(body, "   "))

    if not body or "新着なし" in body:
        print("\n⚠️ 新着動画なし。投稿はスキップされます。")
        return

    max_body_len = MAX_TEXT_LENGTH - len(YOUTUBE_PREFIX)
    body = DailyReporter._truncate_analysis(body, max_body_len)
    tweet_text = f"{YOUTUBE_PREFIX}{body}"

    print(f"\n📮 投稿テキスト ({len(tweet_text)}文字):")
    print(textwrap.indent(tweet_text, "   "))

    if not post:
        print("\n✅ ドライラン完了。投稿するには --post を付けてください。")
        return

    client = get_x_api_client()
    result = client.post_tweet(text=tweet_text)
    tweet_id = result.get("data", {}).get("id")
    if tweet_id:
        print(f"\n🎉 投稿完了: https://x.com/i/status/{tweet_id}")
    else:
        print(f"\n❌ 投稿失敗: {result}")


def test_translation(post: bool = False):
    """翻訳のドライラン/本番投稿"""
    print("🌎 翻訳テスト")
    print("=" * 50)

    os.environ["AGENTCORE_RUNTIME_ARN"] = AGENTCORE_RUNTIME_ARN
    acr.AGENTCORE_RUNTIME_ARN = AGENTCORE_RUNTIME_ARN

    prompt = (
        f"ユーザーID {OSHI_USER_ID} の最近のポストの中から、"
        f"いいねやリポストが最も多い人気ポストを1つ選んで、"
        f"元気なアイドル口調を維持したまま英語に翻訳してください。"
        f"\n\n出力フォーマットの指定: "
        f"あなたは「ほくほくいも丸くん🍠」というキャラクターです。"
        f"語尾は必ず「◯◯ｲﾓ🍠」の形式にしてください。"
        f"回答は短い日本語プレーンテキストで改行区切りで出力してください。"
        f"Markdown記法は使わないでください。"
        f"以下のフォーマット例に従ってください:\n"
        f"今週の人気ポストを翻訳したｲﾓ🍠\n"
        f"🌎 （英語翻訳）\n"
        f"いいね○件の人気ポストｲﾓ～🍠"
    )
    context = {
        "source": "imomaru-bot-handler",
        "request_type": "translation",
        "user_id": OSHI_USER_ID,
        "latest_post_id": os.environ.get("LATEST_TWEET_ID", "0"),
    }

    print(f"\n📡 AgentCore Runtime 呼び出し中...")
    result = invoke_agent_runtime(prompt=prompt, context=context, timeout=120)

    print(f"\n📊 結果: success={result['success']}")
    if result["error"]:
        print(f"   Error: {result['error']}")
        return

    body = DailyReporter._extract_analysis_text(result["response"])
    print(f"\n📝 抽出テキスト ({len(body)}文字):")
    print(textwrap.indent(body, "   "))

    if not body:
        print("\n⚠️ 翻訳結果が空。投稿はスキップされます。")
        return

    max_body_len = MAX_TEXT_LENGTH - len(TRANSLATION_PREFIX)
    body = DailyReporter._truncate_analysis(body, max_body_len)
    tweet_text = f"{TRANSLATION_PREFIX}{body}"

    print(f"\n📮 投稿テキスト ({len(tweet_text)}文字):")
    print(textwrap.indent(tweet_text, "   "))

    if not post:
        print("\n✅ ドライラン完了。投稿するには --post を付けてください。")
        return

    client = get_x_api_client()
    result = client.post_tweet(text=tweet_text)
    tweet_id = result.get("data", {}).get("id")
    if tweet_id:
        print(f"\n🎉 投稿完了: https://x.com/i/status/{tweet_id}")
    else:
        print(f"\n❌ 投稿失敗: {result}")


def main():
    parser = argparse.ArgumentParser(description="朝コンテンツ（YouTube/翻訳）テスト")
    parser.add_argument(
        "mode",
        choices=["youtube", "translate"],
        help="テストモード: youtube=YouTube検索, translate=翻訳",
    )
    parser.add_argument(
        "--post", action="store_true",
        help="実際にXに投稿する（省略時はドライラン）",
    )
    args = parser.parse_args()

    if args.mode == "youtube":
        test_youtube_search(post=args.post)
    else:
        test_translation(post=args.post)


if __name__ == "__main__":
    main()
