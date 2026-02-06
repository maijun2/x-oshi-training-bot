"""
BotStateデータクラス

ボットの状態（累積XP、現在レベル、最新Tweet ID、活動カウント）を管理します。
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


@dataclass
class BotState:
    """
    ボットの状態を表すデータクラス
    
    Attributes:
        cumulative_xp: 累積経験値
        current_level: 現在のレベル
        latest_tweet_id: 最後に処理したTweet ID
        last_updated: 最終更新日時（ISO 8601形式）
        oshi_post_count: 推しの投稿検出回数（累積）
        group_post_count: グループの投稿検出回数（累積）
        repost_count: リポスト回数（累積）
        like_count: いいね回数（累積）
        daily_oshi_count: 今日の推しの投稿検出回数
        daily_group_count: 今日のグループの投稿検出回数
        daily_repost_count: 今日のリポスト回数
        daily_like_count: 今日のいいね回数
        daily_xp: 今日の獲得XP
        last_daily_report_date: 最後の日報投稿日（YYYY-MM-DD形式）
        last_profile_update_month: 最後のプロフィール更新月（YYYY-MM形式）
        total_received_likes: ボット投稿への累積いいね数
        total_received_retweets: ボット投稿への累積リポスト数
    """
    cumulative_xp: float = 0.0
    current_level: int = 1
    latest_tweet_id: Optional[str] = None
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # 累積カウント
    oshi_post_count: int = 0
    group_post_count: int = 0
    repost_count: int = 0
    like_count: int = 0
    # 日次カウント（日報投稿後にリセット）
    daily_oshi_count: int = 0
    daily_group_count: int = 0
    daily_repost_count: int = 0
    daily_like_count: int = 0
    daily_xp: float = 0.0
    last_daily_report_date: Optional[str] = None
    # プロフィール更新制限（月に一度）
    last_profile_update_month: Optional[str] = None  # YYYY-MM形式
    # ボット投稿へのエンゲージメント追跡
    total_received_likes: int = 0      # ボット投稿への累積いいね数
    total_received_retweets: int = 0   # ボット投稿への累積リポスト数
    # 感情画像添付制限（1日1回）
    daily_image_posted: bool = False   # 本日の画像添付済みフラグ

    def to_dict(self) -> dict:
        """
        DynamoDB保存用の辞書に変換
        
        Returns:
            DynamoDB形式の辞書
        """
        result = {
            "state_id": "current",
            "cumulative_xp": self.cumulative_xp,
            "current_level": self.current_level,
            "latest_tweet_id": self.latest_tweet_id,
            "last_updated": self.last_updated,
            "oshi_post_count": self.oshi_post_count,
            "group_post_count": self.group_post_count,
            "repost_count": self.repost_count,
            "like_count": self.like_count,
            "daily_oshi_count": self.daily_oshi_count,
            "daily_group_count": self.daily_group_count,
            "daily_repost_count": self.daily_repost_count,
            "daily_like_count": self.daily_like_count,
            "daily_xp": self.daily_xp,
            "last_daily_report_date": self.last_daily_report_date,
            "last_profile_update_month": self.last_profile_update_month,
            "total_received_likes": self.total_received_likes,
            "total_received_retweets": self.total_received_retweets,
            "daily_image_posted": self.daily_image_posted,
        }
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "BotState":
        """
        DynamoDBから取得した辞書からBotStateを生成
        
        Args:
            data: DynamoDBから取得した辞書
        
        Returns:
            BotStateインスタンス
        """
        return cls(
            cumulative_xp=float(data.get("cumulative_xp", 0.0)),
            current_level=int(data.get("current_level", 1)),
            latest_tweet_id=data.get("latest_tweet_id"),
            last_updated=data.get("last_updated", datetime.now(timezone.utc).isoformat()),
            oshi_post_count=int(data.get("oshi_post_count", 0)),
            group_post_count=int(data.get("group_post_count", 0)),
            repost_count=int(data.get("repost_count", 0)),
            like_count=int(data.get("like_count", 0)),
            daily_oshi_count=int(data.get("daily_oshi_count", 0)),
            daily_group_count=int(data.get("daily_group_count", 0)),
            daily_repost_count=int(data.get("daily_repost_count", 0)),
            daily_like_count=int(data.get("daily_like_count", 0)),
            daily_xp=float(data.get("daily_xp", 0.0)),
            last_daily_report_date=data.get("last_daily_report_date"),
            last_profile_update_month=data.get("last_profile_update_month"),
            total_received_likes=int(data.get("total_received_likes", 0)),
            total_received_retweets=int(data.get("total_received_retweets", 0)),
            daily_image_posted=bool(data.get("daily_image_posted", False)),
        )

    def get_xp_breakdown(self) -> dict:
        """
        XPの内訳を計算（累積）
        
        Returns:
            各活動タイプのXP内訳
        """
        return {
            "oshi_post": self.oshi_post_count * 5.0,
            "group_post": self.group_post_count * 2.0,
            "repost": self.repost_count * 0.5,
            "like": self.like_count * 0.1,
        }

    def get_daily_xp_breakdown(self) -> dict:
        """
        今日のXPの内訳を計算
        
        Returns:
            今日の各活動タイプのXP内訳
        """
        return {
            "oshi_post": self.daily_oshi_count * 5.0,
            "group_post": self.daily_group_count * 2.0,
            "repost": self.daily_repost_count * 0.5,
            "like": self.daily_like_count * 0.1,
        }
