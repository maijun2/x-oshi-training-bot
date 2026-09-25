"""
独り言（自律投稿、3b-1 (i)）の Lambda 側のテスト

- 発火条件（react 0 件・本日未実施・次の枠が今日・キャップ・残り時間・候補の有無）
- 冪等ロック・頭脳の skip／失敗・Buffer 投入・履歴・メール・dry run
- _process_bot_logic からの呼び出し（21:00 回だけ、例外でも状態を保存）
- DraftNotifier.send_autonomous_email
"""
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.hokuhoku_imomaru_bot.lambda_handler import (
    AUTONOMOUS_MIN_REMAINING_MS,
    _autonomous_post,
    _autonomous_post_safe,
    _process_bot_logic,
)
from src.hokuhoku_imomaru_bot.models import BotState
from src.hokuhoku_imomaru_bot.services import (
    AIGenerator,
    BufferScheduler,
    DailyReporter,
    DraftNotifier,
    ImageCompositor,
    LevelManager,
    ProfileUpdater,
    ScheduledPost,
    StateStore,
    TimelineMonitor,
    TweetAlreadyProcessedError,
    XPCalculator,
)
from src.hokuhoku_imomaru_bot.services.ai_generator import BRAIN_FAILED_REASON, Reaction
from src.hokuhoku_imomaru_bot.services.autonomous_selector import (
    AutonomousSelection,
    AutonomousSelector,
    MemoryCandidate,
)
from src.hokuhoku_imomaru_bot.services.daily_reporter import JST
from src.hokuhoku_imomaru_bot.services.post_history_store import HistoryEntry, PostHistoryStore
from tests.test_lambda_handler import _make_reply_mocks

NOW = datetime(2026, 9, 26, 21, 1, tzinfo=JST)
SLOT_22 = datetime(2026, 9, 26, 22, 0, tzinfo=JST)
DUE_AT = datetime(2026, 9, 26, 22, 4, tzinfo=JST)
BIRTHDAY = MemoryCandidate("mem-birthday", "甘木ジュリは2026年9月28日に生誕祭を開催予定", NOW - timedelta(days=1))
PREP = MemoryCandidate("mem-prep", "甘木ジュリは9月28日の生誕祭の準備をしている", NOW - timedelta(days=8))
SELECTION = AutonomousSelection(
    kind="A",
    candidates=[BIRTHDAY, PREP],
    keys={"mem-birthday": "A:2026-09-28:2", "mem-prep": "A:2026-09-28:2"},
    days_left=2,
    event_date=date(2026, 9, 28),
)
POST = Reaction(action="post", text="生誕祭まであと2日ｲﾓ🍠", emotion_key="joy", reason="r", sources=["mem-birthday"])


def _deps(selection=SELECTION, reaction=POST, scheduled=True, history=()):
    state_store = MagicMock(spec=StateStore)
    ai_generator = MagicMock(spec=AIGenerator)
    ai_generator.generate_autonomous.return_value = reaction
    draft_notifier = MagicMock(spec=DraftNotifier)
    buffer_scheduler = MagicMock(spec=BufferScheduler)
    buffer_scheduler.next_slot_at.return_value = SLOT_22
    buffer_scheduler.can_schedule.return_value = True
    buffer_scheduler.run_cap = 2
    buffer_scheduler.schedule_autonomous.return_value = (
        ScheduledPost(post_id="p1", due_at=DUE_AT, image_attached=False) if scheduled else None
    )
    selector = MagicMock(spec=AutonomousSelector)
    selector.select.return_value = selection
    history_store = MagicMock(spec=PostHistoryStore)
    history_store.load_recent.return_value = list(history)
    history_store.used_keys.side_effect = PostHistoryStore.used_keys
    return dict(
        state_store=state_store,
        ai_generator=ai_generator,
        draft_notifier=draft_notifier,
        buffer_scheduler=buffer_scheduler,
        selector=selector,
        history_store=history_store,
    )


