"""
Preservation Property Tests: 非バグ条件での動作維持・後方互換性・翻訳投稿

Property 2: Preservation - 非バグ条件での動作維持・後方互換性・翻訳投稿

修正前のコードで非バグ条件（推しのみ投稿、グループのみ投稿、投稿なし）での
動作を観察し、修正後もこれらの動作が保持されることを検証する。

**Validates: Requirements 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
"""
from copy import deepcopy
from unittest.mock import MagicMock

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
    DraftNotifier,
)


# --- Strategies ---

tweet_id_strategy = st.integers(min_value=1, max_value=10**18)

# 推しツイートリスト生成（1〜5件）
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

# グループツイートリスト生成（1〜5件）
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


def _make_mocks(oshi_tweets=None, group_tweets=None):
    """テスト用のモックオブジェクトを生成"""
    state = BotState()

    state_store = MagicMock(spec=StateStore)
    state_store.reset_daily_counts.return_value = state
    state_store.acquire_tweet_lock.return_value = True

    timeline_monitor = MagicMock(spec=TimelineMonitor)
    timeline_monitor.check_oshi_timeline.return_value = oshi_tweets or []
    timeline_monitor.check_group_timeline.return_value = group_tweets or []
    timeline_monitor.filter_original_posts.side_effect = lambda t: t
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

    draft_notifier = MagicMock(spec=DraftNotifier)
    draft_notifier.send_draft_email.return_value = True

    reply_monitor = MagicMock(spec=ReplyMonitor)
    reply_monitor.detect_replies.return_value = []

    allowed_users_service = MagicMock(spec=AllowedUsersService)
    reply_processor = MagicMock(spec=ReplyProcessor)

    return (
        state, state_store, timeline_monitor, xp_calculator,
        level_manager, ai_generator, image_compositor,
        profile_updater, daily_reporter, x_api_client,
        reply_monitor, allowed_users_service, reply_processor,
        draft_notifier,
    )


# =============================================================================
# Property: 推しのみ投稿時のXP・カウント・引用ポスト結果が修正前後で同一
# =============================================================================

@settings(max_examples=50)
@given(oshi_tweets=oshi_tweets_strategy)
def test_preservation_oshi_only_xp_and_counts(oshi_tweets):
    """
    推しのみ投稿時（グループなし）のXP加算・カウント更新・引用ポスト動作が正常であること。

    非バグ条件: グループの投稿がないため、since_id共有の問題は発生しない。
    推しの投稿数に応じたXP（5.0 * 投稿数）が加算され、引用ポストが投稿されること。

    **Validates: Requirements 3.1**
    """
    (
        state, state_store, timeline_monitor, xp_calculator,
        level_manager, ai_generator, image_compositor,
        profile_updater, daily_reporter, x_api_client,
        reply_monitor, allowed_users_service, reply_processor,
        draft_notifier,
    ) = _make_mocks(oshi_tweets=oshi_tweets, group_tweets=[])

    result = _process_bot_logic(
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
        draft_notifier=draft_notifier,
    )

    n = len(oshi_tweets)
    expected_xp = 5.0 * n

    # XP加算が正しいこと
    assert result["xp_gained"] == expected_xp, \
        f"推し{n}件でXP={result['xp_gained']}（期待: {expected_xp}）"
    assert state.cumulative_xp == expected_xp

    # カウント更新が正しいこと
    assert result["oshi_posts_detected"] == n
    assert state.oshi_post_count == n
    assert state.daily_oshi_count == n

    # グループは検出されないこと
    assert result["group_posts_detected"] == 0
    assert state.group_post_count == 0

    # 引用ポストが投稿されること
    assert result["quotes_posted"] == n

    # latest_oshi_tweet_id が推しの最大IDで更新されること
    expected_max_id = str(max(int(t.id) for t in oshi_tweets))
    assert state.latest_oshi_tweet_id == expected_max_id


# =============================================================================
# Property: グループのみ投稿時のXP・カウント・引用ポスト結果が修正前後で同一
# =============================================================================

