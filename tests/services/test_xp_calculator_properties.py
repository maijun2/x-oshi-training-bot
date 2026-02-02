"""
XPCalculatorクラスのプロパティベーステスト

Property 6: XP計算の正確性
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from src.hokuhoku_imomaru_bot.services import XPCalculator, XPRates, ActivityType


# 活動回数のストラテジー（現実的な範囲）
count_strategy = st.integers(min_value=0, max_value=100000)


@settings(max_examples=100)
@given(
    oshi_count=count_strategy,
    group_count=count_strategy,
    repost_count=count_strategy,
    like_count=count_strategy,
)
def test_xp_calculation_accuracy(oshi_count, group_count, repost_count, like_count):
    """
    Feature: hokuhoku-imomaru-bot, Property 6: XP計算の正確性
    
    *任意の*活動回数に対して、XP計算は以下の式に従うべきである:
    total_xp = oshi_count * 5.0 + group_count * 2.0 + repost_count * 0.5 + like_count * 0.1
    
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
    """
    calc = XPCalculator()
    
    # 期待値を直接計算
    expected_xp = (
        oshi_count * 5.0 +
        group_count * 2.0 +
        repost_count * 0.5 +
        like_count * 0.1
    )
    
    # XPCalculatorで計算
    activities = {
        ActivityType.OSHI_POST: oshi_count,
        ActivityType.GROUP_POST: group_count,
        ActivityType.REPOST: repost_count,
        ActivityType.LIKE: like_count,
    }
    actual_xp = calc.calculate_total_xp(activities)
    
    # 浮動小数点の精度内で一致することを確認
    assert actual_xp == pytest.approx(expected_xp, rel=1e-9)


@settings(max_examples=100)
@given(count=count_strategy)
def test_xp_is_non_negative(count):
    """
    *任意の*非負の活動回数に対して、XPは常に非負であるべきである
    
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
    """
    calc = XPCalculator()
    
    for activity_type in ActivityType:
        xp = calc.calculate_xp(activity_type, count)
        assert xp >= 0.0


@settings(max_examples=100)
@given(count=st.integers(min_value=1, max_value=100000))
def test_xp_is_monotonically_increasing(count):
    """
    *任意の*正の活動回数に対して、回数が増えるとXPも増えるべきである
    
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
    """
    calc = XPCalculator()
    
    for activity_type in ActivityType:
        xp_n = calc.calculate_xp(activity_type, count)
        xp_n_plus_1 = calc.calculate_xp(activity_type, count + 1)
        assert xp_n_plus_1 > xp_n


@settings(max_examples=100)
@given(
    count1=count_strategy,
    count2=count_strategy,
)
def test_xp_is_additive(count1, count2):
    """
    XP計算は加法的であるべきである: xp(a + b) = xp(a) + xp(b)
    
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
    """
    calc = XPCalculator()
    
    for activity_type in ActivityType:
        xp_combined = calc.calculate_xp(activity_type, count1 + count2)
        xp_separate = calc.calculate_xp(activity_type, count1) + calc.calculate_xp(activity_type, count2)
        assert xp_combined == pytest.approx(xp_separate, rel=1e-9)
