"""
BufferSchedulerクラス

推し投稿への応答を Buffer のキューに予約投入します（半人力運用）。
メール素案（DraftNotifier）と並列で動き、人間がメールで確認して
NG なら Buffer 側で削除する。予約時刻は Buffer のスロット設定に任せる。
"""
import logging
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional, Sequence, Tuple

from ..clients.buffer_client import BufferClient
from ..models.bot_state import BotState
from .daily_reporter import JST
from .state_store import StateStore

logger = logging.getLogger(__name__)

EMOTION_IMAGE_ALT_TEXT = "ほくほくいも丸くんのスタンプ"

# Buffer UI のスロット設定（全曜日共通、JST）の写し。公開予定時刻の見込みにだけ使い、
# 実際の予約時刻は Buffer が決める。UI で枠を変えたら env BUFFER_SLOT_TIMES_JST も合わせる
DEFAULT_SLOT_TIMES_JST: Tuple[str, ...] = (
    "08:00", "11:15", "12:15", "14:15", "15:15", "19:15", "20:15", "22:00",
)


def parse_slot_times(value: str) -> Tuple[time, ...]:
    """"HH:MM,HH:MM,..." を JST の time のタプル（昇順）にする。空や不正な要素は無視"""
    slots = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            hour, minute = item.split(":")
            slots.append(time(int(hour), int(minute), tzinfo=JST))
        except ValueError:
            logger.warning(f"Ignoring invalid Buffer slot time: {item!r}")
    return tuple(sorted(slots))


@dataclass
class ScheduledPost:
    """Buffer に投入した予約投稿"""
    post_id: str
    due_at: Optional[datetime]
    image_attached: bool


class BufferScheduler:
    """
    推し投稿への応答を Buffer キューに投入するクラス

    - 投入件数は 2 段でキャップする
      - run_cap: Lambda 1 回の実行あたりの上限（主キャップ。各実行の検知分を均等に Buffer へ載せる）
      - daily_cap: 1 日の上限（安全弁。スロット数/日より小さくして Buffer 無料枠 10 件を溢れさせない）
      実行内カウンタはこのインスタンスに持つ（invocation ごとに生成される前提）
    - 感情画像は公開バケットの URL で添付（1日1回、成功時のみフラグを立てる）。
      Buffer は投稿公開時に URL を取りに来るため、署名付き URL（期限あり）は使えない
    """

    def __init__(
        self,
        buffer_client: BufferClient,
        state_store: StateStore,
        public_image_base_url: str,
        oshi_username: str,
        daily_cap: int = 7,
        run_cap: int = 1,
        slot_times_jst: Sequence[str] = DEFAULT_SLOT_TIMES_JST,
    ):
        """
        Args:
            buffer_client: BufferClient インスタンス
            state_store: StateStore（感情画像ファイル名の取得に使用）
            public_image_base_url: 感情画像を公開している URL のベース
                （例: https://imomaru-bot-public-assets-123.s3.ap-northeast-1.amazonaws.com）
            oshi_username: 推しの X ユーザー名（元ツイート URL 用）
            daily_cap: 1日の Buffer 投入件数の上限（安全弁）
            run_cap: Lambda 1 回の実行あたりの Buffer 投入件数の上限（主キャップ）
            slot_times_jst: Buffer のスロット時刻（"HH:MM"、JST）。next_slot_at の見込み計算に使う
        """
        self._buffer_client = buffer_client
        self._state_store = state_store
        self._public_image_base_url = public_image_base_url.rstrip("/")
        self._oshi_username = oshi_username
        self._daily_cap = daily_cap
        self._run_cap = run_cap
        self._run_count = 0
        self._slot_times = parse_slot_times(",".join(slot_times_jst))

    @property
    def daily_cap(self) -> int:
        return self._daily_cap

    @property
    def run_cap(self) -> int:
        return self._run_cap

    def next_slot_at(self, now: datetime) -> Optional[datetime]:
        """
        now より後の最初のスロット時刻（見込みの公開時刻）を返す。今日に残り枠がなければ翌日の先頭枠。
        頭脳に「応答が読まれる時刻」として渡す。スロット設定が空なら None
        """
        if not self._slot_times:
            return None
        now_jst = now.astimezone(JST)
        for slot in self._slot_times:
            candidate = datetime.combine(now_jst.date(), slot)
            if candidate > now_jst:
                return candidate
        return datetime.combine(now_jst.date() + timedelta(days=1), self._slot_times[0])

    def can_schedule(self, state: BotState) -> bool:
        """この実行のキャップにも本日のキャップにも達していなければ True"""
        return (
            self._run_count < self._run_cap
            and state.daily_buffer_count < self._daily_cap
        )

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
        if self._run_count >= self._run_cap:
            logger.info(
                f"Buffer run cap reached ({self._run_count}/{self._run_cap}); "
                f"email only for tweet {tweet_id}"
            )
            return None
        if state.daily_buffer_count >= self._daily_cap:
            logger.info(
                f"Buffer daily cap reached ({state.daily_buffer_count}/{self._daily_cap}); "
                f"email only for tweet {tweet_id}"
            )
            return None

        image_url = None
        if emotion_key and not state.daily_image_posted:
            image_url = self.build_emotion_image_url(emotion_key)

        post = self._buffer_client.add_to_queue(
            text=self.build_post_text(draft_text, tweet_id),
            image_url=image_url,
            alt_text=EMOTION_IMAGE_ALT_TEXT if image_url else None,
        )

        self._run_count += 1
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
            f"count=run {self._run_count}/{self._run_cap}, "
            f"daily {state.daily_buffer_count}/{self._daily_cap}"
        )
        return ScheduledPost(post_id=post.id, due_at=post.due_at, image_attached=image_attached)

    def build_emotion_image_url(self, emotion_key: str) -> Optional[str]:
        """
        感情キーに対応する画像の公開 URL を返す（emotions/{filename}）

        失敗しても投稿自体は落とさない（画像なしで続行）ため、None を返す。
        """
        try:
            filename = self._state_store.get_emotion_image_filename(emotion_key)
            if not filename:
                return None
            return f"{self._public_image_base_url}/emotions/{urllib.parse.quote(filename)}"
        except Exception as e:
            logger.error(f"Failed to build emotion image URL for {emotion_key}: {e}")
            return None