@settings(max_examples=50)
@given(group_tweets=group_tweets_strategy)
def test_preservation_group_only_xp_and_counts(group_tweets):
    """
    グループのみ投稿時（推しなし）のXP加算・カウント更新・引用ポスト動作が正常であること。

    非バグ条件: 推しの投稿がないため、since_id共有の問題は発生しない。
    グループの投稿数に応じたXP（2.0 * 投稿数）が加算され、引用ポストが投稿されること。

    **Validates: Requirements 3.2**
    """
    (
        state, state_store, timeline_monitor, xp_calculator,
        level_manager, ai_generator, image_compositor,
        profile_updater, daily_reporter, x_api_client,
        reply_monitor, allowed_users_service, reply_processor,
        draft_notifier,
    ) = _make_mocks(oshi_tweets=[], group_tweets=group_tweets)

    result = _process_bot_logic(
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
        draft_notifier=draft_notifier,
    )

    n = len(group_tweets)
    expected_xp = 2.0 * n

    # XP加算が正しいこと
    assert result["xp_gained"] == expected_xp, \
        f"グループ{n}件でXP={result['xp_gained']}（期待: {expected_xp}）"
    assert state.cumulative_xp == expected_xp

    # カウント更新が正しいこと
    assert result["group_posts_detected"] == n
    assert state.group_post_count == n
    assert state.daily_group_count == n

    # 推しは検出されないこと
    assert result["oshi_posts_detected"] == 0
    assert state.oshi_post_count == 0

    # グループオリジナル投稿は引用ポストしない（コスト削減対策）
    assert result["quotes_posted"] == 0

    # latest_group_tweet_id がグループの最大IDで更新されること
    expected_max_id = str(max(int(t.id) for t in group_tweets))
    assert state.latest_group_tweet_id == expected_max_id


# =============================================================================
# Property: 投稿なし時に状態が変更されない
# =============================================================================

@settings(max_examples=50)
@given(
    initial_xp=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False),
    initial_level=st.integers(min_value=1, max_value=100),
    initial_tweet_id=st.one_of(st.none(), tweet_id_strategy.map(str)),
)
def test_preservation_no_posts_state_unchanged(initial_xp, initial_level, initial_tweet_id):
    """
    推しもグループも投稿がない場合、状態が変更されずに正常終了すること。

    非バグ条件: 投稿がないため、since_id共有の問題は発生しない。
    cumulative_xp, current_level, latest_oshi_tweet_id, latest_group_tweet_id, カウントが全て変更されないこと。

    **Validates: Requirements 3.3**
    """
    (
        state, state_store, timeline_monitor, xp_calculator,
        level_manager, ai_generator, image_compositor,
        profile_updater, daily_reporter, x_api_client,
        reply_monitor, allowed_users_service, reply_processor,
        draft_notifier,
    ) = _make_mocks(oshi_tweets=[], group_tweets=[])

    # 初期状態を設定
    state.cumulative_xp = initial_xp
    state.current_level = initial_level
    state.latest_tweet_id = initial_tweet_id
    state.latest_oshi_tweet_id = initial_tweet_id
    state.latest_group_tweet_id = initial_tweet_id
    level_manager.check_level_up.return_value = (False, initial_level)

    # 初期状態を保存
    saved_xp = state.cumulative_xp
    saved_level = state.current_level
    saved_oshi_tweet_id = state.latest_oshi_tweet_id
    saved_group_tweet_id = state.latest_group_tweet_id
    saved_oshi_count = state.oshi_post_count
    saved_group_count = state.group_post_count

    result = _process_bot_logic(
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
        draft_notifier=draft_notifier,
    )

    # 状態が変更されていないこと
    assert state.cumulative_xp == saved_xp, \
        f"cumulative_xp が変更された: {saved_xp} → {state.cumulative_xp}"
    assert state.current_level == saved_level
    assert state.latest_oshi_tweet_id == saved_oshi_tweet_id, \
        f"latest_oshi_tweet_id が変更された: {saved_oshi_tweet_id} → {state.latest_oshi_tweet_id}"
    assert state.latest_group_tweet_id == saved_group_tweet_id, \
        f"latest_group_tweet_id が変更された: {saved_group_tweet_id} → {state.latest_group_tweet_id}"
    assert state.oshi_post_count == saved_oshi_count
    assert state.group_post_count == saved_group_count

    # 結果が0であること
    assert result["xp_gained"] == 0.0
    assert result["oshi_posts_detected"] == 0
    assert result["group_posts_detected"] == 0
    assert result["quotes_posted"] == 0


# =============================================================================
# Property: core_time モードでグループタイムラインがスキップされる
# =============================================================================

