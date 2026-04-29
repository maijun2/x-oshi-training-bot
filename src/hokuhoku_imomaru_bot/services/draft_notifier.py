"""
DraftNotifierクラス

推し投稿への AI 応答素案を HTML メールで通知します。
メール内の X Intent リンクから Web UI 経由でポストできます（API 課金なし）。
"""
import logging
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)


class DraftNotifier:
    """
    推し投稿への AI 応答素案をメールで通知するクラス

    SES で HTML メールを送信し、X Intent リンクから直接ポストできるようにする。
    Web UI 経由のポストは X API 課金対象外。
    """

    SUBJECT = "【いも丸】推し投稿への応答素案ｲﾓ🍠"

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
    ) -> bool:
        """
        投稿素案をメールで送信

        Args:
            original_tweet_text: 推しの元ツイート本文
            original_tweet_id: 推しの元ツイート ID
            oshi_username: 推しの X ユーザー名
            draft_text: AI 生成した応答テキスト（URL なし）
            emotion_key: 感情キー（メール表示用、省略可）

        Returns:
            送信成功の可否
        """
        try:
            original_url = f"https://x.com/{oshi_username}/status/{original_tweet_id}"
            intent_url = self._build_intent_url(draft_text, original_url)

            html_body = self._build_html(
                original_tweet_text=original_tweet_text,
                original_url=original_url,
                draft_text=draft_text,
                intent_url=intent_url,
                emotion_key=emotion_key,
            )
            text_body = self._build_plain_text(
                original_tweet_text=original_tweet_text,
                original_url=original_url,
                draft_text=draft_text,
                intent_url=intent_url,
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

    @staticmethod
    def _build_html(
        original_tweet_text: str,
        original_url: str,
        draft_text: str,
        intent_url: str,
        emotion_key: Optional[str],
    ) -> str:
        emotion_line = (
            f'<p style="color:#888;font-size:13px;">感情: {emotion_key}</p>'
            if emotion_key
            else ""
        )
        escaped_original = original_tweet_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        escaped_draft = draft_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")

        return f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:16px;background:#f9f9f9;">
  <h2 style="color:#d4570a;">🍠 推し投稿への応答素案</h2>

  <div style="background:#fff;border:1px solid #ddd;border-radius:8px;padding:16px;margin-bottom:16px;">
    <h3 style="margin:0 0 8px;font-size:14px;color:#555;">元の投稿</h3>
    <p style="margin:0 0 8px;white-space:pre-wrap;">{escaped_original}</p>
    <a href="{original_url}" style="font-size:13px;color:#1da1f2;">Xで見る →</a>
  </div>

  <div style="background:#fff;border:2px solid #d4570a;border-radius:8px;padding:16px;margin-bottom:16px;">
    <h3 style="margin:0 0 8px;font-size:14px;color:#d4570a;">投稿素案</h3>
    <p style="margin:0 0 8px;white-space:pre-wrap;">{escaped_draft}</p>
    {emotion_line}
  </div>

  <a href="{intent_url}"
     style="display:inline-block;background:#1da1f2;color:#fff;text-decoration:none;
            padding:12px 24px;border-radius:24px;font-weight:bold;font-size:15px;">
    Xに投稿する（Web UI）
  </a>
  <p style="margin-top:8px;font-size:12px;color:#999;">
    ※ ボタンをクリックすると X の投稿画面が開きます。内容を確認してから投稿してください。
  </p>
</body>
</html>"""

    @staticmethod
    def _build_plain_text(
        original_tweet_text: str,
        original_url: str,
        draft_text: str,
        intent_url: str,
    ) -> str:
        return (
            f"【推し投稿への応答素案】\n\n"
            f"■ 元の投稿\n{original_tweet_text}\n{original_url}\n\n"
            f"■ 投稿素案\n{draft_text}\n\n"
            f"■ X で投稿する\n{intent_url}\n"
        )
