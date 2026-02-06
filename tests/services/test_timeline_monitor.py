"""
TimelineMonitorクラスのユニットテスト
"""
import pytest
from unittest.mock import Mock, MagicMock

from src.hokuhoku_imomaru_bot.services.timeline_monitor import (
    TimelineMonitor,
    Tweet,
)


class TestTweet:
    """Tweetデータクラスのテスト"""
    
    def test_from_api_response_basic(self):
        """基本的なツイートデータからTweetを生成"""
        data = {
            "id": "123456789",
            "text": "テスト投稿です",
            "author_id": "user123",
            "created_at": "2024-01-01T12:00:00Z",
        }
        
        tweet = Tweet.from_api_response(data)
        
        assert tweet.id == "123456789"
        assert tweet.text == "テスト投稿です"
        assert tweet.author_id == "user123"
        assert tweet.created_at == "2024-01-01T12:00:00Z"
        assert tweet.is_quote_tweet is False
        assert tweet.is_reply is False
        assert tweet.referenced_tweet_id is None
    
    def test_from_api_response_quote_tweet(self):
        """引用リポストのデータからTweetを生成"""
        data = {
            "id": "123456789",
            "text": "引用リポストです",
            "author_id": "user123",
            "referenced_tweets": [
                {"type": "quoted", "id": "original123"}
            ],
        }
        
        tweet = Tweet.from_api_response(data)
        
        assert tweet.is_quote_tweet is True
        assert tweet.is_reply is False
        assert tweet.referenced_tweet_id == "original123"
    
    def test_from_api_response_reply(self):
        """リプライのデータからTweetを生成"""
        data = {
            "id": "123456789",
            "text": "リプライです",
            "author_id": "user123",
            "referenced_tweets": [
                {"type": "replied_to", "id": "original123"}
            ],
        }
        
        tweet = Tweet.from_api_response(data)
        
        assert tweet.is_quote_tweet is False
        assert tweet.is_reply is True
        assert tweet.referenced_tweet_id == "original123"
    
    def test_from_api_response_empty_data(self):
        """空のデータからTweetを生成"""
        data = {}
        
        tweet = Tweet.from_api_response(data)
        
        assert tweet.id == ""
        assert tweet.text == ""
        assert tweet.author_id == ""
        assert tweet.is_quote_tweet is False
        assert tweet.is_reply is False


