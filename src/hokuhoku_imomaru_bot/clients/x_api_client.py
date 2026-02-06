"""
XAPIClientクラス

X (Twitter) APIとの通信を管理します。
OAuth 1.0a (v1.1用) と Bearer Token (v2用) の両方をサポート。
"""
import json
import logging
import hashlib
import hmac
import time
import urllib.parse
import base64
import secrets
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class XAPICredentials:
    """X API認証情報"""
    api_key: str
    api_key_secret: str
    access_token: str
    access_token_secret: str
    bearer_token: str


class XAPIClient:
    """
    X (Twitter) APIクライアント
    
    OAuth 1.0a認証（v1.1用）とBearer Token認証（v2用）をサポート。
    認証情報はSecrets Managerから取得。
    """
    
    # APIエンドポイント
    API_V1_BASE = "https://api.twitter.com/1.1"
    API_V2_BASE = "https://api.twitter.com/2"
    
    def __init__(
        self,
        secrets_client,
        secret_name: str = "imomaru-bot/x-api-credentials",
    ):
        """
        XAPIClientを初期化
        
        Args:
            secrets_client: boto3 Secrets Managerクライアント
            secret_name: シークレット名
        """
        self._secrets_client = secrets_client
        self._secret_name = secret_name
        self._credentials: Optional[XAPICredentials] = None
    
    def _load_credentials(self) -> XAPICredentials:
        """
        Secrets Managerから認証情報を取得
        
        Returns:
            XAPICredentials
        """
        if self._credentials is not None:
            return self._credentials
        
        try:
            response = self._secrets_client.get_secret_value(
                SecretId=self._secret_name
            )
            secret_data = json.loads(response["SecretString"])
            
            self._credentials = XAPICredentials(
                api_key=secret_data["api_key"],
                api_key_secret=secret_data["api_key_secret"],
                access_token=secret_data["access_token"],
                access_token_secret=secret_data["access_token_secret"],
                bearer_token=secret_data["bearer_token"],
            )
            
            # 認証情報をログに出力しない
            logger.info("X API credentials loaded successfully")
            return self._credentials
            
        except Exception as e:
            # エラーメッセージに認証情報を含めない
            logger.error("Failed to load X API credentials")
            raise
    
    def _generate_oauth_signature(
        self,
        method: str,
        url: str,
        params: Dict[str, str],
        credentials: XAPICredentials,
    ) -> str:
        """
        OAuth 1.0a署名を生成
        
        Args:
            method: HTTPメソッド
            url: リクエストURL
            params: パラメータ
            credentials: 認証情報
        
        Returns:
            署名文字列
        """
        # パラメータをソートしてエンコード
        sorted_params = sorted(params.items())
        param_string = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted_params
        )
        
        # 署名ベース文字列を作成
        signature_base = "&".join([
            method.upper(),
            urllib.parse.quote(url, safe=""),
            urllib.parse.quote(param_string, safe=""),
        ])
        
        # 署名キーを作成
        signing_key = "&".join([
            urllib.parse.quote(credentials.api_key_secret, safe=""),
            urllib.parse.quote(credentials.access_token_secret, safe=""),
        ])
        
        # HMAC-SHA1で署名
        signature = hmac.new(
            signing_key.encode("utf-8"),
            signature_base.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        
        return base64.b64encode(signature).decode("utf-8")
    
    def _build_oauth_header(
        self,
        method: str,
        url: str,
        credentials: XAPICredentials,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        OAuth 1.0a認証ヘッダーを構築
        
        Args:
            method: HTTPメソッド
            url: リクエストURL
            credentials: 認証情報
            extra_params: 追加パラメータ
        
        Returns:
            Authorizationヘッダー値
        """
        oauth_params = {
            "oauth_consumer_key": credentials.api_key,
            "oauth_nonce": secrets.token_hex(16),
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": credentials.access_token,
            "oauth_version": "1.0",
        }
        
        # 署名用パラメータ
        all_params = {**oauth_params}
        if extra_params:
            all_params.update(extra_params)
        
        # 署名を生成
        signature = self._generate_oauth_signature(
            method, url, all_params, credentials
        )
        oauth_params["oauth_signature"] = signature
        
        # ヘッダー文字列を構築
        header_parts = [
            f'{k}="{urllib.parse.quote(str(v), safe="")}"'
            for k, v in sorted(oauth_params.items())
        ]
        return "OAuth " + ", ".join(header_parts)
    
    def request_v1(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        X API v1.1にリクエスト（OAuth 1.0a認証）
        
        Args:
            method: HTTPメソッド
            endpoint: エンドポイント（例: "/account/update_profile_image.json"）
            params: クエリパラメータ
            data: POSTデータ
            files: ファイルデータ
        
        Returns:
            APIレスポンス
        """
        credentials = self._load_credentials()
        url = f"{self.API_V1_BASE}{endpoint}"
        
        # OAuth認証ヘッダーを構築
        auth_header = self._build_oauth_header(
            method, url, credentials, params
        )
        
        headers = {
            "Authorization": auth_header,
        }
        
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            files=files,
            timeout=30,
        )
        
        # エラーハンドリング
        if not response.ok:
            logger.error(f"X API v1.1 error: {response.status_code}")
            response.raise_for_status()
        
        return response.json() if response.text else {}
    
    def request_v2(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        use_oauth: bool = False,
    ) -> Dict[str, Any]:
        """
        X API v2にリクエスト
        
        Args:
            method: HTTPメソッド
            endpoint: エンドポイント（例: "/users/:id/tweets"）
            params: クエリパラメータ
            json_data: JSONデータ
            use_oauth: OAuth 1.0a認証を使用するか（デフォルトはBearer Token）
        
        Returns:
            APIレスポンス
        """
        credentials = self._load_credentials()
        url = f"{self.API_V2_BASE}{endpoint}"
        
        if use_oauth:
            # OAuth 1.0a認証（ツイート投稿などユーザーコンテキストが必要な操作用）
            auth_header = self._build_oauth_header(method, url, credentials)
            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/json",
            }
        else:
            # Bearer Token認証（読み取り専用操作用）
            headers = {
                "Authorization": f"Bearer {credentials.bearer_token}",
                "Content-Type": "application/json",
            }
        
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_data,
            timeout=30,
        )
        
        # エラーハンドリング
        if not response.ok:
            logger.error(f"X API v2 error: {response.status_code} - {response.text}")
            response.raise_for_status()
        
        return response.json() if response.text else {}
    
    def get_user_timeline(
        self,
        user_id: str,
        since_id: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        ユーザーのタイムラインを取得（v2）
        
        Args:
            user_id: ユーザーID
            since_id: このID以降のツイートを取得
            max_results: 最大取得件数
        
        Returns:
            タイムラインデータ
        """
        params = {
            "max_results": max_results,
            "tweet.fields": "created_at,author_id,referenced_tweets,in_reply_to_user_id",
        }
        if since_id:
            params["since_id"] = since_id
        
        return self.request_v2(
            "GET",
            f"/users/{user_id}/tweets",
            params=params,
        )
    
    def post_tweet(
        self,
        text: str,
        quote_tweet_id: Optional[str] = None,
        media_ids: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        ツイートを投稿（v2 + OAuth 1.0a認証）
        
        Args:
            text: ツイート本文
            quote_tweet_id: 引用するツイートID
            media_ids: 添付するメディアIDのリスト
        
        Returns:
            投稿結果
        """
        json_data = {"text": text}
        if quote_tweet_id:
            json_data["quote_tweet_id"] = quote_tweet_id
        if media_ids:
            json_data["media"] = {"media_ids": media_ids}
        
        # ツイート投稿にはOAuth 1.0a認証が必要
        return self.request_v2("POST", "/tweets", json_data=json_data, use_oauth=True)
    
    def update_profile_image(self, image_base64: str) -> Dict[str, Any]:
        """
        プロフィール画像を更新（v1.1）
        
        Args:
            image_base64: Base64エンコードされた画像データ
        
        Returns:
            更新結果
        """
        return self.request_v1(
            "POST",
            "/account/update_profile_image.json",
            data={"image": image_base64},
        )
    
    def update_profile(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        プロフィールを更新（v1.1）
        
        Args:
            name: 表示名
            description: 自己紹介
        
        Returns:
            更新結果
        """
        data = {}
        if name:
            data["name"] = name
        if description:
            data["description"] = description
        
        return self.request_v1(
            "POST",
            "/account/update_profile.json",
            data=data,
        )
    
    def get_my_tweets_with_metrics(
        self,
        bot_user_id: str,
        max_results: int = 100,
    ) -> Dict[str, Any]:
        """
        ボットの投稿とエンゲージメント情報を取得（v2）
        
        Args:
            bot_user_id: ボットのユーザーID
            max_results: 最大取得件数（最大100）
        
        Returns:
            投稿データ（いいね数、リポスト数を含む）
        """
        params = {
            "max_results": min(max_results, 100),
            "tweet.fields": "public_metrics,created_at",
        }
        
        return self.request_v2(
            "GET",
            f"/users/{bot_user_id}/tweets",
            params=params,
        )
    
    def upload_media(self, image_data: bytes) -> Optional[str]:
        """
        画像をアップロードしてmedia_idを取得（v1.1）
        
        Args:
            image_data: 画像のバイナリデータ
        
        Returns:
            media_id文字列（失敗時はNone）
        """
        try:
            # Base64エンコード
            image_base64 = base64.b64encode(image_data).decode("utf-8")
            
            credentials = self._load_credentials()
            url = "https://upload.twitter.com/1.1/media/upload.json"
            
            # OAuth認証ヘッダーを構築
            auth_header = self._build_oauth_header("POST", url, credentials)
            
            headers = {
                "Authorization": auth_header,
            }
            
            response = requests.post(
                url=url,
                headers=headers,
                data={"media_data": image_base64},
                timeout=60,
            )
            
            if not response.ok:
                logger.error(f"Media upload error: {response.status_code}")
                response.raise_for_status()
            
            result = response.json()
            media_id = result.get("media_id_string")
            
            if media_id:
                logger.info(f"Media uploaded successfully: {media_id}")
                return media_id
            else:
                logger.error("Media upload response missing media_id_string")
                return None
                
        except Exception as e:
            logger.error(f"Failed to upload media: {e}")
            return None
