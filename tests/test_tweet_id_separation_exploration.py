"""
Bug Condition Exploration Test: 推しとグループのsince_id共有によるツイート読み飛ばし

Property 1: Fault Condition - 推しとグループのsince_id共有によるツイート読み飛ばし

推しとグループの両方にツイートがあり、かつIDに差がある場合（isBugCondition=true）に
スコープしたプロパティベーステスト。

修正後の期待動作:
- state.latest_oshi_tweet_id == max(oshi_tweets.id)
- state.latest_group_tweet_id == max(group_tweets.id)
- 推しのタイムライン取得に latest_oshi_tweet_id が使用される
- グループのタイムライン取得に latest_group_tweet_id が使用される
- ID更新が独立している（推しのIDでグループのIDが上書きされない、逆も同様）

**Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4**
"""
from unittest.mock import MagicMock, call

from hypothesis import given, settings, assume
from hypothesis import strategies as st

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


# --- Strategies ---

# ツイートIDストラテジー（正の整数、Twitter IDの現実的な範囲）
tweet_id_strategy = st.integers(min_value=1, max_value=10**18)

# 推しツイートリスト生成（1〜5件、全てオリジナル投稿）
oshi_tweets_strategy = st.lists(
    tweet_id_strategy,
    min_size=1,
    max_size=5,
).map(
    lambda ids: [
        Tweet(id=str(tid), text=f"推し投稿{i}", author_id="oshi_user")
        for i, tid in enumerate(ids)
    ]
)

# グループツイートリスト生成（1〜5件、全てオリジナル投稿）
group_tweets_strategy = st.lists(
    tweet_id_strategy,
    min_size=1,
    max_size=5,
).map(
    lambda ids: [
        Tweet(id=str(tid), text=f"グループ投稿{i}", author_id="group_user")
        for i, tid in enumerate(ids)
    ]
)


def _make_mocks(oshi_tweets, group_tweets):
    """テスト用のモックオブジェクトを生成"""
    state = BotState()

    state_store = MagicMock(spec=StateStore)
    state_store.reset_daily_counts.return_value = state
    # acquire_tweet_lock は成功（冪等性チェック通過）
    state_store.acquire_tweet_lock.return_value = True

    timeline_monitor = MagicMock(spec=TimelineMonitor)
    timeline_monitor.check_oshi_timeline.return_value = oshi_tweets
    timeline_monitor.check_group_timeline.return_value = group_tweets
    # filter_original_posts: 全てオリジナル投稿として返す
    timeline_monitor.filter_original_posts.side_effect = lambda t: t
    # filter_retweets: リツイートなし
    timeline_monitor.filter_retweets.side_effect = lambda t: []

    xp_calculator = XPCalculator()

    level_manager = MagicMock(spec=LevelManager)
    level_manager.check_level_up.return_value = (False, 1)

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

    return (
        state, state_store, timeline_monitor, xp_calculator,
        level_manager, ai_generator, image_compositor,
        profile_updater, daily_reporter, x_api_client,
        reply_monitor, allowed_users_service, reply_processor,
    )


@settings(max_examples=50)
@given(
    oshi_tweets=oshi_tweets_strategy,
    group_tweets=group_tweets_strategy,
)
def test_fault_condition_independent_id_update(oshi_tweets, group_tweets):
    """
    Property 1: Fault Condition - 推しとグループのsince_id共有によるツイート読み飛ばし

    推しとグループの両方にツイートがあり、かつ最大IDが異なる場合（isBugCondition=true）、
    修正後の _process_bot_logic は:
    - state.latest_oshi_tweet_id == max(oshi_tweets.id)
    - state.latest_group_tweet_id == max(group_tweets.id)
    であること。ID更新が独立していること。

    **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4**
    """
    # isBugCondition: 両方にツイートがあり、かつ最大IDが異なる
    oshi_max_id = max(int(t.id) for t in oshi_tweets)
    group_max_id = max(int(t.id) for t in group_tweets)
    assume(oshi_max_id != group_max_id)

    (
        state, state_store, timeline_monitor, xp_calculator,
        level_manager, ai_generator, image_compositor,
        profile_updater, daily_reporter, x_api_client,
        reply_monitor, allowed_users_service, reply_processor,
    ) = _make_mocks(oshi_tweets, group_tweets)

    _process_bot_logic(
        state=state,
        state_store=state_store,
        timeline_monitor=timeline_monitor,
        reply_monitor=reply_monitor,
        allowed_users_service=allowed_users_service,
        reply_processor=reply_processor,
        xp_calculator=xp_calculator,
        level_manager=level_manager,
        ai_generator=ai_generator,
        image_compositor=image_compositor,
        profile_updater=profile_updater,
        daily_reporter=daily_reporter,
        x_api_client=x_api_client,
    )

    # 期待動作: 推しとグループのIDが独立して更新される
    assert hasattr(state, "latest_oshi_tweet_id"), \
        "BotState に latest_oshi_tweet_id フィールドが存在しない（バグ: 単一の latest_tweet_id を共有）"
    assert hasattr(state, "latest_group_tweet_id"), \
        "BotState に latest_group_tweet_id フィールドが存在しない（バグ: 単一の latest_tweet_id を共有）"

    assert state.latest_oshi_tweet_id == str(oshi_max_id), \
        f"latest_oshi_tweet_id が推しの最大ID({oshi_max_id})と一致しない: {state.latest_oshi_tweet_id}"
    assert state.latest_group_tweet_id == str(group_max_id), \
        f"latest_group_tweet_id がグループの最大ID({group_max_id})と一致しない: {state.latest_group_tweet_id}"