class TestTimelineMonitor:
    """TimelineMonitorクラスのテスト"""
    
    @pytest.fixture
    def mock_api_client(self):
        """モックAPIクライアント"""
        return Mock()
    
    @pytest.fixture
    def monitor(self, mock_api_client):
        """TimelineMonitorインスタンス"""
        return TimelineMonitor(
            api_client=mock_api_client,
            oshi_user_id="oshi_user_123",
            group_user_id="group_user_456",
        )
    
    def test_check_timeline_success(self, monitor, mock_api_client):
        """タイムラインチェック成功"""
        mock_api_client.get_user_timeline.return_value = {
            "data": [
                {"id": "1", "text": "投稿1", "author_id": "user1"},
                {"id": "2", "text": "投稿2", "author_id": "user2"},
            ]
        }
        
        tweets = monitor.check_timeline("user123")
        
        assert len(tweets) == 2
        assert tweets[0].id == "1"
        assert tweets[1].id == "2"
        mock_api_client.get_user_timeline.assert_called_once_with(
            user_id="user123",
            since_id=None,
            max_results=10,
        )
    
    def test_check_timeline_with_since_id(self, monitor, mock_api_client):
        """since_id指定でタイムラインチェック"""
        mock_api_client.get_user_timeline.return_value = {"data": []}
        
        monitor.check_timeline("user123", since_tweet_id="last_tweet_id")
        
        mock_api_client.get_user_timeline.assert_called_once_with(
            user_id="user123",
            since_id="last_tweet_id",
            max_results=10,
        )
    
    def test_check_timeline_empty_response(self, monitor, mock_api_client):
        """空のレスポンス"""
        mock_api_client.get_user_timeline.return_value = {}
        
        tweets = monitor.check_timeline("user123")
        
        assert len(tweets) == 0
    
    def test_check_oshi_timeline(self, monitor, mock_api_client):
        """推しのタイムラインチェック"""
        mock_api_client.get_user_timeline.return_value = {"data": []}
        
        monitor.check_oshi_timeline(since_tweet_id="last_id")
        
        mock_api_client.get_user_timeline.assert_called_once_with(
            user_id="oshi_user_123",
            since_id="last_id",
            max_results=10,
        )
    
    def test_check_group_timeline(self, monitor, mock_api_client):
        """グループのタイムラインチェック"""
        mock_api_client.get_user_timeline.return_value = {"data": []}
        
        monitor.check_group_timeline(since_tweet_id="last_id")
        
        mock_api_client.get_user_timeline.assert_called_once_with(
            user_id="group_user_456",
            since_id="last_id",
            max_results=10,
        )
    
    def test_is_oshi_post_true(self, monitor):
        """推しの純粋な投稿を正しく判定"""
        tweet = Tweet(
            id="1",
            text="推しの投稿",
            author_id="oshi_user_123",
            is_quote_tweet=False,
            is_reply=False,
        )
        
        assert monitor.is_oshi_post(tweet) is True
    
    def test_is_oshi_post_false_wrong_author(self, monitor):
        """別のユーザーの投稿は推しの投稿ではない"""
        tweet = Tweet(
            id="1",
            text="別のユーザーの投稿",
            author_id="other_user",
            is_quote_tweet=False,
            is_reply=False,
        )
        
        assert monitor.is_oshi_post(tweet) is False
    
    def test_is_oshi_post_false_quote_tweet(self, monitor):
        """推しの引用リポストも投稿として判定される"""
        tweet = Tweet(
            id="1",
            text="推しの引用リポスト",
            author_id="oshi_user_123",
            is_quote_tweet=True,
            is_reply=False,
        )
        
        assert monitor.is_oshi_post(tweet) is True
    
    def test_is_oshi_post_false_reply(self, monitor):
        """推しのリプライは純粋な投稿ではない"""
        tweet = Tweet(
            id="1",
            text="推しのリプライ",
            author_id="oshi_user_123",
            is_quote_tweet=False,
            is_reply=True,
        )
        
        assert monitor.is_oshi_post(tweet) is False
    
    def test_is_group_post_true(self, monitor):
        """グループの純粋な投稿を正しく判定"""
        tweet = Tweet(
            id="1",
            text="グループの投稿",
            author_id="group_user_456",
            is_quote_tweet=False,
            is_reply=False,
        )
        
        assert monitor.is_group_post(tweet) is True
    
    def test_is_group_post_false_wrong_author(self, monitor):
        """別のユーザーの投稿はグループの投稿ではない"""
        tweet = Tweet(
            id="1",
            text="別のユーザーの投稿",
            author_id="other_user",
            is_quote_tweet=False,
            is_reply=False,
        )
        
        assert monitor.is_group_post(tweet) is False
    
    def test_is_group_post_false_quote_tweet(self, monitor):
        """グループの引用リポストも投稿として判定される"""
        tweet = Tweet(
            id="1",
            text="グループの引用リポスト",
            author_id="group_user_456",
            is_quote_tweet=True,
            is_reply=False,
        )
        
        assert monitor.is_group_post(tweet) is True
    
    def test_classify_tweet_oshi(self, monitor):
        """推しの投稿を正しく分類"""
        tweet = Tweet(
            id="1",
            text="推しの投稿",
            author_id="oshi_user_123",
            is_quote_tweet=False,
            is_reply=False,
        )
        
        assert monitor.classify_tweet(tweet) == "oshi"
    
    def test_classify_tweet_group(self, monitor):
        """グループの投稿を正しく分類"""
        tweet = Tweet(
            id="1",
            text="グループの投稿",
            author_id="group_user_456",
            is_quote_tweet=False,
            is_reply=False,
        )
        
        assert monitor.classify_tweet(tweet) == "group"
    
    def test_classify_tweet_none(self, monitor):
        """分類不可の投稿"""
        tweet = Tweet(
            id="1",
            text="他のユーザーの投稿",
            author_id="other_user",
            is_quote_tweet=False,
            is_reply=False,
        )
        
        assert monitor.classify_tweet(tweet) is None
    
    def test_classify_tweet_oshi_quote_returns_oshi(self, monitor):
        """推しの引用リポストはoshiとして分類される"""
        tweet = Tweet(
            id="1",
            text="推しの引用リポスト",
            author_id="oshi_user_123",
            is_quote_tweet=True,
            is_reply=False,
        )
        
        assert monitor.classify_tweet(tweet) == "oshi"
    
    def test_filter_original_posts(self, monitor):
        """オリジナル投稿と引用リポストをフィルタリング（リプライ・リツイート除外）"""
        tweets = [
            Tweet(id="1", text="純粋な投稿", author_id="user1", is_quote_tweet=False, is_reply=False),
            Tweet(id="2", text="引用リポスト", author_id="user2", is_quote_tweet=True, is_reply=False),
            Tweet(id="3", text="リプライ", author_id="user3", is_quote_tweet=False, is_reply=True),
            Tweet(id="4", text="純粋な投稿2", author_id="user4", is_quote_tweet=False, is_reply=False),
            Tweet(id="5", text="リツイート", author_id="user5", is_quote_tweet=False, is_reply=False, is_retweet=True),
        ]
        
        filtered = monitor.filter_original_posts(tweets)
        
        # 純粋な投稿(1, 4)と引用リポスト(2)が含まれる、リプライ(3)とリツイート(5)は除外
        assert len(filtered) == 3
        assert filtered[0].id == "1"
        assert filtered[1].id == "2"
        assert filtered[2].id == "4"
    
    def test_check_timeline_api_error(self, monitor, mock_api_client):
        """APIエラー時の例外処理"""
        mock_api_client.get_user_timeline.side_effect = Exception("API Error")
        
        with pytest.raises(Exception, match="API Error"):
            monitor.check_timeline("user123")
