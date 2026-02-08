#!/usr/bin/env python3
"""
エゴサ分析スレッド投稿の動作テストスクリプト

日報投稿の代わりにテスト用ツイートを投稿し、そのリプライとして
AgentCore Runtime のエゴサ分析結果をスレッド形式で投稿する。

使い方:
    # ドライラン（実際には投稿しない）
    python scripts/test_ego_search_thread.py

    # 実際にX投稿する
    python scripts/test_ego_search_thread.py --post

    # 既存ツイートにリプライする（日報投稿済みの場合）
    python scripts/test_ego_search_thread.py --post --reply-to 1234567890

環境変数:
    AGENTCORE_RUNTIME_ARN: AgentCore Runtime の ARN
    SECRET_NAME: X API認証情報のシークレット名
    OSHI_USER_ID: 推しのXアカウントユーザーID
"""
import argparse
import json
import os
import re
import sys
import textwrap
import uuid

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import boto3
from dotenv import load_dotenv

load_dotenv()

from src.hokuhoku_imomaru_bot.clients import XAPIClient
from src.hokuhoku_imomaru_bot.utils.agentcore_runtime import invoke_agent_runtime


# 定数
AGENTCORE_RUNTIME_ARN = os.environ.get(
    "AGENTCORE_RUNTIME_ARN",
    "arn:aws:bedrock-agentcore:ap-northeast-1:353695163339:runtime/x_bot_supervisor-vA2jSJGGe0",
)
SECRET_NAME = os.environ.get("SECRET_NAME", "imomaru-bot/x-api-credentials")
OSHI_USER_ID = os.environ.get("OSHI_USER_ID", "1746898546341908480")

# ツイート文字数上限（既存ボットのルールに合わせて140文字）
TWEET_MAX_LENGTH = 140


def get_x_api_client() -> XAPIClient:
    """X APIクライアントを初期化"""
    secrets_client = boto3.client("secretsmanager", region_name="ap-northeast-1")
    return XAPIClient(secrets_client=secrets_client, secret_name=SECRET_NAME)


def call_ego_search(latest_tweet_id: str = "0") -> dict:
    """
    AgentCore Runtime のエゴサ分析を呼び出す

    Args:
        latest_tweet_id: 分析対象の起点ツイートID

    Returns:
        AgentCore Runtime のレスポンス
    """
    # AGENTCORE_RUNTIME_ARN を一時的に環境変数にセット（モジュールが参照するため）
    os.environ["AGENTCORE_RUNTIME_ARN"] = AGENTCORE_RUNTIME_ARN

    # agentcore_runtime モジュールのグローバル変数を更新
    import src.hokuhoku_imomaru_bot.utils.agentcore_runtime as acr
    acr.AGENTCORE_RUNTIME_ARN = AGENTCORE_RUNTIME_ARN

    prompt = (
        f"ユーザーID {OSHI_USER_ID} の最新ポストへのリプライを分析して、"
        f"ファンの反応をポジティブな内容を中心に要約・報告してください。"
        f"\n\n出力フォーマットの指定: "
        f"回答は短い日本語プレーンテキストで簡潔に出力してください。"
        f"Markdown記法（#や**や-）は使わないでください。"
        f"絵文字は1〜2個まで。件数などの数値情報を含めてください。"
    )
    context = {
        "source": "imomaru-bot-handler",
        "request_type": "ego_search",
        "user_id": OSHI_USER_ID,
        "latest_post_id": latest_tweet_id,
    }

    print(f"\n📡 AgentCore Runtime 呼び出し中...")
    print(f"   ARN: {AGENTCORE_RUNTIME_ARN}")
    print(f"   Prompt: {prompt[:80]}...")
    print(f"   Context: {json.dumps(context, ensure_ascii=False)}")

    result = invoke_agent_runtime(
        prompt=prompt,
        context=context,
        timeout=120,
    )

    return result


