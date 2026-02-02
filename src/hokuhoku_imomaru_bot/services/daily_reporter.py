"""
DailyReporterクラス

日報投稿の生成と送信を行います。
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from ..models.bot_state import BotState

logger = logging.getLogger(__name__)

# 日本標準時（JST）
JST = timezone(timedelta(hours=9))

# 日報投稿のテンプレート
DAILY_REPORT_TEMPLATE = """今日の活動報告ｲﾓ🍠
じゅりちゃんの投稿：{daily_oshi_count}回
グループの投稿：{daily_group_count}回
みんなからのいいね：{daily_like_count}回
みんなのリポスト：{daily_repost_count}回
今日の獲得XP：{daily_xp:.1f} XP
現在Lv.{current_level} → 次まで{next_level_xp} XP
#さつまいもの民 #びっくえんじぇる"""

# 日報投稿時刻（21:00 JST以降）
DAILY_REPORT_HOUR = 21


class DailyReporter:
    """
    日報投稿の生成と送信を行うクラス
    
    Attributes:
        api_client: XAPIClientインスタンス
    """
    
    def __init__(self, api_client):
        """
        DailyReporterを初期化
        
        Args:
            api_client: XAPIClientインスタンス
        """
        self.api_client = api_client
    
    def should_post_daily_report(
        self,
        state: BotState,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """
        日報投稿を行うべきかを判定
        
        Args:
            state: 現在のボット状態
            current_time: 現在時刻（Noneの場合は現在時刻を使用）
        
        Returns:
            日報投稿を行うべきかどうか
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        
        # JSTに変換
        jst_time = current_time.astimezone(JST)
        today = jst_time.strftime("%Y-%m-%d")
        
        # 21:00 JST以降で、今日まだ日報を投稿していない場合
        return (
            jst_time.hour >= DAILY_REPORT_HOUR and
            state.last_daily_report_date != today
        )

    
    def generate_daily_report(
        self,
        state: BotState,
        next_level_xp: int,
    ) -> str:
        """
        日報投稿のテキストを生成
        
        Args:
            state: 現在のボット状態
            next_level_xp: 次のレベルまでに必要なXP
        
        Returns:
            日報投稿テキスト
        """
        return DAILY_REPORT_TEMPLATE.format(
            daily_oshi_count=state.daily_oshi_count,
            daily_group_count=state.daily_group_count,
            daily_like_count=state.daily_like_count,
            daily_repost_count=state.daily_repost_count,
            daily_xp=state.daily_xp,
            current_level=state.current_level,
            next_level_xp=next_level_xp,
        )
    
    def post_daily_report(
        self,
        state: BotState,
        next_level_xp: int,
    ) -> bool:
        """
        日報投稿を送信
        
        Args:
            state: 現在のボット状態
            next_level_xp: 次のレベルまでに必要なXP
        
        Returns:
            投稿成功の可否
        """
        try:
            text = self.generate_daily_report(state, next_level_xp)
            
            # X API v2で投稿
            result = self.api_client.post_tweet(text)
            
            if result:
                logger.info("Daily report posted successfully")
                return True
            else:
                logger.warning("Daily report post returned False")
                return False
                
        except Exception as e:
            logger.error(f"Failed to post daily report: {e}")
            return False
    
    def get_today_date_jst(
        self,
        current_time: Optional[datetime] = None,
    ) -> str:
        """
        現在のJST日付を取得
        
        Args:
            current_time: 現在時刻（Noneの場合は現在時刻を使用）
        
        Returns:
            YYYY-MM-DD形式の日付文字列
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        
        jst_time = current_time.astimezone(JST)
        return jst_time.strftime("%Y-%m-%d")
