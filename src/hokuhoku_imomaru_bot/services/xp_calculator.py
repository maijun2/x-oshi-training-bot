"""
XPCalculatorクラス

活動タイプに基づいてXPを計算します。
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict


class ActivityType(Enum):
    """活動タイプの列挙型"""
    OSHI_POST = "oshi_post"      # 推しの投稿検知
    GROUP_POST = "group_post"    # グループの投稿検知
    REPOST = "repost"            # リポスト
    LIKE = "like"                # いいね


@dataclass(frozen=True)
class XPRates:
    """XPレート定数"""
    OSHI_POST: float = 5.0   # 推しの投稿検知: 5.0 XP
    GROUP_POST: float = 2.0  # グループの投稿検知: 2.0 XP
    REPOST: float = 0.5      # リポスト: 0.5 XP
    LIKE: float = 0.1        # いいね: 0.1 XP


class XPCalculator:
    """
    活動タイプに基づいてXPを計算するクラス
    
    Attributes:
        rates: XPレート設定
    """
    
    # デフォルトのXPレート
    DEFAULT_RATES = XPRates()
    
    def __init__(self, rates: XPRates = None):
        """
        XPCalculatorを初期化
        
        Args:
            rates: カスタムXPレート（省略時はデフォルト値を使用）
        """
        self.rates = rates or self.DEFAULT_RATES
    
    def get_rate(self, activity_type: ActivityType) -> float:
        """
        活動タイプに対応するXPレートを取得
        
        Args:
            activity_type: 活動タイプ
        
        Returns:
            XPレート
        """
        rate_map = {
            ActivityType.OSHI_POST: self.rates.OSHI_POST,
            ActivityType.GROUP_POST: self.rates.GROUP_POST,
            ActivityType.REPOST: self.rates.REPOST,
            ActivityType.LIKE: self.rates.LIKE,
        }
        return rate_map[activity_type]
    
    def calculate_xp(self, activity_type: ActivityType, count: int = 1) -> float:
        """
        活動タイプと回数からXPを計算
        
        Args:
            activity_type: 活動タイプ
            count: 活動回数（デフォルト: 1）
        
        Returns:
            獲得XP
        """
        if count < 0:
            raise ValueError("count must be non-negative")
        return self.get_rate(activity_type) * count
    
    def calculate_total_xp(self, activities: Dict[ActivityType, int]) -> float:
        """
        複数の活動からの合計XPを計算
        
        Args:
            activities: 活動タイプと回数のマッピング
        
        Returns:
            合計XP
        """
        total = 0.0
        for activity_type, count in activities.items():
            total += self.calculate_xp(activity_type, count)
        return total
    
    def calculate_xp_breakdown(
        self,
        oshi_post_count: int = 0,
        group_post_count: int = 0,
        repost_count: int = 0,
        like_count: int = 0,
    ) -> Dict[str, float]:
        """
        各活動タイプのXP内訳を計算
        
        Args:
            oshi_post_count: 推しの投稿検出回数
            group_post_count: グループの投稿検出回数
            repost_count: リポスト回数
            like_count: いいね回数
        
        Returns:
            各活動タイプのXP内訳
        """
        return {
            "oshi_post": self.calculate_xp(ActivityType.OSHI_POST, oshi_post_count),
            "group_post": self.calculate_xp(ActivityType.GROUP_POST, group_post_count),
            "repost": self.calculate_xp(ActivityType.REPOST, repost_count),
            "like": self.calculate_xp(ActivityType.LIKE, like_count),
        }
