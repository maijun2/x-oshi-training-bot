"""
TimelineMonitorクラスのプロパティベーステスト

Property 1: 投稿タイプの正確な分類
Property 3: since_idによるタイムラインフィルタリング
"""
import pytest
from unittest.mock import Mock
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.hokuhoku_imomaru_bot.services.timeline_monitor import (
    TimelineMonitor,
    Tweet,
)


# 定数
OSHI_USER_ID = "oshi_user_123"
GROUP_USER_ID = "group_user_456"

# ユーザーIDのストラテジー
user_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=20,
)


def create_monitor(mock_api_client=None):
    """TimelineMonitorインスタンスを作成"""
    if mock_api_client is None:
        mock_api_client = Mock()
    return TimelineMonitor(
        api_client=mock_api_client,
        oshi_user_id=OSHI_USER_ID,
        group_user_id=GROUP_USER_ID,
    )


class TestPostClassificationProperty:
    """
    Property 1: 投稿タイプの正確な分類
    
    任意の投稿に対して、author_idが推しのIDと一致する場合は「oshi」として分類され、
    グループのIDと一致する場合は「group」として分類され、
    それ以外の場合は分類されないべきである
    
    **Validates: Requirements 1.2**
    """
    
    @settings(max_examples=100)
    @given(
        tweet_id=st.text(min_size=1, max_size=20),
        tweet_text=st.text(max_size=280),
    )
    def test_oshi_post_classified_as_oshi(
        self,
        tweet_id,
        tweet_text,
    ):
        """
        Feature: hokuhoku-imomaru-bot, Property 1: 投稿タイプの正確な分類
        
        推しのユーザーIDを持つ純粋な投稿は「oshi」として分類されるべき
        """
        monitor = create_monitor()
        tweet = Tweet(
            id=tweet_id,
            text=tweet_text,
            author_id=OSHI_USER_ID,
            is_quote_tweet=False,
            is_reply=False,
        )
        
        classification = monitor.classify_tweet(tweet)
        
        assert classification == "oshi"
    
    @settings(max_examples=100)
    @given(
        tweet_id=st.text(min_size=1, max_size=20),
        tweet_text=st.text(max_size=280),
    )
    def test_group_post_classified_as_group(
        self,
        tweet_id,
        tweet_text,
    ):
        """
        Feature: hokuhoku-imomaru-bot, Property 1: 投稿タイプの正確な分類
        
        グループのユーザーIDを持つ純粋な投稿は「group」として分類されるべき
        """
        monitor = create_monitor()
        tweet = Tweet(
            id=tweet_id,
            text=tweet_text,
            author_id=GROUP_USER_ID,
            is_quote_tweet=False,
            is_reply=False,
        )
        
        classification = monitor.classify_tweet(tweet)
        
        assert classification == "group"
    
    @settings(max_examples=100)
    @given(
        tweet_id=st.text(min_size=1, max_size=20),
        tweet_text=st.text(max_size=280),
        author_id=user_id_strategy,
    )
    def test_other_post_not_classified(
        self,
        tweet_id,
        tweet_text,
        author_id,
    ):
        """
        Feature: hokuhoku-imomaru-bot, Property 1: 投稿タイプの正確な分類
        
        推しでもグループでもないユーザーの投稿は分類されないべき
        """
        # 推しでもグループでもないユーザーIDを使用
        assume(author_id != OSHI_USER_ID)
        assume(author_id != GROUP_USER_ID)
        
        monitor = create_monitor()
        tweet = Tweet(
            id=tweet_id,
            text=tweet_text,
            author_id=author_id,
            is_quote_tweet=False,
            is_reply=False,
        )
        
        classification = monitor.classify_tweet(tweet)
        
        assert classification is None
    
    @settings(max_examples=100)
    @given(
        tweet_id=st.text(min_size=1, max_size=20),
        tweet_text=st.text(max_size=280),
        is_quote=st.booleans(),
        is_reply=st.booleans(),
    )
    def test_oshi_non_original_post_not_classified(
        self,
        tweet_id,
        tweet_text,
        is_quote,
        is_reply,
    ):
        """
        Feature: hokuhoku-imomaru-bot, Property 1: 投稿タイプの正確な分類
        
        推しのリプライは分類されないべき（引用リポストは分類される）
        """
        # リプライの場合のみテスト（引用リポストは採点対象）
        assume(is_reply)
        
        monitor = create_monitor()
        tweet = Tweet(
            id=tweet_id,
            text=tweet_text,
            author_id=OSHI_USER_ID,
            is_quote_tweet=is_quote,
            is_reply=is_reply,
        )
        
        classification = monitor.classify_tweet(tweet)
        
        assert classification is None
    
    @settings(max_examples=100)
    @given(
        tweet_id=st.text(min_size=1, max_size=20),
        tweet_text=st.text(max_size=280),
        is_quote=st.booleans(),
        is_reply=st.booleans(),
    )
    def test_group_non_original_post_not_classified(
        self,
        tweet_id,
        tweet_text,
        is_quote,
        is_reply,
    ):
        """
        Feature: hokuhoku-imomaru-bot, Property 1: 投稿タイプの正確な分類
        
        グループのリプライは分類されないべき（引用リポストは分類される）
        """
        # リプライの場合のみテスト（引用リポストは採点対象）
        assume(is_reply)
        
        monitor = create_monitor()
        tweet = Tweet(
            id=tweet_id,
            text=tweet_text,
            author_id=GROUP_USER_ID,
            is_quote_tweet=is_quote,
            is_reply=is_reply,
        )
        
        classification = monitor.classify_tweet(tweet)
        
        assert classification is None
    
    @settings(max_examples=100)
    @given(
        tweet_id=st.text(min_size=1, max_size=20),
        tweet_text=st.text(max_size=280),
    )
    def test_oshi_quote_tweet_classified_as_oshi(
        self,
        tweet_id,
        tweet_text,
    ):
        """
        Feature: hokuhoku-imomaru-bot, Property 1: 投稿タイプの正確な分類
        
        推しの引用リポストは「oshi」として分類されるべき
        """
        monitor = create_monitor()
        tweet = Tweet(
            id=tweet_id,
            text=tweet_text,
            author_id=OSHI_USER_ID,
            is_quote_tweet=True,
            is_reply=False,
        )
        
        classification = monitor.classify_tweet(tweet)
        
        assert classification == "oshi"
    
    @settings(max_examples=100)
    @given(
        tweet_id=st.text(min_size=1, max_size=20),
        tweet_text=st.text(max_size=280),
    )
    def test_group_quote_tweet_classified_as_group(
        self,
        tweet_id,
        tweet_text,
    ):
        """
        Feature: hokuhoku-imomaru-bot, Property 1: 投稿タイプの正確な分類
        
        グループの引用リポストは「group」として分類されるべき
        """
        monitor = create_monitor()
        tweet = Tweet(
            id=tweet_id,
            text=tweet_text,
            author_id=GROUP_USER_ID,
            is_quote_tweet=True,
            is_reply=False,
        )
        
        classification = monitor.classify_tweet(tweet)
        
        assert classification == "group"


