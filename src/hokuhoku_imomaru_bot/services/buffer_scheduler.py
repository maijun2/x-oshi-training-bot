"""
BufferSchedulerクラス

推し投稿への応答を Buffer のキューに予約投入します（半人力運用）。
メール素案（DraftNotifier）と並列で動き、人間がメールで確認して
NG なら Buffer 側で削除する。予約時刻は Buffer のスロット設定に任せる。
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..clients.buffer_client import BufferClient
from ..models.bot_state import BotState
from .state_store import StateStore

logger = logging.getLogger(__name__)

EMOTION_IMAGE_ALT_TEXT = "ほくほくいも丸くんのスタンプ"


@dataclass
class ScheduledPost:
    """Buffer に投入した予約投稿"""
    post_id: str
    due_at: Optional[datetime]
    image_attached: bool


class BufferScheduler:
    """
    推し投稿への応答を Buffer キューに投入するクラス

    - 1日の投入件数をキャップして Buffer 無料枠（10件）を溢れさせない
    - 感情画像は S3 の presigned URL で添付（1日1回、成功時のみフラグを立てる）
    """

    def __init__(
        self,
        buffer_client: BufferClient,
        state_store: StateStore,
        s3_client,
        bucket_name: str,
        oshi_username: str,
        daily_cap: int = 3,
        image_url_ttl_seconds: int = 3600,
    ):
        """
        Args:
            buffer_client: BufferClient インスタンス
            state_store: StateStore（感情画像ファイル名の取得に使用）
            s3_client: boto3 S3 クライアント（presigned URL 生成）
            bucket_name: 感情画像を置いている S3 バケット名
            oshi_username: 推しの X ユーザー名（元ツイート URL 用）
            daily_cap: 1日の Buffer 投入件数の上限
            image_url_ttl_seconds: presigned URL の有効期限（秒）
        """
        self._buffer_client = buffer_client
        self._state_store = state_store
        self._s3_client = s3_client
        self._bucket_name = bucket_name
        self._oshi_username = oshi_username
        self._daily_cap = daily_cap
        self._image_url_ttl_seconds = image_url_ttl_seconds

    @property
    def daily_cap(self) -> int:
        return self._daily_cap

    def can_schedule(self, state: BotState) -> bool:
        """本日のキャップに達していなければ True"""
        return state.daily_buffer_count < self._daily_cap

    def can_attach_image(self, state: BotState) -> bool:
        """本日まだ画像を添付しておらず、かつ投入枠が残っていれば True"""
        return self.can_schedule(state) and not state.daily_image_posted

    def build_post_text(self, draft_text: str, tweet_id: str) -> str:
        """投稿本文 = AI 応答 ＋ 空行 ＋ 元ツイート URL（x.com 形式）"""
        original_url = f"https://x.com/{self._oshi_username}/status/{tweet_id}"
        return f"{draft_text}\n\n{original_url}"

    def schedule_quote(
        self,
        state: BotState,
        tweet_id: str,
        draft_text: str,
        emotion_key: Optional[str] = None,
    ) -> Optional[ScheduledPost]:
        """
        応答を Buffer キューに投入する

        Args:
            state: ボット状態（キャップ判定・画像フラグを更新する）
            tweet_id: 推しの元ツイート ID（監視で取得済み。追加取得しない）
            draft_text: AI 生成した応答テキスト（URL なし）
            emotion_key: 感情キー（画像を添付する場合）

        Returns:
            投入結果。キャップ到達時は None

        Raises:
            BufferAPIError 等: 投入に失敗した場合（握りつぶしは呼び出し元の責務）
        """
        if not self.can_schedule(state):
            logger.info(
                f"Buffer daily cap reached ({state.daily_buffer_count}/{self._daily_cap}); "
                f"email only for tweet {tweet_id}"
            )
            return None

        image_url = None
        if emotion_key and not state.daily_image_posted:
            image_url = self._build_emotion_image_url(emotion_key)

        post = self._buffer_client.add_to_queue(
            text=self.build_post_text(draft_text, tweet_id),
            image_url=image_url,
            alt_text=EMOTION_IMAGE_ALT_TEXT if image_url else None,
        )

        state.daily_buffer_count += 1
        image_attached = bool(image_url) and len(post.asset_urls) > 0
        if image_attached:
            state.daily_image_posted = True
        elif image_url:
            logger.error(
                f"Buffer accepted post {post.id} but returned no assets; image not attached"
            )

        logger.info(
            f"Buffer scheduled quote for tweet {tweet_id}: post={post.id} "
            f"due_at={post.due_at} image={image_attached} "
            f"count={state.daily_buffer_count}/{self._daily_cap}"
        )
        return ScheduledPost(post_id=post.id, due_at=post.due_at, image_attached=image_attached)

    def _build_emotion_image_url(self, emotion_key: str) -> Optional[str]:
        """
        感情キーに対応する S3 画像の presigned URL を返す

        失敗しても投稿自体は落とさない（画像なしで続行）ため、None を返す。
        """
        try:
            filename = self._state_store.get_emotion_image_filename(emotion_key)
            if not filename:
                return None
            return self._s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket_name, "Key": f"emotions/{filename}"},
                ExpiresIn=self._image_url_ttl_seconds,
            )
        except Exception as e:
            logger.error(f"Failed to build emotion image URL for {emotion_key}: {e}")
            return None