def _run(state=None, react_calls=0, **kwargs):
    deps = kwargs.pop("deps", None) or _deps()
    state = state or BotState()
    status = _autonomous_post(state=state, react_calls=react_calls, now=NOW, **deps, **kwargs)
    return status, state, deps


class TestConditions:
    def test_reacted_run_does_nothing(self):
        status, _, deps = _run(react_calls=1)
        assert status == "reacted"
        deps["selector"].select.assert_not_called()

    def test_already_done_today(self):
        status, _, deps = _run(state=BotState(last_autonomous_date="2026-09-26"))
        assert status == "already_done"
        deps["selector"].select.assert_not_called()

    def test_next_slot_tomorrow(self):
        deps = _deps()
        deps["buffer_scheduler"].next_slot_at.return_value = datetime(2026, 9, 27, 2, 0, tzinfo=JST)
        status, _, _ = _run(deps=deps)
        assert status == "next_slot_tomorrow"

    def test_cap(self):
        deps = _deps()
        deps["buffer_scheduler"].can_schedule.return_value = False
        assert _run(deps=deps)[0] == "cap"

    def test_low_time(self):
        status, _, deps = _run(remaining_time_ms=lambda: AUTONOMOUS_MIN_REMAINING_MS - 1)
        assert status == "low_time"
        deps["selector"].select.assert_not_called()

    def test_not_configured(self):
        deps = _deps()
        deps["selector"] = None
        assert _run(deps=deps)[0] == "not_configured"

    def test_no_candidates_calls_neither_brain_nor_email(self):
        status, state, deps = _run(deps=_deps(selection=None))
        assert status == "no_candidates"
        deps["state_store"].acquire_tweet_lock.assert_not_called()
        deps["ai_generator"].generate_autonomous.assert_not_called()
        deps["draft_notifier"].send_autonomous_email.assert_not_called()
        assert state.last_autonomous_date is None

    def test_history_keys_are_passed_to_selector(self):
        history = [HistoryEntry(posted_date="2026-09-25", kind="A", text="前の独り言", dedupe_keys=["A:2026-09-28:3"])]
        _, _, deps = _run(deps=_deps(history=history))
        assert deps["selector"].select.call_args.args[1] == {"A:2026-09-28:3"}
        assert deps["ai_generator"].generate_autonomous.call_args.kwargs["recent_texts"] == ["前の独り言"]


