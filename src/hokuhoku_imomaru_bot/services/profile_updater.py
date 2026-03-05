"""
ProfileUpdaterクラス

X API v1.1を使用してプロフィールを更新し、レベルアップ投稿を送信します。
プロフィールバナー画像・名前の更新は月に一度のみ実行されます（Xのレート制限対策）。
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

# レベルアップ画像のS3キー
LEVEL_UP_IMAGE_KEY = "level_up_image.png"


class ProfileUpdater:
    """
    X API v1.1を使用してプロフィールを更新するクラス
    
    Attributes:
        api_client: XAPIClientインスタンス
        s3_client: boto3 S3クライアント（オプション）
        bucket_name: S3バケット名（オプション）
    """
    
    def __init__(self, api_client, s3_client=None, bucket_name: str = None):
        """
        ProfileUpdaterを初期化
        
        Args:
            api_client: XAPIClientインスタンス
            s3_client: boto3 S3クライアント（レベルアップ画像取得用）
            bucket_name: S3バケット名
        """
        self.api_client = api_client
        self.s3_client = s3_client
        self.bucket_name = bucket_name
    
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
        プロフィールバナー画像を更新
        
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
            
            # X API v1.1でプロフィールバナー画像を更新
            result = self.api_client.update_profile_banner(image_base64)
            
            if result:
                logger.info("Profile banner updated successfully")
                return True
            else:
                logger.warning("Profile banner update returned False")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update profile banner: {e}")
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
        レベルアップを報告する投稿を送信（画像付き）
        
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
            
            # S3から画像を取得してアップロード
            media_ids = None
            if self.s3_client and self.bucket_name:
                media_id = self._upload_level_up_image()
                if media_id:
                    media_ids = [media_id]
            
            # X API v2で投稿（画像付き）
            result = self.api_client.post_tweet(text, media_ids=media_ids)
            
            if result:
                logger.info(f"Level up announcement posted: Lv.{level} (with_image={media_ids is not None})")
                return True
            else:
                logger.warning("Level up announcement post returned False")
                return False
                
        except Exception as e:
            logger.error(f"Failed to post level up announcement: {e}")
            return False
    
    def _upload_level_up_image(self) -> Optional[str]:
        """
        S3からレベルアップ画像を取得してXにアップロード
        
        Returns:
            media_id文字列（失敗時はNone）
        """
        try:
            # S3から画像を取得
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=LEVEL_UP_IMAGE_KEY,
            )
            image_data = response["Body"].read()
            
            # Xにアップロード
            media_id = self.api_client.upload_media(image_data)
            return media_id
            
        except Exception as e:
            logger.error(f"Failed to upload level up image: {e}")
            return None
    
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
        プロフィールバナー画像・名前の更新は月に一度のみ実行
        
        Args:
            level: 新しいレベル
            image_data: 合成された画像データ（Noneの場合はバナー画像更新をスキップ）
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
            # プロフィールバナー画像を更新
            if image_data is not None:
                results["image"] = self.update_profile_image(image_data)
            else:
                logger.info("Skipping profile banner update (no image data)")
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