@settings(max_examples=50)
@given(oshi_tweets=st.one_of(
    st.just([]),
    oshi_tweets_strategy,
))
def test_preservation_core_time_skips_group_timeline(oshi_tweets):
    """
    core_time モードでグループタイムラインのチェックがスキップされ、
    推しのタイムラインのみがチェックされること。

    **Validates: Requirements 3.5**
    """
    (
        state, state_store, timeline_monitor, xp_calculator,
        level_manager, ai_generator, image_compositor,
        profile_updater, daily_reporter, x_api_client,
        reply_monitor, allowed_users_service, reply_processor,
        draft_notifier,
    ) = _make_mocks(oshi_tweets=oshi_tweets, group_tweets=[])

    # core_time モード用の設定
    daily_reporter.should_post_morning_content.return_value = False

    result = _process_bot_logic(
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
        draft_notifier=draft_notifier,
        execution_mode="core_time",
    )

    # グループタイムラインはスキップされること
    timeline_monitor.check_group_timeline.assert_not_called()

    # 推しタイムラインはチェックされること
    timeline_monitor.check_oshi_timeline.assert_called_once()

    # execution_mode が正しいこと
    assert result["execution_mode"] == "core_time"


# =============================================================================
# Property: from_dict() のフォールバック
# （latest_tweet_id → latest_oshi_tweet_id / latest_group_tweet_id）
# =============================================================================

@settings(max_examples=50)
@given(
    latest_tweet_id=st.one_of(st.none(), tweet_id_strategy.map(str)),
    cumulative_xp=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False),
    current_level=st.integers(min_value=1, max_value=100),
)
def test_preservation_from_dict_fallback(latest_tweet_id, cumulative_xp, current_level):
    """
    from_dict() で latest_oshi_tweet_id / latest_group_tweet_id が存在しない場合、
    latest_tweet_id の値がフォールバックとして使用されること。

    現在の未修正コードでは latest_oshi_tweet_id / latest_group_tweet_id フィールドが
    存在しないため、from_dict() は latest_tweet_id のみを読み込む。
    修正後は新フィールドが None の場合に latest_tweet_id をフォールバックとして使用する。

    このテストは修正前後で from_dict() の基本動作（latest_tweet_id の読み込み）が
    保持されることを検証する。

    **Validates: Requirements 2.5**
    """
    # 旧形式のDynamoDBデータ（新フィールドなし）
    data = {
        "latest_tweet_id": latest_tweet_id,
        "cumulative_xp": cumulative_xp,
        "current_level": current_level,
    }

    state = BotState.from_dict(data)

    # latest_tweet_id が正しく読み込まれること
    assert state.latest_tweet_id == latest_tweet_id
    assert state.cumulative_xp == cumulative_xp
    assert state.current_level == current_level

    # to_dict() → from_dict() のラウンドトリップで latest_tweet_id が保持されること
    restored = BotState.from_dict(state.to_dict())
    assert restored.latest_tweet_id == latest_tweet_id


# =============================================================================
# Property: 翻訳投稿で正しいIDが渡される
# =============================================================================

@settings(max_examples=50)
@given(
    latest_oshi_tweet_id=st.one_of(st.none(), tweet_id_strategy.map(str)),
)
def test_preservation_translation_receives_correct_id(latest_oshi_tweet_id):
    """
    翻訳投稿で latest_oshi_tweet_id が post_translation に正しく渡されること。

    core_time モードで翻訳投稿が実行される際、state.latest_oshi_tweet_id（または "0"）が
    post_translation の latest_tweet_id 引数として渡されること。

    **Validates: Requirements 3.6**
    """
    (
        state, state_store, timeline_monitor, xp_calculator,
        level_manager, ai_generator, image_compositor,
        profile_updater, daily_reporter, x_api_client,
        reply_monitor, allowed_users_service, reply_processor,
        draft_notifier,
    ) = _make_mocks(oshi_tweets=[], group_tweets=[])

    state.latest_oshi_tweet_id = latest_oshi_tweet_id

    # core_time モード + 翻訳投稿が有効
    daily_reporter.should_post_morning_content.return_value = True
    daily_reporter.post_youtube_search.return_value = False
    daily_reporter.should_post_translation.return_value = True
    daily_reporter.post_translation.return_value = True

    result = _process_bot_logic(
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
        draft_notifier=draft_notifier,
        execution_mode="core_time",
    )

    # post_translation が呼ばれたこと
    daily_reporter.post_translation.assert_called_once()

    # 渡された latest_tweet_id を検証
    call_kwargs = daily_reporter.post_translation.call_args.kwargs
    expected_id = latest_oshi_tweet_id or "0"
    assert call_kwargs["latest_tweet_id"] == expected_id, \
        f"post_translation に渡された latest_tweet_id={call_kwargs['latest_tweet_id']}（期待: {expected_id}）"
