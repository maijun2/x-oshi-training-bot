"""
推しの記憶（AgentCore Memory のレコード）の判定（Lambda と頭脳 AgentCore Runtime の単一ソース）

このモジュールは `agent/memory_filters.py` からシンボリックリンクで参照され、Runtime の
デプロイパッケージにも同梱される（prompts.py と同じ方式）。**パッケージ相対 import を書かないこと**。

- 頭脳の react（3a-read）: ファン視点・生活の細部の除外
- Lambda の自律投稿の候補選び（3b-1）: 上に加えて自律用の除外語、イベント語・告知語・取り組み語、
  本文中の日付の抽出、preferences の JSON の読み取り
"""
import json
import re
from datetime import date
from typing import List, Optional, Tuple

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

# これからの予定・決定の告知（3b-1 (ii)）。B（終わった出来事の余韻）から外し、C（これからの活動へのエール）に回す
ANNOUNCE_WORDS = ("予定", "決定", "リリース", "キャンペーン", "発売")

# タイプ C（進行中・これからの活動へのエール、3b-1 (ii)）の対象にする語。告知語も含む
ONGOING_WORDS = ANNOUNCE_WORDS + ("取り組", "やっている", "つもり", "向上心", "準備", "練習", "挑戦", "目指")

# タイプ D（好み・小ネタ、3b-1 (ii)）だけで追加する除外語（苦手なもの・本人のお願い・不満はファンが話題にしない）
PREFERENCE_EXTRA_EXCLUDE_WORDS = ("苦手", "隠して", "不満")

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


def is_announcement(text: str) -> bool:
    return any(word in text for word in ANNOUNCE_WORDS)


def is_ongoing(text: str) -> bool:
    return any(word in text for word in ONGOING_WORDS)


def preference_parts(raw: str) -> Optional[Tuple[str, str]]:
    """
    preferences のレコード（{"context", "preference", ...} の JSON）を (context, preference) に分ける

    JSON でなければ本文全体を preference とみなす（context は空）。preference が空なら None。
    """
    try:
        parsed = json.loads(raw)
    except ValueError:
        return ("", raw.strip()) if raw.strip() else None
    if not isinstance(parsed, dict):
        return None
    preference = parsed.get("preference")
    if not isinstance(preference, str) or not preference.strip():
        return None
    return str(parsed.get("context", "")), preference.strip()


def preference_text(raw: str) -> Optional[str]:
    """react に渡す本人の好みの 1 文（ファン視点・生活の細部は None）"""
    parts = preference_parts(raw)
    if parts is None:
        return None
    context, preference = parts
    if is_fan_view(context) or is_fan_view(preference) or is_private_life(preference):
        return None
    return preference


def is_excluded_preference_for_autonomous(context: str, preference: str) -> bool:
    """タイプ D の材料にしない好み（ファン視点・生活の細部・苦手なもの・本人のお願い）"""
    text = f"{context}\n{preference}"
    return (
        is_fan_view(context)
        or is_excluded_for_autonomous(preference)
        or is_private_life(text)
        or any(word in text for word in AUTONOMOUS_EXTRA_EXCLUDE_WORDS + PREFERENCE_EXTRA_EXCLUDE_WORDS)
    )


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
