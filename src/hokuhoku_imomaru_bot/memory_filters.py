"""
推しの記憶（AgentCore Memory のレコード）の判定（Lambda と頭脳 AgentCore Runtime の単一ソース）

このモジュールは `agent/memory_filters.py` からシンボリックリンクで参照され、Runtime の
デプロイパッケージにも同梱される（prompts.py と同じ方式）。**パッケージ相対 import を書かないこと**。

- 頭脳の react（3a-read）: ファン視点・生活の細部の除外
- Lambda の自律投稿の候補選び（3b-1）: 上に加えて自律用の除外語、イベント語、本文中の日付の抽出
"""
import re
from datetime import date
from typing import List

# ファン視点への誤抽出（「ユーザーは…閲覧・転載…」）は除外する（設計書 §10-11）
FAN_VIEW_PREFIX = "ユーザーは"
FAN_VIEW_WORDS = ("閲覧", "転載", "運営")

# 体調・睡眠など生活の細部（設計書 v19 のタイプ E）。react の記憶からも除外する。
# 出来事と混ざったレコードも丸ごと落とす（取りこぼしより、監視しているような文面を避ける方を優先）
PRIVATE_LIFE_WORDS = ("眠", "寝", "睡眠", "起床", "目覚まし", "体調", "風邪", "発熱", "熱が", "病院", "通院", "怪我", "ケガ")

# 自律投稿だけで追加する除外語（v19 タイプ E: 体調・住環境・失敗談・食生活の反省）。
# react の記憶には効かせない（react は推しの投稿に関係する記憶だけが渡るため）
AUTONOMOUS_EXTRA_EXCLUDE_WORDS = ("腹痛", "お腹", "ヤモリ", "忘れ", "野菜")

# タイプ B（直近の出来事の余韻）の対象にするイベント語（v19: ライブ・公演・配信などイベント系のみ）
EVENT_WORDS = ("ライブ", "公演", "配信", "出演", "イベント", "生誕", "収録", "ラジオ", "特典会", "ステージ")

_DATE_WITH_YEAR = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_DATE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DATE_NO_YEAR = re.compile(r"(?<![\d年])(\d{1,2})月(\d{1,2})日")


def is_fan_view(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(FAN_VIEW_PREFIX) and any(word in stripped for word in FAN_VIEW_WORDS)


def is_private_life(text: str) -> bool:
    return any(word in text for word in PRIVATE_LIFE_WORDS)


def is_excluded_for_autonomous(text: str) -> bool:
    """自律投稿の材料にしないレコード（ファン視点・生活の細部）"""
    return (
        is_fan_view(text)
        or is_private_life(text)
        or any(word in text for word in AUTONOMOUS_EXTRA_EXCLUDE_WORDS)
    )


def is_event(text: str) -> bool:
    return any(word in text for word in EVENT_WORDS)


def _safe_date(year: int, month: int, day: int) -> List[date]:
    try:
        return [date(year, month, day)]
    except ValueError:
        return []


def extract_dates(text: str, base_year: int) -> List[date]:
    """
    本文に書かれた日付を抜き出す（重複なし、出現順）

    「2026年9月28日」「2026-09-28」と、年なしの「9月28日」（base_year で補う）を読む。
    存在しない日付（2 月 30 日など）は捨てる。
    """
    found: List[date] = []
    for m in _DATE_WITH_YEAR.finditer(text):
        found += _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    for m in _DATE_ISO.finditer(text):
        found += _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    for m in _DATE_NO_YEAR.finditer(text):
        found += _safe_date(base_year, int(m.group(1)), int(m.group(2)))
    unique: List[date] = []
    for d in found:
        if d not in unique:
            unique.append(d)
    return unique
