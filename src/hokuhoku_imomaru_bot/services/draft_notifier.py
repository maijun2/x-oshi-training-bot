"""
DraftNotifierクラス

推し投稿への AI 応答素案を HTML メールで通知します。
メール内の X Intent リンクから Web UI 経由でポストできます（API 課金なし）。
"""
import logging
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

# Buffer の予約キュー（メールから削除しに行く先）
BUFFER_QUEUE_URL = "https://publish.buffer.com/"


class DraftNotifier:
    """
    推し投稿への AI 応答素案をメールで通知するクラス

    SES で HTML メールを送信し、X Intent リンクから直接ポストできるようにする。
    Web UI 経由のポストは X API 課金対象外。
    """

    SUBJECT = "【いも丸】推し投稿への応答素案ｲﾓ🍠"

    # Buffer 投入状況（_post_quote_safe から渡される）
    BUFFER_STATUS_DISABLED = "disabled"    # Buffer 連携なし（セクション非表示）
    BUFFER_STATUS_SCHEDULED = "scheduled"  # 予約投入済み（NG なら Buffer で削除）
    BUFFER_STATUS_CAP = "cap"              # 本日のキャップ到達（メールのみ）
    BUFFER_STATUS_FAILED = "failed"        # 投入失敗（メールのみ）

    def __init__(
        self,
        ses_client,
        from_email: str,
        to_email: str,
    ):
        """
        DraftNotifier を初期化

        Args:
            ses_client: boto3 SES クライアント
            from_email: 送信元メールアドレス（SES 検証済み）
            to_email: 通知先メールアドレス
        """
        self._ses_client = ses_client
        self._from_email = from_email
        self._to_email = to_email

    def send_draft_email(
        self,
        original_tweet_text: str,
        original_tweet_id: str,
        oshi_username: str,
        draft_text: str,
        emotion_key: Optional[str] = None,
        buffer_status: str = BUFFER_STATUS_DISABLED,
        buffer_due_at: Optional[datetime] = None,
        buffer_daily_cap: Optional[int] = None,
    ) -> bool:
        """
        投稿素案をメールで送信

        Args:
            original_tweet_text: 推しの元ツイート本文
            original_tweet_id: 推しの元ツイート ID
            oshi_username: 推しの X ユーザー名
            draft_text: AI 生成した応答テキスト（URL なし）
            emotion_key: 感情キー（Buffer に画像添付した場合のみ。メール表示用）
            buffer_status: Buffer 投入状況（BUFFER_STATUS_*）
            buffer_due_at: Buffer の予約時刻（scheduled のとき）
            buffer_daily_cap: 1日の投入キャップ（cap のときの表示用）

        Returns:
            送信成功の可否
        """
        try:
            original_url = f"https://x.com/{oshi_username}/status/{original_tweet_id}"
            intent_url = self._build_intent_url(draft_text, original_url)
            buffer_note = self._build_buffer_note(buffer_status, buffer_due_at, buffer_daily_cap)

            html_body = self._build_html(
                original_tweet_text=original_tweet_text,
                original_url=original_url,
                draft_text=draft_text,
                intent_url=intent_url,
                emotion_key=emotion_key,
                buffer_status=buffer_status,
                buffer_note=buffer_note,
            )
            text_body = self._build_plain_text(
                original_tweet_text=original_tweet_text,
                original_url=original_url,
                draft_text=draft_text,
                intent_url=intent_url,
                buffer_note=buffer_note,
            )

            self._ses_client.send_email(
                Source=self._from_email,
                Destination={"ToAddresses": [self._to_email]},
                Message={
                    "Subject": {
                        "Data": self.SUBJECT,
                        "Charset": "UTF-8",
                    },
                    "Body": {
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                    },
                },
            )

            logger.info(
                f"Draft email sent for tweet {original_tweet_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send draft email: {e}")
            return False

    @staticmethod
    def _build_intent_url(draft_text: str, original_url: str) -> str:
        """
        X Intent URL を生成（テキスト末尾に元ツイート URL を付加）

        Web UI 経由のポストは X API 課金対象外。
        """
        full_text = f"{draft_text}\n\n{original_url}"
        return "https://x.com/intent/tweet?text=" + urllib.parse.quote(full_text)

    @classmethod
    def _build_buffer_note(
        cls,
        buffer_status: str,
        buffer_due_at: Optional[datetime],
        buffer_daily_cap: Optional[int],
    ) -> Optional[str]:
        """
        Buffer 投入状況の説明文（HTML / テキスト共通）。disabled のときは None
        """
        if buffer_status == cls.BUFFER_STATUS_SCHEDULED:
            if buffer_due_at is not None:
                jst = buffer_due_at.astimezone(JST)
                when = f"{jst.month}/{jst.day}({WEEKDAYS_JA[jst.weekday()]}) {jst:%H:%M} JST"
            else:
                when = "次の空きスロット"
            return (
                f"Buffer に予約済み: {when} に自動投稿されます。"
                f"内容が NG なら Buffer のキューから削除してください。"
            )
        if buffer_status == cls.BUFFER_STATUS_CAP:
            cap = f"{buffer_daily_cap}件" if buffer_daily_cap is not None else "上限"
            return (
                f"本日の Buffer 予約枠（{cap}）は上限に達したため、Buffer には入れていません。"
                f"投稿する場合は下の X リンクから手動でどうぞ。"
            )
        if buffer_status == cls.BUFFER_STATUS_FAILED:
            return (
                "⚠️ Buffer への予約投入に失敗しました。"
                "投稿する場合は下の X リンクから手動でどうぞ。"
            )
        return None

    @staticmethod
    def _build_html(
        original_tweet_text: str,
        original_url: str,
        draft_text: str,
        intent_url: str,
        emotion_key: Optional[str],
        buffer_status: str = "disabled",
        buffer_note: Optional[str] = None,
    ) -> str:
        def _escape(text: str) -> str:
            return (
                text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
            )

        post_text = f"{draft_text}\n\n{original_url}"
        escaped_post_text = _escape(post_text)
        escaped_original = _escape(original_tweet_text)

        emotion_section = (
            f"""
        <div style="margin-bottom: 25px;">
          <p style="font-weight: bold; color: #888; font-size: 14px; margin: 0 0 8px;">▼ 感情タグ</p>
          <p style="background: #f5f5f5; padding: 10px 15px; border-radius: 8px; font-size: 13px;
                     color: #555; margin: 0; display: inline-block;">{_escape(emotion_key)}</p>
        </div>"""
            if emotion_key
            else ""
        )

        if buffer_note:
            # 予約済みは青系、キャップ/失敗は注意色で区別する
            is_scheduled = buffer_status == "scheduled"
            note_bg = "#e8f4fd" if is_scheduled else "#fff4e5"
            note_color = "#1a5276" if is_scheduled else "#8a4b00"
            buffer_link = (
                f'<a href="{BUFFER_QUEUE_URL}" style="font-size: 13px; color: #1da1f2;">Buffer のキューを開く →</a>'
                if is_scheduled
                else ""
            )
            buffer_section = f"""
        <div style="margin-bottom: 25px;">
          <p style="font-weight: bold; margin-bottom: 8px; font-size: 14px;">▼ Buffer 予約</p>
          <p style="background: {note_bg}; color: {note_color}; padding: 12px 15px; border-radius: 8px;
                    font-size: 13px; line-height: 1.6; margin: 0 0 8px;">{_escape(buffer_note)}</p>
          {buffer_link}
        </div>"""
        else:
            buffer_section = ""

        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="margin: 0; padding: 30px 0; background-color: #f9f9f9; font-family: sans-serif;">

  <div style="
    background-color: #ffffff;
    max-width: 600px;
    margin: 0 auto;
    padding: 30px;
    color: #333;
    border-radius: 10px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    border: 1px solid #e0e0e0;
  ">

    <h2 style="font-size: 18px; margin-top: 0; margin-bottom: 20px;
               border-bottom: 2px solid #333; padding-bottom: 10px;">
      🍠 推し投稿の準備完了
    </h2>

    <div style="margin-bottom: 25px;">
      <p style="font-weight: bold; margin-bottom: 8px; font-size: 14px;">▼ 元の投稿</p>
      <p style="background: #f5f5f5; padding: 15px; border-radius: 8px; font-size: 14px;
                line-height: 1.6; white-space: pre-wrap; margin: 0 0 8px;">{escaped_original}</p>
      <a href="{original_url}" style="font-size: 13px; color: #1da1f2;">Xで見る →</a>
    </div>

    <div style="margin-bottom: 25px;">
      <p style="font-weight: bold; margin-bottom: 8px; font-size: 14px;">▼ ツイート本文（素案）</p>
      <p style="background: #f5f5f5; padding: 15px; border-radius: 8px; font-size: 14px;
                line-height: 1.6; white-space: pre-wrap; margin: 0;">{escaped_post_text}</p>
    </div>

    {buffer_section}

    {emotion_section}

    <div style="text-align: center; margin-top: 20px;">
      <a href="{intent_url}" style="
        background-color: #000000;
        color: #ffffff;
        padding: 15px 50px;
        text-decoration: none;
        border-radius: 30px;
        font-weight: bold;
        font-size: 16px;
        display: inline-block;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
      ">Xを開いてペーストする</a>
    </div>

    <p style="margin-top: 30px; font-size: 12px; color: #aaa; text-align: center;">
      ほくほくいも丸くん 自動通知
    </p>

  </div>
</body>
</html>"""

    @staticmethod
    def _build_plain_text(
        original_tweet_text: str,
        original_url: str,
        draft_text: str,
        intent_url: str,
        buffer_note: Optional[str] = None,
    ) -> str:
        buffer_block = f"■ Buffer 予約\n{buffer_note}\n{BUFFER_QUEUE_URL}\n\n" if buffer_note else ""
        return (
            f"【推し投稿への応答素案】\n\n"
            f"■ 元の投稿\n{original_tweet_text}\n{original_url}\n\n"
            f"■ 投稿素案\n{draft_text}\n\n"
            f"{buffer_block}"
            f"■ X で投稿する\n{intent_url}\n"
        )
