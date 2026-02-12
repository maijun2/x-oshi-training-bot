"""
DailyReporter スケジュール最適化のプロパティベーステスト

Property 3: 日報投稿時刻の境界条件
Property 4: 朝コンテンツの時刻・活動量ゲート
"""
import pytest
from datetime import datetime, timezone, timedelta
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from unittest.mock import Mock

from src.hokuhoku_imomaru_bot.services.daily_reporter import (
    DailyReporter,
    DAILY_REPORT_HOUR,
    LOW_ACTIVITY_THRESHOLD,
    JST,
)
from src.hokuhoku_imomaru_bot.models.bot_state import BotState


# JST datetimeを生成するストラテジー
jst_datetimes = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2026, 12, 31),
    timezones=st.just(timezone.utc),
)


class TestProperty3DailyReportHourBoundary:
    """
    **Property 3: 日報投稿時刻の境界条件**

    For any datetime and BotState, should_post_daily_report SHALL return True
    if and only if the JST hour is >= 23 AND the state's last_daily_report_date
    does not equal today's JST date.

    **Validates: Requirements 3.1**
    """

    @given(dt=jst_datetimes, already_posted_today=st.booleans())
    @settings(max_examples=200)
    def test_daily_report_hour_boundary(self, dt, already_posted_today):
        """日報投稿はJST 23時以降かつ未投稿日のみTrue"""
        reporter = DailyReporter(api_client=Mock())

        jst_time = dt.astimezone(JST)
        today_str = jst_time.strftime("%Y-%m-%d")

        state = BotState()
        if already_posted_today:
            state.last_daily_report_date = today_str
        else:
            state.last_daily_report_date = "1970-01-01"

        result = reporter.should_post_daily_report(state, dt)

        expected = (jst_time.hour >= DAILY_REPORT_HOUR) and not already_posted_today
        assert result == expected, (
            f"dt={dt}, jst_hour={jst_time.hour}, "
            f"already_posted={already_posted_today}, "
            f"result={result}, expected={expected}"
        )


class TestProperty4MorningContentGate:
    """
    **Property 4: 朝コンテンツの時刻・活動量ゲート**

    For any datetime and prev_daily_oshi_count, should_post_morning_content
    SHALL return True if and only if the JST hour equals 10 AND
    prev_daily_oshi_count <= LOW_ACTIVITY_THRESHOLD.

    **Validates: Requirements 4.1, 4.3**
    """

    @given(
        dt=jst_datetimes,
        prev_count=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=200)
    def test_morning_content_gate(self, dt, prev_count):
        """朝コンテンツはJST 10時台かつ閾値以下のみTrue"""
        reporter = DailyReporter(api_client=Mock())

        jst_time = dt.astimezone(JST)
        result = reporter.should_post_morning_content(prev_count, dt)

        expected = (jst_time.hour == 10) and (prev_count <= LOW_ACTIVITY_THRESHOLD)
        assert result == expected, (
            f"dt={dt}, jst_hour={jst_time.hour}, "
            f"prev_count={prev_count}, threshold={LOW_ACTIVITY_THRESHOLD}, "
            f"result={result}, expected={expected}"
        )
