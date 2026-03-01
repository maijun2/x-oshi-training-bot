"""
リプライ投稿のLambda Handler統合プロパティベーステスト

Feature: group-quote-removal-and-reply-feature
Property 11: リプライ投稿とレコード作成
Property 12: リプライ投稿時のXP非加算
"""
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import MagicMock

from src.hokuhoku_imomaru_bot.lambda_handler import _process_bot_logic
from src.hokuhoku_imomaru_bot.models import BotState
from src.hokuhoku_imomaru_bot.models.reply import Reply
from src.hokuhoku_imomaru_bot.services import (
    StateStore,
    TimelineMonitor,
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

def reply_id_strategy():
    """有効なリプライIDを生成するストラテジー"""
    return st.integers(min_value=1, max_value=10**18).map(str)


def reply_strategy():
    """Replyオブジェクトを生成するストラテジー"""
    return st.builds(
        Reply,
        id=reply_id_strategy(),
        text=st.text(min_size=1, max_size=140),
        author_id=st.just("allowed_user_001"),
        author_username=st.just("test_user"),
        created_at=st.just("2026-02-28T10:00:00Z"),
        in_reply_to_tweet_id=st.just("bot_tweet_001"),
        in_reply_to_user_id=st.just("bot_user_id"),
    )


def _make_mocks(replies=None, all_allowed=True, process_success=True):
    """テスト用のモックオブジェクトを生成するヘルパー"""
    replies = replies or []

    state = BotState()
    state_store = MagicMock(spec=StateStore)
    state_store.reset_daily_counts.return_value = state

    timeline_monitor = MagicMock(spec=TimelineMonitor)
    timeline_monitor.check_oshi_timeline.return_value = []
    timeline_monitor.check_group_timeline.return_value = []
    timeline_monitor.filter_original_posts.return_value = []
    timeline_monitor.filter_retweets.return_value = []

    level_manager = MagicMock(spec=LevelManager)
    level_manager.check_level_up.return_value = (False, state.current_level)

    ai_generator = MagicMock(spec=AIGenerator)
    image_compositor = MagicMock(spec=ImageCompositor)
    profile_updater = MagicMock(spec=ProfileUpdater)

    daily_reporter = MagicMock(spec=DailyReporter)
    daily_reporter.should_post_daily_report.return_value = False

    x_api_client = MagicMock()

    reply_monitor = MagicMock(spec=ReplyMonitor)
    reply_monitor.detect_replies.return_value = replies

    allowed_users_service = MagicMock(spec=AllowedUsersService)
    allowed_users_service.is_user_allowed.return_value = all_allowed

    reply_processor = MagicMock(spec=ReplyProcessor)
    reply_processor.process_reply.return_value = process_success

    return {
        "state": state,
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
# Property 11: リプライ投稿とレコード作成
# ============================================

@settings(max_examples=100)
@given(replies=st.lists(reply_strategy(), min_size=1, max_size=10))
def test_property_11_reply_posting_and_record_creation(replies):
    """
    Property 11: リプライ投稿とレコード作成

    *For any* 許可ユーザーからのリプライリストに対して、
    reply_processor.process_reply が各リプライに対して呼び出され、
    処理成功数が replies_processed に反映されること。

    **Validates: Requirements 7.1, 7.3, 7.4**
    """
    mocks = _make_mocks(replies=replies, all_allowed=True, process_success=True)

    result = _process_bot_logic(
        state=mocks["state"],
        state_store=mocks["state_store"],
        timeline_monitor=mocks["timeline_monitor"],
        reply_monitor=mocks["reply_monitor"],
        allowed_users_service=mocks["allowed_users_service"],
        reply_processor=mocks["reply_processor"],
        xp_calculator=mocks["xp_calculator"],
        level_manager=mocks["level_manager"],
        ai_generator=mocks["ai_generator"],
        image_compositor=mocks["image_compositor"],
        profile_updater=mocks["profile_updater"],
        daily_reporter=mocks["daily_reporter"],
        x_api_client=mocks["x_api_client"],
    )

    n = len(replies)

    # 全リプライに対してprocess_replyが呼ばれること
    assert mocks["reply_processor"].process_reply.call_count == n, \
        f"process_reply が {n} 回呼ばれるべきだが {mocks['reply_processor'].process_reply.call_count} 回"

    # 処理成功数がreplies_processedに反映されること
    assert result["replies_processed"] == n, \
        f"replies_processed が {n} であるべきだが {result['replies_processed']}"

    # 各リプライに対してai_generatorとx_api_clientが渡されること
    for call in mocks["reply_processor"].process_reply.call_args_list:
        assert call.kwargs["ai_generator"] == mocks["ai_generator"]
        assert call.kwargs["x_api_client"] == mocks["x_api_client"]


@settings(max_examples=100)
@given(replies=st.lists(reply_strategy(), min_size=1, max_size=10))
def test_property_11_failed_replies_not_counted(replies):
    """
    Property 11 補足: process_replyがFalseを返した場合、replies_processedに含まれないこと。

    **Validates: Requirements 7.1, 7.3, 7.4**
    """
    mocks = _make_mocks(replies=replies, all_allowed=True, process_success=False)

    result = _process_bot_logic(
        state=mocks["state"],
        state_store=mocks["state_store"],
        timeline_monitor=mocks["timeline_monitor"],
        reply_monitor=mocks["reply_monitor"],
        allowed_users_service=mocks["allowed_users_service"],
        reply_processor=mocks["reply_processor"],
        xp_calculator=mocks["xp_calculator"],
        level_manager=mocks["level_manager"],
        ai_generator=mocks["ai_generator"],
        image_compositor=mocks["image_compositor"],
        profile_updater=mocks["profile_updater"],
        daily_reporter=mocks["daily_reporter"],
        x_api_client=mocks["x_api_client"],
    )

    # process_replyは呼ばれるが、全て失敗なのでreplies_processedは0
    assert mocks["reply_processor"].process_reply.call_count == len(replies)
    assert result["replies_processed"] == 0


# ============================================
# Property 12: リプライ投稿時のXP非加算
# ============================================

@settings(max_examples=100)
@given(
    replies=st.lists(reply_strategy(), min_size=0, max_size=10),
    initial_xp=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False),
)
def test_property_12_no_xp_on_reply_processing(replies, initial_xp):
    """
    Property 12: リプライ投稿時のXP非加算

    *For any* リプライ処理時に、XPが加算されないこと。
    リプライ処理前後でcumulative_xp, daily_xpが変化しないこと。

    **Validates: Requirements 7.5**
    """
    mocks = _make_mocks(replies=replies, all_allowed=True, process_success=True)
    mocks["state"].cumulative_xp = initial_xp
    mocks["state"].daily_xp = initial_xp

    result = _process_bot_logic(
        state=mocks["state"],
        state_store=mocks["state_store"],
        timeline_monitor=mocks["timeline_monitor"],
        reply_monitor=mocks["reply_monitor"],
        allowed_users_service=mocks["allowed_users_service"],
        reply_processor=mocks["reply_processor"],
        xp_calculator=mocks["xp_calculator"],
        level_manager=mocks["level_manager"],
        ai_generator=mocks["ai_generator"],
        image_compositor=mocks["image_compositor"],
        profile_updater=mocks["profile_updater"],
        daily_reporter=mocks["daily_reporter"],
        x_api_client=mocks["x_api_client"],
    )

    # XPが変化しないこと
    assert mocks["state"].cumulative_xp == initial_xp, \
        f"cumulative_xp が変化した: {initial_xp} → {mocks['state'].cumulative_xp}"
    assert mocks["state"].daily_xp == initial_xp, \
        f"daily_xp が変化した: {initial_xp} → {mocks['state'].daily_xp}"
    assert result["xp_gained"] == 0.0, \
        f"xp_gained が 0 であるべきだが {result['xp_gained']}"
