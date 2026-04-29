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
    ) -> str:
        return (
            f"【推し投稿への応答素案】\n\n"
            f"■ 元の投稿\n{original_tweet_text}\n{original_url}\n\n"
            f"■ 投稿素案\n{draft_text}\n\n"
            f"■ X で投稿する\n{intent_url}\n"
        )