def split_for_thread(text: str, prefix: str = "") -> list[str]:
    """
    長いテキストをツイート文字数制限に合わせて分割する

    Args:
        text: 分割するテキスト
        prefix: 各ツイートの先頭に付けるプレフィックス

    Returns:
        分割されたテキストのリスト
    """
    max_len = TWEET_MAX_LENGTH - len(prefix)
    if len(text) + len(prefix) <= TWEET_MAX_LENGTH:
        return [f"{prefix}{text}"]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) + len(prefix) <= TWEET_MAX_LENGTH:
            chunks.append(f"{prefix}{remaining}")
            break

        # 文の区切りで分割を試みる
        split_pos = max_len
        for sep in ["。\n", "。", "\n", "、", " "]:
            pos = remaining[:max_len].rfind(sep)
            if pos > 0:
                split_pos = pos + len(sep)
                break

        chunks.append(f"{prefix}{remaining[:split_pos]}")
        remaining = remaining[split_pos:]

    return chunks


def post_reply(
    client: XAPIClient,
    text: str,
    reply_to_tweet_id: str,
) -> dict | None:
    """
    リプライ（スレッド）としてツイートを投稿する

    post_tweet に reply 機能がまだないため、request_v2 を直接使う。

    Args:
        client: XAPIClient
        text: ツイート本文
        reply_to_tweet_id: リプライ先のツイートID

    Returns:
        投稿結果 or None
    """
    json_data = {
        "text": text,
        "reply": {
            "in_reply_to_tweet_id": reply_to_tweet_id,
        },
    }
    try:
        result = client.request_v2("POST", "/tweets", json_data=json_data, use_oauth=True)
        return result
    except Exception as e:
        print(f"   ❌ 投稿失敗: {e}")
        return None


