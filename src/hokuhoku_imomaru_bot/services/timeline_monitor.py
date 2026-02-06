"""
TimelineMonitorクラス

X API v2を使用してタイムラインを監視し、新しい投稿を検出します。
"""
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Tweet:
    """
    ツイートを表すデータクラス
    
    Attributes:
        id: ツイートID
        text: ツイート本文
        author_id: 投稿者のユーザーID
        created_at: 作成日時
        is_quote_tweet: 引用リポストかどうか
        is_reply: リプライかどうか
        is_retweet: リツイート（リポスト）かどうか
        referenced_tweet_id: 参照しているツイートID（引用・リプライの場合）
    """
    id: str
    text: str
    author_id: str
    created_at: Optional[str] = None
    is_quote_tweet: bool = False
    is_reply: bool = False
    is_retweet: bool = False
    referenced_tweet_id: Optional[str] = None

    @classmethod
    def from_api_response(cls, data: dict) -> "Tweet":
        """
        X API v2のレスポンスからTweetを生成
        
        Args:
            data: APIレスポンスのツイートデータ
        
        Returns:
            Tweetインスタンス
        """
        is_quote_tweet = False
        is_reply = False
        is_retweet = False
        referenced_tweet_id = None
        
        # referenced_tweetsをチェック
        referenced_tweets = data.get("referenced_tweets", [])
        for ref in referenced_tweets:
            ref_type = ref.get("type")
            if ref_type == "quoted":
                is_quote_tweet = True
                referenced_tweet_id = ref.get("id")
            elif ref_type == "replied_to":
                is_reply = True
                referenced_tweet_id = ref.get("id")
            elif ref_type == "retweeted":
                is_retweet = True
                referenced_tweet_id = ref.get("id")
        
        return cls(
            id=data.get("id", ""),
            text=data.get("text", ""),
            author_id=data.get("author_id", ""),
            created_at=data.get("created_at"),
            is_quote_tweet=is_quote_tweet,
            is_reply=is_reply,
            is_retweet=is_retweet,
            referenced_tweet_id=referenced_tweet_id,
        )


class TimelineMonitor:
    """
    X API v2を使用してタイムラインを監視するクラス
    
    推しアイドル（@juri_bigangel）とグループ（@big_angel5）の
    純粋な投稿（引用リポスト・リプライ除外）を検出します。
    """
    
    def __init__(
        self,
        api_client,
        oshi_user_id: str,
        group_user_id: str,
    ):
        """
        TimelineMonitorを初期化
        
        Args:
            api_client: XAPIClientインスタンス
            oshi_user_id: 推しのユーザーID
            group_user_id: グループのユーザーID
        """
        self.api_client = api_client
        self.oshi_user_id = oshi_user_id
        self.group_user_id = group_user_id
    
    def check_timeline(
        self,
        user_id: str,
        since_tweet_id: Optional[str] = None,
        max_results: int = 10,
    ) -> List[Tweet]:
        """
        指定ユーザーのタイムラインをチェックして新しい投稿を取得
        
        Args:
            user_id: チェックするユーザーID
            since_tweet_id: 前回チェックした最新のTweet ID
            max_results: 最大取得件数
        
        Returns:
            新しい投稿のリスト
        """
        try:
            response = self.api_client.get_user_timeline(
                user_id=user_id,
                since_id=since_tweet_id,
                max_results=max_results,
            )
            
            tweets = []
            data = response.get("data", [])
            
            for tweet_data in data:
                tweet = Tweet.from_api_response(tweet_data)
                tweets.append(tweet)
            
            logger.info(f"Retrieved {len(tweets)} tweets from user {user_id}")
            return tweets
            
        except Exception as e:
            logger.error(f"Failed to check timeline for user {user_id}: {e}")
            raise
    
    def check_oshi_timeline(
        self,
        since_tweet_id: Optional[str] = None,
        max_results: int = 10,
    ) -> List[Tweet]:
        """
        推しのタイムラインをチェック
        
        Args:
            since_tweet_id: 前回チェックした最新のTweet ID
            max_results: 最大取得件数
        
        Returns:
            新しい投稿のリスト
        """
        return self.check_timeline(
            user_id=self.oshi_user_id,
            since_tweet_id=since_tweet_id,
            max_results=max_results,
        )
    
    def check_group_timeline(
        self,
        since_tweet_id: Optional[str] = None,
        max_results: int = 10,
    ) -> List[Tweet]:
        """
        グループのタイムラインをチェック
        
        Args:
            since_tweet_id: 前回チェックした最新のTweet ID
            max_results: 最大取得件数
        
        Returns:
            新しい投稿のリスト
        """
        return self.check_timeline(
            user_id=self.group_user_id,
            since_tweet_id=since_tweet_id,
            max_results=max_results,
        )
    
    def is_oshi_post(self, tweet: Tweet) -> bool:
        """
        推しの投稿かどうかを判定
        オリジナル投稿と引用リポストを含む（リプライは除外）
        
        Args:
            tweet: 判定するツイート
        
        Returns:
            推しの投稿の場合True
        """
        return (
            tweet.author_id == self.oshi_user_id
            and not tweet.is_reply
            and not tweet.is_retweet
        )
    
    def is_group_post(self, tweet: Tweet) -> bool:
        """
        グループの投稿かどうかを判定
        オリジナル投稿と引用リポストを含む（リプライは除外）
        
        Args:
            tweet: 判定するツイート
        
        Returns:
            グループの投稿の場合True
        """
        return (
            tweet.author_id == self.group_user_id
            and not tweet.is_reply
            and not tweet.is_retweet
        )
    
    def classify_tweet(self, tweet: Tweet) -> Optional[str]:
        """
        ツイートを分類
        
        Args:
            tweet: 分類するツイート
        
        Returns:
            "oshi", "group", またはNone（分類不可の場合）
        """
        if self.is_oshi_post(tweet):
            return "oshi"
        elif self.is_group_post(tweet):
            return "group"
        return None
    
    def filter_original_posts(self, tweets: List[Tweet]) -> List[Tweet]:
        """
        オリジナル投稿と引用リポスト（リプライ・リツイート除外）をフィルタリング
        
        Args:
            tweets: フィルタリングするツイートリスト
        
        Returns:
            オリジナル投稿と引用リポストのリスト
        """
        return [
            tweet for tweet in tweets
            if not tweet.is_reply and not tweet.is_retweet
        ]
    
    def filter_retweets(self, tweets: List[Tweet]) -> List[Tweet]:
        """
        リツイート（リポスト）のみをフィルタリング
        
        Args:
            tweets: フィルタリングするツイートリスト
        
        Returns:
            リツイートのみのリスト
        """
        return [tweet for tweet in tweets if tweet.is_retweet]
