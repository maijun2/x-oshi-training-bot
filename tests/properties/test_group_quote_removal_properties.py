"""
グループオリジナル投稿の引用ポスト停止に関するプロパティベーステスト

Feature: group-quote-removal-and-reply-feature
Property 1: グループオリジナル投稿のXP加算とカウント更新
Property 2: グループオリジナル投稿の引用ポスト停止
Property 3: グループオリジナル投稿のAI生成停止
Property 4: グループリツイートの既存動作維持
Property 5: 推しオリジナル投稿の既存動作維持
"""
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import MagicMock, patch

from src.hokuhoku_imomaru_bot.lambda_handler import _process_bot_logic
from src.hokuhoku_imomaru_bot.models import BotState
from src.hokuhoku_imomaru_bot.services import (
    StateStore,
    TimelineMonitor,
    Tweet,
    XPCalculator,
    LevelManager,
    AIGenerator,
    ImageCompositor,
    ProfileUpdater,
    DailyReporter,
    ReplyMonitor,
    AllowedUsersService,
    ReplyProcessor,
)


# ============================================
# Strategies
# ============================================

def tweet_id_strategy():
    """有効なツイートIDを生成するストラテジー"""
    return st.integers(min_value=1, max_value=10**18).map(str)


def original_tweet_strategy():
    """オリジナル投稿のTweetを生成するストラテジー"""
    return st.builds(
        Tweet,
        id=tweet_id_strategy(),
        text=st.text(min_size=1, max_size=280),
        author_id=st.just("group_user_id"),
        is_retweet=st.just(False),
        is_reply=st.just(False),
        is_quote_tweet=st.just(False),
    )


def retweet_strategy():
    """リツイートのTweetを生成するストラテジー"""
    return st.builds(
        Tweet,
        id=tweet_id_strategy(),
        text=st.text(min_size=1, max_size=280),
        author_id=st.just("group_user_id"),
        is_retweet=st.just(True),
        is_reply=st.just(False),
        is_quote_tweet=st.just(False),
    )


def oshi_original_tweet_strategy():
    """推しオリジナル投稿のTweetを生成するストラテジー"""
    return st.builds(
        Tweet,
        id=tweet_id_strategy(),
        text=st.text(min_size=1, max_size=280),
        author_id=st.just("oshi_user_id"),
        is_retweet=st.just(False),
        is_reply=st.just(False),
        is_quote_tweet=st.just(False),
    )


def _make_mocks(state, group_original=None, group_retweets=None,
                oshi_original=None, oshi_retweets=None):
    """テスト用のモックオブジェクトを生成するヘルパー"""
    group_original = group_original or []
    group_retweets = group_retweets or []
    oshi_original = oshi_original or []
    oshi_retweets = oshi_retweets or []

    all_group = group_original + group_retweets
    all_oshi = oshi_original + oshi_retweets

    state_store = MagicMock(spec=StateStore)
    state_store.reset_daily_counts.return_value = state

    timeline_monitor = MagicMock(spec=TimelineMonitor)
    timeline_monitor.check_oshi_timeline.return_value = all_oshi
    timeline_monitor.check_group_timeline.return_value = all_group
    timeline_monitor.filter_original_posts.side_effect = (
        lambda tweets: [t for t in tweets if not t.is_retweet and not t.is_reply]
    )
    timeline_monitor.filter_retweets.side_effect = (
        lambda tweets: [t for t in tweets if t.is_retweet]
    )

    level_manager = MagicMock(spec=LevelManager)
    level_manager.check_level_up.return_value = (False, state.current_level)

    ai_generator = MagicMock(spec=AIGenerator)
    ai_generator.generate_response.return_value = "応答テキスト"

    image_compositor = MagicMock(spec=ImageCompositor)
    profile_updater = MagicMock(spec=ProfileUpdater)

    daily_reporter = MagicMock(spec=DailyReporter)
    daily_reporter.should_post_daily_report.return_value = False

    x_api_client = MagicMock()
    x_api_client.post_tweet.return_value = {"data": {"id": "999"}}

    reply_monitor = MagicMock(spec=ReplyMonitor)
    reply_monitor.detect_replies.return_value = []

    allowed_users_service = MagicMock(spec=AllowedUsersService)
    reply_processor = MagicMock(spec=ReplyProcessor)

    return {
        "state_store": state_store,
        "timeline_monitor": timeline_monitor,
        "reply_monitor": reply_monitor,
        "allowed_users_service": allowed_users_service,
        "reply_processor": reply_processor,
        "xp_calculator": XPCalculator(),
        "level_manager": level_manager,
        "ai_generator": ai_generator,
        "image_compositor": image_compositor,
        "profile_updater": profile_updater,
        "daily_reporter": daily_reporter,
        "x_api_client": x_api_client,
    }


# ============================================
# Property 1: グループオリジナル投稿のXP加算とカウント更新
# ============================================