def _extract_response_text(raw: str) -> str:
    """
    AgentCore Runtime のレスポンスから投稿用テキストを抽出する

    - JSON文字列の場合は response フィールドを取り出す
    - <think>...</think> タグ（Kimi K2 Thinking の思考過程）を除去
    - Markdown記法をプレーンテキストに変換
    """
    text = raw

    # JSON文字列の場合、responseフィールドを抽出
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "response" in parsed:
            text = parsed["response"]
    except (json.JSONDecodeError, TypeError):
        pass

    # エスケープされた改行を実際の改行に（<think>除去の前に処理）
    text = text.replace("\\n", "\n")

    # <think> タグの中身を保持（フォールバック用）
    think_content = ""
    think_match = re.search(r"<think>(.*?)(?:</think>|$)", text, flags=re.DOTALL)
    if think_match:
        think_content = think_match.group(1)

    # <think>...</think> タグを除去（閉じタグがない場合も対応）
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)

    # JSON の残骸を除去（", "key": value} のようなパターン）
    cleaned = re.sub(r'^[\s,"]+\s*"?\w+"?\s*:.*', "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip()

    # 思考過程のみで本文が空の場合、思考内容から要約を抽出
    if not cleaned and think_content:
        sentences = [s.strip() for s in re.split(r"[。\n]", think_content) if s.strip()]
        if sentences:
            cleaned = sentences[-1]

    # Markdown記法を簡易的にプレーンテキスト化
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"---+", "", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

    # 連続する空行を1つに
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # ツイートID（15桁以上の数字列）とその周辺の括弧・記号を除去
    cleaned = re.sub(r"[（(]\d{15,}[）)]", "", cleaned)
    cleaned = re.sub(r"\d{15,}", "", cleaned)

    return cleaned.strip()


def main():
    parser = argparse.ArgumentParser(description="エゴサ分析スレッド投稿テスト")
    parser.add_argument(
        "--post", action="store_true",
        help="実際にXに投稿する（省略時はドライラン）",
    )
    parser.add_argument(
        "--reply-to",
        help="リプライ先のツイートID（日報投稿のIDを指定）",
    )
    parser.add_argument(
        "--latest-tweet-id", default="0",
        help="エゴサ分析の起点ツイートID（デフォルト: 0）",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("🧪 エゴサ分析スレッド投稿テスト")
    print(f"   モード: {'本番投稿' if args.post else 'ドライラン'}")
    print("=" * 60)

    # Step 1: AgentCore Runtime でエゴサ分析
    ego_result = call_ego_search(args.latest_tweet_id)

    print(f"\n📊 AgentCore Runtime 結果:")
    print(f"   Success: {ego_result['success']}")
    if ego_result["error"]:
        print(f"   Error: {ego_result['error']}")
        sys.exit(1)

    raw_response = ego_result["response"]

    # AgentCore のレスポンスが JSON 文字列の場合、response フィールドを抽出
    response_text = _extract_response_text(raw_response)

    print(f"   Response ({len(response_text)}文字):")
    print(textwrap.indent(response_text[:500], "   "))
    if len(response_text) > 500:
        print(f"   ... (残り{len(response_text) - 500}文字)")

    # Step 2: 140文字制限に合わせて整形
    thread_prefix = "🔍 今日のポスト分析ｲﾓ🍠\n"
    max_body_len = TWEET_MAX_LENGTH - len(thread_prefix)

    body = response_text
    if len(body) > max_body_len:
        # 末尾の要約文を探す（「全体として」「まとめると」等で始まる文）
        summary_markers = ["全体として", "まとめると", "総じて", "結論として", "全体的に"]
        summary = ""
        for marker in summary_markers:
            pos = body.rfind(marker)
            if pos >= 0:
                summary = body[pos:]
                break

        if summary and len(summary) + 10 < max_body_len:
            # 冒頭の数値情報 + 末尾の要約を組み合わせ
            first_line_end = body.find("\n")
            if first_line_end > 0 and first_line_end + len(summary) + 1 <= max_body_len:
                body = body[:first_line_end] + "\n" + summary
            else:
                body = summary
        else:
            # 文の区切りで切り詰め
            truncated = body[:max_body_len]
            for sep in ["。", "！", "✨", "💜", "🎀", "\n"]:
                pos = truncated.rfind(sep)
                if pos > max_body_len // 2:
                    truncated = truncated[:pos + len(sep)]
                    break
            body = truncated

    tweet_text = f"{thread_prefix}{body}"
    tweets = [tweet_text]

    print(f"\n📝 投稿内容 ({len(tweet_text)}文字):")
    print(textwrap.indent(tweet_text, "   "))

    # Step 3: 投稿（またはドライラン）
    if not args.post:
        print("\n✅ ドライラン完了。実際に投稿するには --post を付けてください。")
        return

    client = get_x_api_client()
    reply_to_id = args.reply_to

    # reply-to が指定されていない場合、テスト用の日報ツイートを投稿
    if not reply_to_id:
        print("\n📮 テスト用日報ツイートを投稿中...")
        test_report = (
            "【テスト】今日の活動報告ｲﾓ🍠\n"
            "これはエゴサ分析スレッドのテスト投稿です。"
        )
        result = client.post_tweet(test_report)
        reply_to_id = result.get("data", {}).get("id")
        if not reply_to_id:
            print(f"   ❌ テスト投稿のID取得失敗: {result}")
            sys.exit(1)
        print(f"   ✅ テスト日報投稿完了: {reply_to_id}")

    # スレッドとしてリプライ投稿
    print(f"\n📮 スレッド投稿中（リプライ先: {reply_to_id}）...")
    current_reply_to = reply_to_id

    for i, tweet_text in enumerate(tweets):
        result = post_reply(client, tweet_text, current_reply_to)
        if result:
            new_id = result.get("data", {}).get("id")
            print(f"   ✅ ツイート {i + 1}/{len(tweets)} 投稿完了: {new_id}")
            if new_id:
                current_reply_to = new_id  # 次のリプライ先を更新（スレッドを繋げる）
        else:
            print(f"   ❌ ツイート {i + 1} で中断")
            break

    print(f"\n🎉 完了！スレッドURL:")
    print(f"   https://x.com/i/status/{reply_to_id}")


if __name__ == "__main__":
    main()
