"""
ProfileUpdaterクラス

X API v1.1を使用してプロフィールを更新し、レベルアップ投稿を送信します。
プロフィール画像・名前の更新は月に一度のみ実行されます（Xのレート制限対策）。
"""
import base64
import logging
from datetime import datetime, timezone, timedelta
from io import BytesIO
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# プロフィール名のテンプレート
PROFILE_NAME_TEMPLATE = "ほくほくいも丸くん🍠Lv.{level}"

# レベルアップ投稿のテンプレート
LEVEL_UP_TEMPLATE = """レベルが{level}にあがったｲﾓ🍠
じゅりちゃんの投稿：{oshi_xp:.1f} XP
グループの投稿：{group_xp:.1f} XP
みんなからのいいね：{like_xp:.1f} XP
みんなのリポスト：{repost_xp:.1f} XP
次のレベルまで: {next_level_xp} XP
#さつまいもの民 #びっくえんじぇる"""

# 日本時間のタイムゾーン
JST = timezone(timedelta(hours=9))


class ProfileUpdater:
    """
    X API v1.1を使用してプロフィールを更新するクラス
    
    Attributes:
        api_client: XAPIClientインスタンス
    """
    
    def __init__(self, api_client):
        """
        ProfileUpdaterを初期化
        
        Args:
            api_client: XAPIClientインスタンス
        """
        self.api_client = api_client
    
    def get_current_month_jst(self) -> str:
        """
        現在の月を日本時間で取得（YYYY-MM形式）
        
        Returns:
            YYYY-MM形式の文字列
        """
        now_jst = datetime.now(JST)
        return now_jst.strftime("%Y-%m")
    
    def should_update_profile(self, last_profile_update_month: Optional[str]) -> bool:
        """
        プロフィール更新を実行すべきかチェック（月に一度のみ）
        
        Args:
            last_profile_update_month: 最後にプロフィールを更新した月（YYYY-MM形式）
        
        Returns:
            更新すべきならTrue
        """
        current_month = self.get_current_month_jst()
        
        if last_profile_update_month is None:
            return True
        
        return current_month != last_profile_update_month
    
    def generate_profile_name(self, level: int) -> str:
        """
        レベルに基づいてプロフィール名を生成
        
        Args:
            level: 現在のレベル
        
        Returns:
            生成されたプロフィール名
        """
        return PROFILE_NAME_TEMPLATE.format(level=level)
    
    def update_profile_image(self, image_data: BytesIO) -> bool:
        """
        プロフィール画像を更新
        
        Args:
            image_data: 画像データのBytesIO
        
        Returns:
            更新成功の可否
        """
        try:
            # 画像をBase64エンコード
            image_data.seek(0)
            image_bytes = image_data.read()
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            
            # X API v1.1でプロフィール画像を更新
            result = self.api_client.update_profile_image(image_base64)
            
            if result:
                logger.info("Profile image updated successfully")
                return True
            else:
                logger.warning("Profile image update returned False")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update profile image: {e}")
            return False
    
    def update_profile_name(self, level: int) -> bool:
        """
        プロフィール名を更新
        
        Args:
            level: 現在のレベル
        
        Returns:
            更新成功の可否
        """
        try:
            new_name = self.generate_profile_name(level)
            
            # X API v1.1でプロフィール名を更新
            result = self.api_client.update_profile(name=new_name)
            
            if result:
                logger.info(f"Profile name updated to: {new_name}")
                return True
            else:
                logger.warning("Profile name update returned False")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update profile name: {e}")
            return False

    
    def generate_level_up_text(
        self,
        level: int,
        xp_breakdown: Dict[str, float],
        next_level_xp: int,
    ) -> str:
        """
        レベルアップ投稿のテキストを生成
        
        Args:
            level: 新しいレベル
            xp_breakdown: XPの内訳
                {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
            next_level_xp: 次のレベルまでに必要なXP
        
        Returns:
            レベルアップ投稿テキスト
        """
        return LEVEL_UP_TEMPLATE.format(
            level=level,
            oshi_xp=xp_breakdown.get("oshi_post", 0.0),
            group_xp=xp_breakdown.get("group_post", 0.0),
            like_xp=xp_breakdown.get("like", 0.0),
            repost_xp=xp_breakdown.get("repost", 0.0),
            next_level_xp=next_level_xp,
        )
    
    def post_level_up_announcement(
        self,
        level: int,
        xp_breakdown: Dict[str, float],
        next_level_xp: int,
    ) -> bool:
        """
        レベルアップを報告する投稿を送信
        
        Args:
            level: 新しいレベル
            xp_breakdown: XPの内訳
                {"oshi_post": 25.0, "group_post": 10.0, "like": 8.0, "repost": 5.0}
            next_level_xp: 次のレベルまでに必要なXP
        
        Returns:
            投稿成功の可否
        """
        try:
            text = self.generate_level_up_text(level, xp_breakdown, next_level_xp)
            
            # X API v2で投稿
            result = self.api_client.post_tweet(text)
            
            if result:
                logger.info(f"Level up announcement posted: Lv.{level}")
                return True
            else:
                logger.warning("Level up announcement post returned False")
                return False
                
        except Exception as e:
            logger.error(f"Failed to post level up announcement: {e}")
            return False
    
    def update_profile_on_level_up(
        self,
        level: int,
        image_data: Optional[BytesIO],
        xp_breakdown: Dict[str, float],
        next_level_xp: int,
        last_profile_update_month: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        レベルアップ時にプロフィールを一括更新
        プロフィール画像・名前の更新は月に一度のみ実行
        
        Args:
            level: 新しいレベル
            image_data: 合成された画像データ（Noneの場合は画像更新をスキップ）
            xp_breakdown: XPの内訳
            next_level_xp: 次のレベルまでに必要なXP
            last_profile_update_month: 最後にプロフィールを更新した月（YYYY-MM形式）
        
        Returns:
            各更新の成功状況と更新月
            {"image": bool, "name": bool, "announcement": bool, "profile_update_month": str or None}
        """
        results = {
            "image": False,
            "name": False,
            "announcement": False,
            "profile_update_month": None,
        }
        
        # 月次チェック：プロフィール更新は月に一度のみ
        should_update = self.should_update_profile(last_profile_update_month)
        
        if should_update:
            # プロフィール画像を更新
            if image_data is not None:
                results["image"] = self.update_profile_image(image_data)
            else:
                logger.info("Skipping profile image update (no image data)")
                results["image"] = True  # スキップは成功扱い
            
            # プロフィール名を更新
            results["name"] = self.update_profile_name(level)
            
            # 更新月を記録
            if results["image"] or results["name"]:
                results["profile_update_month"] = self.get_current_month_jst()
        else:
            logger.info(f"Skipping profile update (already updated this month: {last_profile_update_month})")
            results["image"] = True  # スキップは成功扱い
            results["name"] = True
        
        # レベルアップ投稿を送信（これは毎回実行）
        results["announcement"] = self.post_level_up_announcement(
            level, xp_breakdown, next_level_xp
        )
        
        return results