class TestPost:
    def test_scheduled(self):
        status, state, deps = _run()

        assert status == DraftNotifier.BUFFER_STATUS_SCHEDULED
        deps["state_store"].acquire_tweet_lock.assert_called_once_with("autonomous-2026-09-26", "autonomous")
        gen_kwargs = deps["ai_generator"].generate_autonomous.call_args.kwargs
        assert gen_kwargs["kind"] == "A"
        assert gen_kwargs["days_left"] == 2
        assert gen_kwargs["publish_at"] == SLOT_22
        assert [c["id"] for c in gen_kwargs["candidates"]] == ["mem-birthday", "mem-prep"]
        deps["buffer_scheduler"].schedule_autonomous.assert_called_once_with(state, POST.text, "joy")
        assert state.last_autonomous_date == "2026-09-26"

        entry = deps["history_store"].record.call_args.args[0]
        assert entry.posted_date == "2026-09-26"
        assert entry.record_ids == ["mem-birthday"]
        assert entry.dedupe_keys == ["A:2026-09-28:2"]
        assert entry.buffer_post_id == "p1"

        email = deps["draft_notifier"].send_autonomous_email.call_args.kwargs
        assert email["buffer_status"] == DraftNotifier.BUFFER_STATUS_SCHEDULED
        assert email["buffer_due_at"] == DUE_AT
        assert email["sources"] == [("mem-birthday", BIRTHDAY.text)]
        assert "あと 2 日" in email["kind_label"]

    def test_locked_does_not_call_brain(self):
        deps = _deps()
        deps["state_store"].acquire_tweet_lock.side_effect = TweetAlreadyProcessedError("dup")
        status, _, _ = _run(deps=deps)
        assert status == "locked"
        deps["ai_generator"].generate_autonomous.assert_not_called()

    def test_brain_skip_sends_email_only(self):
        skip = Reaction(action="skip", text="", emotion_key=None, reason="記憶が古い")
        status, state, deps = _run(deps=_deps(reaction=skip))

        assert status == "skipped"
        deps["buffer_scheduler"].schedule_autonomous.assert_not_called()
        deps["history_store"].record.assert_not_called()
        email = deps["draft_notifier"].send_autonomous_email.call_args.kwargs
        assert email["buffer_status"] == DraftNotifier.BUFFER_STATUS_SKIPPED
        assert email["reason"] == "記憶が古い"
        assert len(email["sources"]) == 2  # sources なし → 渡した候補を全部載せる
        assert state.last_autonomous_date == "2026-09-26"

    def test_brain_failure_sends_nothing(self):
        failed = Reaction(action="skip", text="", emotion_key=None, reason=BRAIN_FAILED_REASON, source="error")
        status, state, deps = _run(deps=_deps(reaction=failed))
        assert status == "brain_failed"
        deps["draft_notifier"].send_autonomous_email.assert_not_called()
        deps["buffer_scheduler"].schedule_autonomous.assert_not_called()

    def test_cap_at_enqueue_emails_without_history(self):
        status, state, deps = _run(deps=_deps(scheduled=False))
        assert status == DraftNotifier.BUFFER_STATUS_CAP
        deps["history_store"].record.assert_not_called()
        assert state.last_autonomous_date == "2026-09-26"

    def test_buffer_failure_is_reported(self):
        deps = _deps()
        deps["buffer_scheduler"].schedule_autonomous.side_effect = RuntimeError("buffer down")
        status, _, _ = _run(deps=deps)
        assert status == DraftNotifier.BUFFER_STATUS_FAILED
        deps["history_store"].record.assert_not_called()
        assert deps["draft_notifier"].send_autonomous_email.call_args.kwargs["buffer_status"] == "failed"

    def test_history_failure_does_not_stop_email(self):
        deps = _deps()
        deps["history_store"].record.side_effect = RuntimeError("ddb")
        status, _, _ = _run(deps=deps)
        assert status == DraftNotifier.BUFFER_STATUS_SCHEDULED
        deps["draft_notifier"].send_autonomous_email.assert_called_once()

    def test_dry_run_touches_no_state(self):
        status, state, deps = _run(dry_run=True)
        assert status == "dry_run"
        deps["state_store"].acquire_tweet_lock.assert_not_called()
        deps["buffer_scheduler"].schedule_autonomous.assert_not_called()
        deps["history_store"].record.assert_not_called()
        assert state.last_autonomous_date is None
        assert "dry run" in deps["draft_notifier"].send_autonomous_email.call_args.kwargs["kind_label"]

    def test_safe_wrapper_swallows_errors(self):
        deps = _deps()
        deps["selector"].select.side_effect = RuntimeError("AccessDenied")
        status = _autonomous_post_safe(state=BotState(), react_calls=0, now=NOW, **deps)
        assert status == "error"