class TestProperty1GroupOriginalXPAndCounts:
    """
    Feature: group-quote-removal-and-reply-feature
    Property 1: グループオリジナル投稿のXP加算とカウント更新

    For any グループアカウントのオリジナル投稿が検出されたとき、
    システムはXPを2.0加算し、group_post_countとdaily_group_countをインクリメントする。

    Validates: Requirements 1.1, 13.1, 13.2
    """

    @given(tweets=st.lists(original_tweet_strategy(), min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_group_original_xp_and_counts(self, tweets):
        # ツイートIDの重複を排除
        seen_ids = set()
        unique_tweets = []
        for t in tweets:
            if t.id not in seen_ids:
                seen_ids.add(t.id)
                unique_tweets.append(t)
        tweets = unique_tweets

        state = BotState()
        mocks = _make_mocks(state, group_original=tweets)

        result = _process_bot_logic(state=state, **mocks)

        n = len(tweets)
        assert result["xp_gained"] == n * 2.0
        assert state.group_post_count == n
        assert state.daily_group_count == n
        assert result["group_posts_detected"] == n


# ============================================
# Property 2: グループオリジナル投稿の引用ポスト停止
# ============================================

class TestProperty2GroupOriginalNoQuotePost:
    """
    Feature: group-quote-removal-and-reply-feature
    Property 2: グループオリジナル投稿の引用ポスト停止

    For any グループアカウントのオリジナル投稿が検出されたとき、
    システムは引用ポストを実行してはいけない。

    Validates: Requirements 1.2
    """

    @given(tweets=st.lists(original_tweet_strategy(), min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_group_original_no_quote_post(self, tweets):
        seen_ids = set()
        unique_tweets = []
        for t in tweets:
            if t.id not in seen_ids:
                seen_ids.add(t.id)
                unique_tweets.append(t)
        tweets = unique_tweets

        state = BotState()
        mocks = _make_mocks(state, group_original=tweets)

        result = _process_bot_logic(state=state, **mocks)

        assert result["quotes_posted"] == 0
        mocks["x_api_client"].post_tweet.assert_not_called()


# ============================================
# Property 3: グループオリジナル投稿のAI生成停止
# ============================================

class TestProperty3GroupOriginalNoAIGeneration:
    """
    Feature: group-quote-removal-and-reply-feature
    Property 3: グループオリジナル投稿のAI生成停止

    For any グループアカウントのオリジナル投稿が検出されたとき、
    システムはAI_Generatorを呼び出してはいけない。

    Validates: Requirements 1.3
    """

    @given(tweets=st.lists(original_tweet_strategy(), min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_group_original_no_ai_generation(self, tweets):
        seen_ids = set()
        unique_tweets = []
        for t in tweets:
            if t.id not in seen_ids:
                seen_ids.add(t.id)
                unique_tweets.append(t)
        tweets = unique_tweets

        state = BotState()
        mocks = _make_mocks(state, group_original=tweets)

        _process_bot_logic(state=state, **mocks)

        mocks["ai_generator"].generate_response.assert_not_called()


# ============================================
# Property 4: グループリツイートの既存動作維持
# ============================================

class TestProperty4GroupRetweetBehavior:
    """
    Feature: group-quote-removal-and-reply-feature
    Property 4: グループリツイートの既存動作維持

    For any グループアカウントのリツイート（リポスト）が検出されたとき、
    システムはXPを0.5加算し、引用ポストを実行してはいけない。

    Validates: Requirements 1.4
    """

    @given(tweets=st.lists(retweet_strategy(), min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_group_retweet_xp_and_no_quote(self, tweets):
        seen_ids = set()
        unique_tweets = []
        for t in tweets:
            if t.id not in seen_ids:
                seen_ids.add(t.id)
                unique_tweets.append(t)
        tweets = unique_tweets

        state = BotState()
        mocks = _make_mocks(state, group_retweets=tweets)

        result = _process_bot_logic(state=state, **mocks)

        n = len(tweets)
        assert result["xp_gained"] == n * 0.5
        assert state.repost_count == n
        assert result["quotes_posted"] == 0
        mocks["x_api_client"].post_tweet.assert_not_called()
        mocks["ai_generator"].generate_response.assert_not_called()


# ============================================
# Property 5: 推しオリジナル投稿の既存動作維持
# ============================================

class TestProperty5OshiOriginalBehavior:
    """
    Feature: group-quote-removal-and-reply-feature
    Property 5: 推しオリジナル投稿の既存動作維持

    For any 推しアカウントのオリジナル投稿が検出されたとき、
    システムはAI応答を生成し、引用ポストを実行し、XPを5.0加算する。

    Validates: Requirements 1.5
    """

    @given(tweets=st.lists(oshi_original_tweet_strategy(), min_size=1, max_size=5))
    @settings(max_examples=100, deadline=None)
    def test_oshi_original_ai_quote_and_xp(self, tweets):
        seen_ids = set()
        unique_tweets = []
        for t in tweets:
            if t.id not in seen_ids:
                seen_ids.add(t.id)
                unique_tweets.append(t)
        tweets = unique_tweets

        state = BotState()
        mocks = _make_mocks(state, oshi_original=tweets)

        result = _process_bot_logic(state=state, **mocks)

        n = len(tweets)
        # AI応答が生成されること
        assert mocks["ai_generator"].generate_response.call_count == n
        # 引用ポストが実行されること
        assert mocks["x_api_client"].post_tweet.call_count == n
        assert result["quotes_posted"] == n
        # XPが5.0加算されること
        assert result["xp_gained"] == n * 5.0
        assert state.oshi_post_count == n
        assert state.daily_oshi_count == n
