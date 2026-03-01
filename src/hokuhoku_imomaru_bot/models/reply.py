"""
Replyデータクラス

ボット投稿へのリプライを表すデータモデルです。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Reply:
    """
    リプライを表すデータクラス

    Attributes:
        id: リプライツイートID
        text: リプライ本文
        author_id: リプライ元ユーザーID
        author_username: リプライ元ユーザー名
        created_at: 作成日時（ISO 8601形式）
        in_reply_to_tweet_id: リプライ先ツイートID（ボット投稿のID）
        in_reply_to_user_id: リプライ先ユーザーID（ボットのユーザーID）
    """
    id: str
    text: str
    author_id: str
    author_username: str
    created_at: str
    in_reply_to_tweet_id: str
    in_reply_to_user_id: str

    @classmethod
    def from_api_response(cls, data: dict, includes: Optional[dict] = None) -> "Reply":
        """
        X API v2のレスポンスからReplyを生成

        Args:
            data: APIレスポンスのツイートデータ
            includes: APIレスポンスのincludesデータ（ユーザー情報を含む）

        Returns:
            Replyインスタンス
        """
        # includesからユーザー名を取得
        author_username = ""
        author_id = data.get("author_id", "")
        if includes and "users" in includes:
            for user in includes["users"]:
                if user.get("id") == author_id:
                    author_username = user.get("username", "")
                    break

        # referenced_tweetsからリプライ先ツイートIDを取得
        in_reply_to_tweet_id = ""
        referenced_tweets = data.get("referenced_tweets", [])
        for ref in referenced_tweets:
            if ref.get("type") == "replied_to":
                in_reply_to_tweet_id = ref.get("id", "")
                break

        return cls(
            id=data.get("id", ""),
            text=data.get("text", ""),
            author_id=author_id,
            author_username=author_username,
            created_at=data.get("created_at", ""),
            in_reply_to_tweet_id=in_reply_to_tweet_id,
            in_reply_to_user_id=data.get("in_reply_to_user_id", ""),
        )
