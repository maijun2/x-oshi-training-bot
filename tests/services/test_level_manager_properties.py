"""
LevelManagerクラスのプロパティベーステスト

Property 8: レベルアップ判定の正確性
"""
import json
import pytest
from pathlib import Path
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from src.hokuhoku_imomaru_bot.services import LevelManager


def load_xp_table() -> dict:
    """DQ3経験値テーブルを読み込む"""
    json_path = Path(__file__).parent.parent.parent / "data" / "dq3_xp_table.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["level"]: item["required_xp"] for item in data["levels"]}


# DQ3経験値テーブルを使用
XP_TABLE = load_xp_table()


@settings(max_examples=100)
@given(
    current_level=st.integers(min_value=1, max_value=98),
    xp_offset=st.floats(min_value=0.0, max_value=1000000.0, allow_nan=False, allow_infinity=False),
)
def test_level_up_accuracy(current_level, xp_offset):
    """
    Feature: hokuhoku-imomaru-bot, Property 8: レベルアップ判定の正確性
    
    *任意の*レベルと経験値に対して、レベルアップ判定は経験値テーブルに従うべきである
    
    **Validates: Requirements 4.2, 4.3**
    """
    manager = LevelManager(XP_TABLE)
    
    # 現在レベルの必要経験値 + オフセット
    base_xp = XP_TABLE[current_level]
    cumulative_xp = base_xp + xp_offset
    
    leveled_up, new_level = manager.check_level_up(current_level, cumulative_xp)
    
    # 新しいレベルの経験値要件を満たしていることを確認
    if leveled_up:
        assert new_level > current_level
        assert cumulative_xp >= XP_TABLE[new_level]
    else:
        # レベルアップしない場合、次のレベルの経験値に達していない
        if current_level < 99:
            assert cumulative_xp < XP_TABLE[current_level + 1]


@settings(max_examples=100)
@given(level=st.integers(min_value=1, max_value=99))
def test_level_threshold_boundary(level):
    """
    レベル境界での判定が正確であることを確認
    
    **Validates: Requirements 4.2, 4.3**
    """
    manager = LevelManager(XP_TABLE)
    
    threshold_xp = XP_TABLE[level]
    
    # ちょうど閾値の経験値でそのレベルになる
    calculated_level = manager.calculate_level(threshold_xp)
    assert calculated_level == level
    
    # 閾値より1少ない経験値では前のレベル（レベル1以外）
    if level > 1:
        calculated_level_below = manager.calculate_level(threshold_xp - 1)
        assert calculated_level_below == level - 1


@settings(max_examples=100)
@given(
    cumulative_xp=st.floats(min_value=0.0, max_value=200000000.0, allow_nan=False, allow_infinity=False),
)
def test_calculated_level_is_valid(cumulative_xp):
    """
    *任意の*経験値に対して、計算されたレベルは1〜99の範囲内であるべきである
    
    **Validates: Requirements 4.2, 4.3**
    """
    manager = LevelManager(XP_TABLE)
    
    level = manager.calculate_level(cumulative_xp)
    
    assert 1 <= level <= 99


@settings(max_examples=100)
@given(
    xp1=st.floats(min_value=0.0, max_value=100000000.0, allow_nan=False, allow_infinity=False),
    xp2=st.floats(min_value=0.0, max_value=100000000.0, allow_nan=False, allow_infinity=False),
)
def test_level_is_monotonic(xp1, xp2):
    """
    経験値が増えるとレベルは減らない（単調増加）
    
    **Validates: Requirements 4.2, 4.3**
    """
    manager = LevelManager(XP_TABLE)
    
    level1 = manager.calculate_level(xp1)
    level2 = manager.calculate_level(xp2)
    
    if xp1 <= xp2:
        assert level1 <= level2
    else:
        assert level1 >= level2
