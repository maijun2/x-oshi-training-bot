"""
Buffer API クライアント

Buffer の GraphQL API（https://api.buffer.com）でキューに投稿を予約投入します。
Buffer 経由の投稿は X API の Create 課金対象外（ContentCreateWithUrl 回避）。

参考: https://developers.buffer.com/guides/getting-started.html
      https://developers.buffer.com/reference.html
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

BUFFER_API_URL = "https://api.buffer.com"
REQUEST_TIMEOUT_SECONDS = 30


class BufferAPIError(Exception):
    """Buffer API 呼び出しエラー"""


@dataclass
class BufferCredentials:
    """Buffer API 認証情報"""
    access_token: str
    channel_id: str


@dataclass
class BufferPost:
    """キューに投入された投稿"""
    id: str
    due_at: Optional[datetime]
    asset_urls: List[str]


# createPost の結果は union（PostActionSuccess | LimitReachedError | InvalidInputError | ...）。
# エラー型はすべて MutationError インターフェース（message）を実装する（スキーマ introspection で確認済み）
_CREATE_POST_MUTATION = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess {
      post {
        id
        dueAt
        assets { source mimeType }
      }
    }
    ... on MutationError { message }
  }
}
"""

_DELETE_POST_MUTATION = """
mutation DeletePost($input: DeletePostInput!) {
  deletePost(input: $input) {
    __typename
    ... on DeletePostSuccess { id }
    ... on MutationError { message }
  }
}
"""


class BufferClient:
    """
    Buffer API クライアント（Personal Access Token 認証）

    認証情報は Secrets Manager から遅延読み込みする（XAPIClient と同じ流儀）。
    """

    def __init__(self, secrets_client, secret_name: str):
        """
        Args:
            secrets_client: boto3 Secrets Manager クライアント
            secret_name: シークレット名（access_token / channel_id を含む JSON）
        """
        self._secrets_client = secrets_client
        self._secret_name = secret_name
        self._credentials: Optional[BufferCredentials] = None

    def _load_credentials(self) -> BufferCredentials:
        """Secrets Manager から認証情報を取得（キャッシュあり）"""
        if self._credentials is not None:
            return self._credentials

        try:
            response = self._secrets_client.get_secret_value(SecretId=self._secret_name)
            secret_data = json.loads(response["SecretString"])
            self._credentials = BufferCredentials(
                access_token=secret_data["access_token"],
                channel_id=secret_data["channel_id"],
            )
            # トークンはログに出さない
            logger.info("Buffer API credentials loaded successfully")
            return self._credentials
        except Exception:
            logger.error("Failed to load Buffer API credentials")
            raise

    @property
    def channel_id(self) -> str:
        """投稿先チャンネル ID"""
        return self._load_credentials().channel_id

    def _graphql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        GraphQL リクエストを送信し data を返す

        Raises:
            BufferAPIError: HTTP エラーまたは GraphQL errors
        """
        credentials = self._load_credentials()
        response = requests.post(
            BUFFER_API_URL,
            json={"query": query, "variables": variables},
            headers={
                "Authorization": f"Bearer {credentials.access_token}",
                "Content-Type": "application/json",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise BufferAPIError(
                f"Buffer API HTTP {response.status_code}: {response.text[:300]}"
            )

        body = response.json()
        if body.get("errors"):
            messages = "; ".join(e.get("message", "") for e in body["errors"])
            raise BufferAPIError(f"Buffer API GraphQL error: {messages}")

        return body.get("data") or {}

    def add_to_queue(
        self,
        text: str,
        image_url: Optional[str] = None,
        alt_text: Optional[str] = None,
    ) -> BufferPost:
        """
        投稿をキューに追加する（次の空きスロットに Buffer が自動配置）

        Args:
            text: 投稿本文（元ツイート URL を含む）
            image_url: 添付画像の URL（Buffer が取得できる公開/署名付き URL）
            alt_text: 画像の代替テキスト

        Returns:
            BufferPost

        Raises:
            BufferAPIError: 投入に失敗した場合
        """
        credentials = self._load_credentials()
        # assets / tagIds / needsApproval はスキーマ上 non-null なので空でも明示する
        post_input: Dict[str, Any] = {
            "channelId": credentials.channel_id,
            "text": text,
            "mode": "addToQueue",
            "schedulingType": "automatic",
            "needsApproval": False,
            "tagIds": [],
            "assets": [],
        }
        if image_url:
            post_input["assets"] = [
                {
                    "image": {
                        "url": image_url,
                        "metadata": {"altText": alt_text or "", "userTags": []},
                    }
                }
            ]

        data = self._graphql(_CREATE_POST_MUTATION, {"input": post_input})
        result = data.get("createPost") or {}
        typename = result.get("__typename")
        if typename != "PostActionSuccess":
            raise BufferAPIError(
                f"Buffer createPost failed: {typename}: {result.get('message')}"
            )

        post = result["post"]
        buffer_post = BufferPost(
            id=post["id"],
            due_at=self._parse_datetime(post.get("dueAt")),
            asset_urls=[
                a["source"] for a in (post.get("assets") or []) if a.get("source")
            ],
        )
        logger.info(
            f"Buffer post queued: id={buffer_post.id} due_at={buffer_post.due_at} "
            f"assets={len(buffer_post.asset_urls)}"
        )
        return buffer_post

    def delete_post(self, post_id: str) -> bool:
        """
        キューから投稿を削除する（検証スクリプトの後片付け用）

        Returns:
            削除成功の可否
        """
        data = self._graphql(_DELETE_POST_MUTATION, {"input": {"id": post_id}})
        result = data.get("deletePost") or {}
        typename = result.get("__typename")
        if typename != "DeletePostSuccess":
            logger.error(f"Buffer deletePost failed: {typename}: {result.get('message')}")
            return False
        logger.info(f"Buffer post deleted: id={post_id}")
        return True

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        """ISO 8601 文字列を datetime に変換（"Z" 表記対応）"""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(f"Unparseable dueAt from Buffer: {value}")
            return None