def _process(autonomous_allowed, oshi_tweets=(), execution_mode="core_time", selector=None):
    from src.hokuhoku_imomaru_bot.services import Tweet

    state = BotState(last_autonomous_date="2026-09-26")  # 発火条件の手前で止める（ここでは配線だけ見る）
    state_store = MagicMock(spec=StateStore)
    state_store.reset_daily_counts.return_value = state
    timeline_monitor = MagicMock(spec=TimelineMonitor)
    timeline_monitor.check_oshi_timeline.return_value = [Tweet(id=t, text="推し投稿", author_id="oshi") for t in oshi_tweets]
    timeline_monitor.check_group_timeline.return_value = []
    timeline_monitor.filter_original_posts.side_effect = lambda t: t
    timeline_monitor.filter_retweets.return_value = []
    level_manager = MagicMock(spec=LevelManager)
    level_manager.check_level_up.return_value = (False, 1)
    daily_reporter = MagicMock(spec=DailyReporter)
    daily_reporter.should_post_daily_report.return_value = False
    ai_generator = MagicMock(spec=AIGenerator)
    ai_generator.generate_reaction.return_value = Reaction(action="skip", text="", emotion_key=None)
    reply_monitor, allowed_users_service, reply_processor = _make_reply_mocks()
    x_api_client = MagicMock()
    x_api_client.get_my_tweets_with_metrics.return_value = []
    result = _process_bot_logic(
        state=state,
        state_store=state_store,
        timeline_monitor=timeline_monitor,
        reply_monitor=reply_monitor,
        allowed_users_service=allowed_users_service,
        reply_processor=reply_processor,
        xp_calculator=XPCalculator(),
        level_manager=level_manager,
        ai_generator=ai_generator,
        image_compositor=MagicMock(spec=ImageCompositor),
        profile_updater=MagicMock(spec=ProfileUpdater),
        daily_reporter=daily_reporter,
        x_api_client=x_api_client,
        draft_notifier=MagicMock(spec=DraftNotifier),
        buffer_scheduler=MagicMock(spec=BufferScheduler),
        execution_mode=execution_mode,
        autonomous_allowed=autonomous_allowed,
        autonomous_selector=selector or MagicMock(spec=AutonomousSelector),
        post_history_store=MagicMock(spec=PostHistoryStore),
    )
    return result, state_store


class TestProcessBotLogicWiring:
    def test_night_run_without_react_tries_autonomous(self):
        result, state_store = _process(autonomous_allowed=True)
        assert result["react_calls"] == 0
        assert result["autonomous_status"] == "already_done"
        state_store.save_state.assert_called_once()

    def test_react_calls_are_counted(self):
        result, _ = _process(autonomous_allowed=True, oshi_tweets=("111", "112"))
        assert result["react_calls"] == 2
        assert result["autonomous_status"] == "reacted"

    @pytest.mark.parametrize("allowed, mode", [(False, "core_time"), (True, "daily_report")])
    def test_other_runs_skip_autonomous(self, allowed, mode):
        result, _ = _process(autonomous_allowed=allowed, execution_mode=mode)
        assert "autonomous_status" not in result


class TestSendAutonomousEmail:
    def _send(self, **kwargs):
        ses_client = MagicMock()
        notifier = DraftNotifier(ses_client=ses_client, from_email="from@example.com", to_email="to@example.com")
        params = dict(
            kind_label="A. 未来イベント（09/28 まであと 2 日）",
            draft_text="生誕祭まであと2日ｲﾓ🍠\n\n#さつまいもの民 #びっくえんじぇる",
            reason="生誕祭が近い",
            sources=[("mem-birthday", "甘木ジュリは2026年9月28日に生誕祭<予定>")],
        )
        params.update(kwargs)
        assert notifier.send_autonomous_email(**params) is True
        message = ses_client.send_email.call_args.kwargs["Message"]
        return message["Subject"]["Data"], message["Body"]["Html"]["Data"], message["Body"]["Text"]["Data"]

    def test_scheduled_email_has_sources_and_no_original_url(self):
        subject, html, text = self._send(buffer_status="scheduled", buffer_due_at=DUE_AT, buffer_run_cap=2)
        assert subject == DraftNotifier.AUTONOMOUS_SUBJECT
        assert "[mem-birthday] 甘木ジュリは2026年9月28日に生誕祭<予定>" in text
        assert "&lt;予定&gt;" in html
        assert "9/26(土) 22:04 JST" in text
        assert "x.com/intent/tweet?text=" in text
        assert "x.com/juri_bigangel/status" not in text

    def test_skipped_email_has_reason_and_no_intent(self):
        _, _, text = self._send(draft_text="", reason="記憶が古い", buffer_status="skipped")
        assert "独り言を見送りました" in text
        assert "記憶が古い" in text
        assert "intent/tweet" not in text

    def test_send_failure_returns_false(self):
        ses_client = MagicMock()
        ses_client.send_email.side_effect = RuntimeError("ses")
        notifier = DraftNotifier(ses_client=ses_client, from_email="f", to_email="t")
        assert notifier.send_autonomous_email(kind_label="k", draft_text="t", reason="r", sources=[]) is False
