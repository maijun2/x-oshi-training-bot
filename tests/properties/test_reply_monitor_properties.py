"""
ReplyMonitorのプロパティテスト

Feature: group-quote-removal-and-reply-feature
Property 6: ボット投稿へのリプライフィルタリング
Validates: Requirements 3.4, 3.5
"""
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from unittest.mock import MagicMock
from src.hokuhoku_imomaru_bot.services.reply_monitor import ReplyMonitor


# ストラテジー: ツイートIDとユーザーID
tweet_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Nd",)),
    min_size=1,
    max_size=20,
).filter(lambda x: x.isdigit())

user_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Nd",)),
    min_size=1,
    max_size=20,
).filter(lambda x: x.isdigit())

username_st = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=1,
    max_size=15,
)

text_st = st.text(min_size=1, max_size=280)


def _make_mention(tweet_id, author_id, in_reply_to_user_id):
    """テスト用メンションデータを生成"""
    return {
        "id": tweet_id,
        "text": f"@bot テスト {tweet_id}",
        "author_id": author_id,
        "created_at": "2026-01-15T10:00:00Z",
        "in_reply_to_user_id": in_reply_to_user_id,
        "referenced_tweets": [{"type": "replied_to", "id": f"ref_{tweet_id}"}],
    }


# Feature: group-quote-removal-and-reply-feature
# Property 6: ボット投稿へのリプライフィルタリング
# For any メンションリストに対して、システムはin_reply_to_user_idがボットの
# ユーザーIDと一致するメンションのみをリプライとしてフィルタリングする
@settings(max_examples=100)
@given(
    bot_user_id=user_id_st,
    bot_reply_ids=st.lists(tweet_id_st, min_size=0, max_size=10),
    bot_reply_author_ids=st.lists(user_id_st, min_size=0, max_size=10),
    other_reply_ids=st.lists(tweet_id_st, min_size=0, max_size=10),
    other_reply_author_ids=st.lists(user_id_st, min_size=0, max_size=10),
    other_user_ids=st.lists(user_id_st, min_size=0, max_size=10),
)
def test_property_6_reply_filtering(
    bot_user_id,
    bot_reply_ids,
    bot_reply_author_ids,
    other_reply_ids,
    other_reply_author_ids,
    other_user_ids,
):
    """
    Property 6: ボット投稿へのリプライフィルタリング

    任意のメンションリストに対して:
    - in_reply_to_user_id == bot_user_id のメンションのみがリプライとして返される
    - in_reply_to_user_id != bot_user_id のメンションは除外される
    - 返されるリプライ数 <= 全メンション数
    """
    # ボットへのリプライを生成
    bot_replies = []
    for i, tid in enumerate(bot_reply_ids):
        aid = bot_reply_author_ids[i % max(len(bot_reply_author_ids), 1)] if bot_reply_author_ids else "100"
        # author_idがbot_user_idと同じ場合はスキップ（自分自身へのリプライは通常ない）
        bot_replies.append(_make_mention(f"bot_{tid}_{i}", aid, bot_user_id))

    # 他ユーザーへのリプライを生成
    other_replies = []
    for i, tid in enumerate(other_reply_ids):
        aid = other_reply_author_ids[i % max(len(other_reply_author_ids), 1)] if other_reply_author_ids else "200"
        target_id = other_user_ids[i % max(len(other_user_ids), 1)] if other_user_ids else "300"
        # target_idがbot_user_idと同じにならないようにする
        if target_id == bot_user_id:
            target_id = f"{target_id}_other"
        other_replies.append(_make_mention(f"other_{tid}_{i}", aid, target_id))

    all_mentions = bot_replies + other_replies

    # モッククライアントを設定
    mock_client = MagicMock()
    mock_client.get_user_mentions.return_value = {
        "data": all_mentions,
        "includes": {"users": []},
    }

    monitor = ReplyMonitor(api_client=mock_client, bot_user_id=bot_user_id)
    detected = monitor.detect_replies()

    # プロパティ検証:
    # 1. 検出されたリプライ数はボットへのリプライ数と一致
    assert len(detected) == len(bot_replies)

    # 2. 全ての検出されたリプライのin_reply_to_user_idがbot_user_idと一致
    for reply in detected:
        assert reply.in_reply_to_user_id == bot_user_id

    # 3. 検出されたリプライ数 <= 全メンション数
    assert len(detected) <= len(all_mentions)


# Property 6 補足: 空のメンションリストに対する動作
@settings(max_examples=100)
@given(bot_user_id=user_id_st)
def test_property_6_empty_mentions_returns_empty(bot_user_id):
    """
    Property 6 補足: メンションが空の場合、リプライも空

    任意のbot_user_idに対して、メンションリストが空なら
    検出されるリプライも空であること。
    """
    mock_client = MagicMock()
    mock_client.get_user_mentions.return_value = {"data": []}

    monitor = ReplyMonitor(api_client=mock_client, bot_user_id=bot_user_id)
    detected = monitor.detect_replies()

    assert detected == []