@settings(max_examples=50)
@given(
    oshi_tweets=oshi_tweets_strategy,
    group_tweets=group_tweets_strategy,
)
def test_fault_condition_independent_since_id_usage(oshi_tweets, group_tweets):
    """
    Property 1: Fault Condition - タイムライン取得時のsince_id独立性

    推しとグループの両方にツイートがあり、かつ最大IDが異なる場合、
    推しのタイムライン取得に latest_oshi_tweet_id が、
    グループのタイムライン取得に latest_group_tweet_id が使用されること。

    **Validates: Requirements 2.1, 2.2**
    """
    oshi_max_id = max(int(t.id) for t in oshi_tweets)
    group_max_id = max(int(t.id) for t in group_tweets)
    assume(oshi_max_id != group_max_id)

    # 初期状態: 推しとグループで異なるsince_idを設定
    initial_oshi_id = "100"
    initial_group_id = "200"

    (
        state, state_store, timeline_monitor, xp_calculator,
        level_manager, ai_generator, image_compositor,
        profile_updater, daily_reporter, x_api_client,
        reply_monitor, allowed_users_service, reply_processor,
    ) = _make_mocks(oshi_tweets, group_tweets)

    # 初期状態を設定（修正後のフィールドが存在する前提）
    # 未修正コードでは latest_oshi_tweet_id / latest_group_tweet_id が存在しないため失敗する
    state.latest_oshi_tweet_id = initial_oshi_id
    state.latest_group_tweet_id = initial_group_id

    _process_bot_logic(
        state=state,
        state_store=state_store,
        timeline_monitor=timeline_monitor,
        reply_monitor=reply_monitor,
        allowed_users_service=allowed_users_service,
        reply_processor=reply_processor,
        xp_calculator=xp_calculator,
        level_manager=level_manager,
        ai_generator=ai_generator,
        image_compositor=image_compositor,
        profile_updater=profile_updater,
        daily_reporter=daily_reporter,
        x_api_client=x_api_client,
    )

    # 推しのタイムライン取得に latest_oshi_tweet_id が使用されたことを検証
    oshi_call = timeline_monitor.check_oshi_timeline.call_args
    assert oshi_call is not None, "check_oshi_timeline が呼ばれていない"
    oshi_since_id = oshi_call.kwargs.get("since_tweet_id") or oshi_call[0][0] if oshi_call[0] else oshi_call.kwargs.get("since_tweet_id")

    # グループのタイムライン取得に latest_group_tweet_id が使用されたことを検証
    group_call = timeline_monitor.check_group_timeline.call_args
    assert group_call is not None, "check_group_timeline が呼ばれていない"
    group_since_id = group_call.kwargs.get("since_tweet_id") or group_call[0][0] if group_call[0] else group_call.kwargs.get("since_tweet_id")

    # 未修正コードでは state.latest_tweet_id（共通）が両方に渡されるため、
    # oshi_since_id != initial_oshi_id または group_since_id != initial_group_id となる
    assert oshi_since_id == initial_oshi_id, \
        f"推しのsince_idが latest_oshi_tweet_id({initial_oshi_id})ではなく {oshi_since_id} が使用された（バグ: 共通のlatest_tweet_idを使用）"
    assert group_since_id == initial_group_id, \
        f"グループのsince_idが latest_group_tweet_id({initial_group_id})ではなく {group_since_id} が使用された（バグ: 共通のlatest_tweet_idを使用）"