class TestTimelineFilteringProperty:
    """
    Property 3: since_idによるタイムラインフィルタリング
    
    任意のTweet IDとタイムラインデータに対して、since_idを指定してタイムラインをチェックすると、
    そのID以降の投稿のみが返されるべきである
    
    **Validates: Requirements 1.4, 11.5**
    """
    
    @settings(max_examples=100)
    @given(
        since_id=st.text(min_size=1, max_size=20),
        user_id=user_id_strategy,
        max_results=st.integers(min_value=1, max_value=100),
    )
    def test_since_id_passed_to_api(
        self,
        since_id,
        user_id,
        max_results,
    ):
        """
        Feature: hokuhoku-imomaru-bot, Property 3: since_idによるタイムラインフィルタリング
        
        since_idが指定された場合、APIクライアントに正しく渡されるべき
        """
        mock_api_client = Mock()
        mock_api_client.get_user_timeline.return_value = {"data": []}
        monitor = create_monitor(mock_api_client)
        
        monitor.check_timeline(
            user_id=user_id,
            since_tweet_id=since_id,
            max_results=max_results,
        )
        
        mock_api_client.get_user_timeline.assert_called_once_with(
            user_id=user_id,
            since_id=since_id,
            max_results=max_results,
        )
    
    @settings(max_examples=100)
    @given(
        user_id=user_id_strategy,
        max_results=st.integers(min_value=1, max_value=100),
    )
    def test_none_since_id_passed_to_api(
        self,
        user_id,
        max_results,
    ):
        """
        Feature: hokuhoku-imomaru-bot, Property 3: since_idによるタイムラインフィルタリング
        
        since_idがNoneの場合、APIクライアントにNoneが渡されるべき
        """
        mock_api_client = Mock()
        mock_api_client.get_user_timeline.return_value = {"data": []}
        monitor = create_monitor(mock_api_client)
        
        monitor.check_timeline(
            user_id=user_id,
            since_tweet_id=None,
            max_results=max_results,
        )
        
        mock_api_client.get_user_timeline.assert_called_once_with(
            user_id=user_id,
            since_id=None,
            max_results=max_results,
        )
    
    @settings(max_examples=50)
    @given(
        tweet_ids=st.lists(
            st.text(min_size=1, max_size=20),
            min_size=0,
            max_size=10,
        ),
    )
    def test_all_returned_tweets_are_parsed(
        self,
        tweet_ids,
    ):
        """
        Feature: hokuhoku-imomaru-bot, Property 3: since_idによるタイムラインフィルタリング
        
        APIから返されたすべてのツイートが正しくパースされるべき
        """
        mock_api_client = Mock()
        # APIレスポンスを構築
        api_response = {
            "data": [
                {"id": tid, "text": f"Tweet {tid}", "author_id": "user123"}
                for tid in tweet_ids
            ]
        }
        mock_api_client.get_user_timeline.return_value = api_response
        monitor = create_monitor(mock_api_client)
        
        tweets = monitor.check_timeline("user123")
        
        assert len(tweets) == len(tweet_ids)
        for i, tweet in enumerate(tweets):
            assert tweet.id == tweet_ids[i]
