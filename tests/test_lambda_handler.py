"""
Lambda関数の統合テスト
"""
import json
import os
import pytest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock, patch, PropertyMock

from moto import mock_aws

from src.hokuhoku_imomaru_bot.lambda_handler import (
    lambda_handler,
    _process_bot_logic,
    _check_timeline_safe,
    _post_quote_safe,
    _update_profile_on_level_up,
)
from src.hokuhoku_imomaru_bot.models import BotState
from src.hokuhoku_imomaru_bot.services import (
    StateStore,
    TimelineMonitor,
    Tweet,
    XPCalculator,
    LevelManager,
    AIGenerator,
    ImageCompositor,
    ProfileUpdater,
    DailyReporter,
)


class TestProcessBotLogic:
    """_process_bot_logic関数のテスト"""
    
    def test_no_new_posts(self):
        """新しい投稿がない場合のテスト"""
        # モックの設定
        state = BotState()
        state_store = MagicMock(spec=StateStore)
        state_store.reset_daily_counts.return_value = state
        
        timeline_monitor = MagicMock(spec=TimelineMonitor)
        timeline_monitor.check_oshi_timeline.return_value = []
        timeline_monitor.check_group_timeline.return_value = []
        timeline_monitor.filter_original_posts.return_value = []
        
        xp_calculator = XPCalculator()
        level_manager = MagicMock(spec=LevelManager)
        level_manager.check_level_up.return_value = (False, 1)
        
        ai_generator = MagicMock(spec=AIGenerator)
        image_compositor = MagicMock(spec=ImageCompositor)
        profile_updater = MagicMock(spec=ProfileUpdater)
        
        daily_reporter = MagicMock(spec=DailyReporter)
        daily_reporter.should_post_daily_report.return_value = False
        
        x_api_client = MagicMock()
        
        # 実行
        result = _process_bot_logic(
            state=state,
            state_store=state_store,
            timeline_monitor=timeline_monitor,
            xp_calculator=xp_calculator,
            level_manager=level_manager,
            ai_generator=ai_generator,
            image_compositor=image_compositor,
            profile_updater=profile_updater,
            daily_reporter=daily_reporter,
            x_api_client=x_api_client,
        )
        
        # 検証
        assert result["oshi_posts_detected"] == 0
        assert result["group_posts_detected"] == 0
        assert result["xp_gained"] == 0.0
        assert result["level_up"] is False
        state_store.save_state.assert_called_once()
    
    def test_oshi_post_detected(self):
        """推しの投稿が検出された場合のテスト"""
        state = BotState()
        state_store = MagicMock(spec=StateStore)
        state_store.reset_daily_counts.return_value = state
        
        oshi_tweet = Tweet(
            id="123456789",
            text="テスト投稿",
            author_id="oshi_user_id",
        )
        
        timeline_monitor = MagicMock(spec=TimelineMonitor)
        timeline_monitor.check_oshi_timeline.return_value = [oshi_tweet]
        timeline_monitor.check_group_timeline.return_value = []
        timeline_monitor.filter_original_posts.side_effect = lambda tweets: tweets
        
        xp_calculator = XPCalculator()
        level_manager = MagicMock(spec=LevelManager)
        level_manager.check_level_up.return_value = (False, 1)
        
        ai_generator = MagicMock(spec=AIGenerator)
        ai_generator.generate_response.return_value = "応答テキスト"
        
        image_compositor = MagicMock(spec=ImageCompositor)
        profile_updater = MagicMock(spec=ProfileUpdater)
        
        daily_reporter = MagicMock(spec=DailyReporter)
        daily_reporter.should_post_daily_report.return_value = False
        
        x_api_client = MagicMock()
        x_api_client.post_tweet.return_value = {"data": {"id": "999"}}
        
        result = _process_bot_logic(
            state=state,
            state_store=state_store,
            timeline_monitor=timeline_monitor,
            xp_calculator=xp_calculator,
            level_manager=level_manager,
            ai_generator=ai_generator,
            image_compositor=image_compositor,
            profile_updater=profile_updater,
            daily_reporter=daily_reporter,
            x_api_client=x_api_client,
        )
        
        assert result["oshi_posts_detected"] == 1
        assert result["xp_gained"] == 5.0
        assert result["quotes_posted"] == 1
        assert state.oshi_post_count == 1
        assert state.daily_oshi_count == 1
        assert state.cumulative_xp == 5.0
    
    def test_group_post_detected(self):
        """グループの投稿が検出された場合のテスト"""
        state = BotState()
        state_store = MagicMock(spec=StateStore)
        state_store.reset_daily_counts.return_value = state
        
        group_tweet = Tweet(
            id="987654321",
            text="グループ投稿",
            author_id="group_user_id",
        )
        
        timeline_monitor = MagicMock(spec=TimelineMonitor)
        timeline_monitor.check_oshi_timeline.return_value = []
        timeline_monitor.check_group_timeline.return_value = [group_tweet]
        timeline_monitor.filter_original_posts.side_effect = lambda tweets: tweets
        
        xp_calculator = XPCalculator()
        level_manager = MagicMock(spec=LevelManager)
        level_manager.check_level_up.return_value = (False, 1)
        
        ai_generator = MagicMock(spec=AIGenerator)
        ai_generator.generate_response.return_value = "応答テキスト"
        
        image_compositor = MagicMock(spec=ImageCompositor)
        profile_updater = MagicMock(spec=ProfileUpdater)
        
        daily_reporter = MagicMock(spec=DailyReporter)
        daily_reporter.should_post_daily_report.return_value = False
        
        x_api_client = MagicMock()
        x_api_client.post_tweet.return_value = {"data": {"id": "999"}}
        
        result = _process_bot_logic(
            state=state,
            state_store=state_store,
            timeline_monitor=timeline_monitor,
            xp_calculator=xp_calculator,
            level_manager=level_manager,
            ai_generator=ai_generator,
            image_compositor=image_compositor,
            profile_updater=profile_updater,
            daily_reporter=daily_reporter,
            x_api_client=x_api_client,
        )
        
        assert result["group_posts_detected"] == 1
        assert result["xp_gained"] == 2.0
        assert state.group_post_count == 1
        assert state.daily_group_count == 1

    
    def test_level_up(self):
        """レベルアップのテスト"""
        state = BotState(cumulative_xp=6.0, current_level=1)
        state_store = MagicMock(spec=StateStore)
        state_store.reset_daily_counts.return_value = state
        
        timeline_monitor = MagicMock(spec=TimelineMonitor)
        timeline_monitor.check_oshi_timeline.return_value = []
        timeline_monitor.check_group_timeline.return_value = []
        timeline_monitor.filter_original_posts.return_value = []
        
        xp_calculator = XPCalculator()
        level_manager = MagicMock(spec=LevelManager)
        level_manager.check_level_up.return_value = (True, 2)
        level_manager.get_xp_to_next_level.return_value = 17
        
        ai_generator = MagicMock(spec=AIGenerator)
        
        image_compositor = MagicMock(spec=ImageCompositor)
        image_compositor.composite_level_image.return_value = BytesIO(b"fake_image")
        
        profile_updater = MagicMock(spec=ProfileUpdater)
        profile_updater.update_profile_on_level_up.return_value = {
            "image": True,
            "name": True,
            "announcement": True,
        }
        
        daily_reporter = MagicMock(spec=DailyReporter)
        daily_reporter.should_post_daily_report.return_value = False
        
        x_api_client = MagicMock()
        
        result = _process_bot_logic(
            state=state,
            state_store=state_store,
            timeline_monitor=timeline_monitor,
            xp_calculator=xp_calculator,
            level_manager=level_manager,
            ai_generator=ai_generator,
            image_compositor=image_compositor,
            profile_updater=profile_updater,
            daily_reporter=daily_reporter,
            x_api_client=x_api_client,
        )
        
        assert result["level_up"] is True
        assert result["new_level"] == 2
        assert state.current_level == 2
        profile_updater.update_profile_on_level_up.assert_called_once()
    
    def test_daily_report_posted(self):
        """日報投稿のテスト"""
        state = BotState(
            daily_oshi_count=3,
            daily_group_count=2,
            daily_xp=19.0,
        )
        state_store = MagicMock(spec=StateStore)
        state_store.reset_daily_counts.return_value = BotState()
        
        timeline_monitor = MagicMock(spec=TimelineMonitor)
        timeline_monitor.check_oshi_timeline.return_value = []
        timeline_monitor.check_group_timeline.return_value = []
        timeline_monitor.filter_original_posts.return_value = []
        
        xp_calculator = XPCalculator()
        level_manager = MagicMock(spec=LevelManager)
        level_manager.check_level_up.return_value = (False, 1)
        level_manager.get_xp_to_next_level.return_value = 7
        
        ai_generator = MagicMock(spec=AIGenerator)
        image_compositor = MagicMock(spec=ImageCompositor)
        profile_updater = MagicMock(spec=ProfileUpdater)
        
        daily_reporter = MagicMock(spec=DailyReporter)
        daily_reporter.should_post_daily_report.return_value = True
        daily_reporter.post_daily_report.return_value = True
        daily_reporter.get_today_date_jst.return_value = "2024-01-15"
        
        x_api_client = MagicMock()
        
        result = _process_bot_logic(
            state=state,
            state_store=state_store,
            timeline_monitor=timeline_monitor,
            xp_calculator=xp_calculator,
            level_manager=level_manager,
            ai_generator=ai_generator,
            image_compositor=image_compositor,
            profile_updater=profile_updater,
            daily_reporter=daily_reporter,
            x_api_client=x_api_client,
        )
        
        assert result["daily_report_posted"] is True
        daily_reporter.post_daily_report.assert_called_once()
        state_store.reset_daily_counts.assert_called_once()
    
    def test_latest_tweet_id_updated(self):
        """最新Tweet IDが更新されることを確認"""
        state = BotState()
        state_store = MagicMock(spec=StateStore)
        state_store.reset_daily_counts.return_value = state
        
        tweets = [
            Tweet(id="100", text="投稿1", author_id="oshi"),
            Tweet(id="200", text="投稿2", author_id="oshi"),
            Tweet(id="150", text="投稿3", author_id="oshi"),
        ]
        
        timeline_monitor = MagicMock(spec=TimelineMonitor)
        timeline_monitor.check_oshi_timeline.return_value = tweets
        timeline_monitor.check_group_timeline.return_value = []
        timeline_monitor.filter_original_posts.side_effect = lambda t: t
        
        xp_calculator = XPCalculator()
        level_manager = MagicMock(spec=LevelManager)
        level_manager.check_level_up.return_value = (False, 1)
        
        ai_generator = MagicMock(spec=AIGenerator)
        ai_generator.generate_response.return_value = "応答"
        
        image_compositor = MagicMock(spec=ImageCompositor)
        profile_updater = MagicMock(spec=ProfileUpdater)
        
        daily_reporter = MagicMock(spec=DailyReporter)
        daily_reporter.should_post_daily_report.return_value = False
        
        x_api_client = MagicMock()
        x_api_client.post_tweet.return_value = {"data": {"id": "999"}}
        
        _process_bot_logic(
            state=state,
            state_store=state_store,
            timeline_monitor=timeline_monitor,
            xp_calculator=xp_calculator,
            level_manager=level_manager,
            ai_generator=ai_generator,
            image_compositor=image_compositor,
            profile_updater=profile_updater,
            daily_reporter=daily_reporter,
            x_api_client=x_api_client,
        )
        
        # 最大のIDが設定される
        assert state.latest_tweet_id == "200"


class TestCheckTimelineSafe:
    """_check_timeline_safe関数のテスト"""
    
    def test_returns_tweets_on_success(self):
        """成功時にツイートリストを返す"""
        tweets = [Tweet(id="1", text="test", author_id="user")]
        check_func = MagicMock(return_value=tweets)
        
        result = _check_timeline_safe(check_func, "since_id", "test")
        
        assert result == tweets
    
    def test_returns_empty_list_on_error(self):
        """エラー時に空リストを返す"""
        check_func = MagicMock(side_effect=Exception("API Error"))
        
        result = _check_timeline_safe(check_func, "since_id", "test")
        
        assert result == []


class TestPostQuoteSafe:
    """_post_quote_safe関数のテスト"""
    
    def test_posts_quote_successfully(self):
        """引用ポストが成功する場合"""
        tweet = Tweet(id="123", text="元の投稿", author_id="user")
        ai_generator = MagicMock(spec=AIGenerator)
        ai_generator.generate_response.return_value = "応答テキスト"
        x_api_client = MagicMock()
        x_api_client.post_tweet.return_value = {"data": {"id": "999"}}
        
        result = _post_quote_safe(tweet, "oshi", ai_generator, x_api_client)
        
        assert result is True
        ai_generator.generate_response.assert_called_once_with(
            post_content="元の投稿",
            post_type="oshi",
        )
        x_api_client.post_tweet.assert_called_once_with(
            text="応答テキスト",
            quote_tweet_id="123",
        )
    
    def test_returns_false_on_error(self):
        """エラー時にFalseを返す"""
        tweet = Tweet(id="123", text="元の投稿", author_id="user")
        ai_generator = MagicMock(spec=AIGenerator)
        ai_generator.generate_response.side_effect = Exception("API Error")
        x_api_client = MagicMock()
        
        result = _post_quote_safe(tweet, "oshi", ai_generator, x_api_client)
        
        assert result is False


class TestUpdateProfileOnLevelUp:
    """_update_profile_on_level_up関数のテスト"""
    
    def test_updates_profile_successfully(self):
        """プロフィール更新が成功する場合"""
        state = BotState(
            current_level=5,
            cumulative_xp=100.0,
            oshi_post_count=10,
            group_post_count=5,
        )
        
        level_manager = MagicMock(spec=LevelManager)
        level_manager.get_xp_to_next_level.return_value = 50
        
        xp_calculator = XPCalculator()
        
        image_compositor = MagicMock(spec=ImageCompositor)
        image_compositor.composite_level_image.return_value = BytesIO(b"image")
        
        profile_updater = MagicMock(spec=ProfileUpdater)
        profile_updater.update_profile_on_level_up.return_value = {
            "image": True,
            "name": True,
            "announcement": True,
        }
        
        # エラーなく実行される
        _update_profile_on_level_up(
            state=state,
            level_manager=level_manager,
            xp_calculator=xp_calculator,
            image_compositor=image_compositor,
            profile_updater=profile_updater,
        )
        
        profile_updater.update_profile_on_level_up.assert_called_once()
    
    def test_handles_image_composition_error(self):
        """画像合成エラー時もプロフィール更新を試みる"""
        state = BotState(current_level=5, cumulative_xp=100.0)
        
        level_manager = MagicMock(spec=LevelManager)
        level_manager.get_xp_to_next_level.return_value = 50
        
        xp_calculator = XPCalculator()
        
        image_compositor = MagicMock(spec=ImageCompositor)
        image_compositor.composite_level_image.side_effect = Exception("S3 Error")
        
        profile_updater = MagicMock(spec=ProfileUpdater)
        profile_updater.update_profile_on_level_up.return_value = {
            "image": True,
            "name": True,
            "announcement": True,
        }
        
        # エラーなく実行される（フォールバックでNoneが渡される）
        _update_profile_on_level_up(
            state=state,
            level_manager=level_manager,
            xp_calculator=xp_calculator,
            image_compositor=image_compositor,
            profile_updater=profile_updater,
        )
        
        # image_dataがNoneで呼ばれる
        call_args = profile_updater.update_profile_on_level_up.call_args
        assert call_args.kwargs["image_data"] is None



class TestLambdaHandler:
    """lambda_handler関数のテスト"""
    
    @patch("src.hokuhoku_imomaru_bot.lambda_handler.boto3")
    @patch("src.hokuhoku_imomaru_bot.lambda_handler._process_bot_logic")
    def test_lambda_handler_success(self, mock_process, mock_boto3):
        """Lambda関数が正常に実行される場合"""
        mock_process.return_value = {
            "oshi_posts_detected": 1,
            "group_posts_detected": 0,
            "xp_gained": 5.0,
            "level_up": False,
            "new_level": 1,
            "daily_report_posted": False,
            "quotes_posted": 1,
        }
        
        # DynamoDBモックの設定
        mock_dynamodb = MagicMock()
        mock_dynamodb.get_item.return_value = {}
        mock_dynamodb.scan.return_value = {
            "Items": [
                {"level": {"N": "1"}, "required_xp": {"N": "0"}},
                {"level": {"N": "2"}, "required_xp": {"N": "7"}},
            ]
        }
        
        mock_boto3.client.side_effect = lambda service: {
            "dynamodb": mock_dynamodb,
            "s3": MagicMock(),
            "secretsmanager": MagicMock(),
            "bedrock-runtime": MagicMock(),
        }.get(service, MagicMock())
        
        event = {"source": "aws.events"}
        context = MagicMock()
        
        result = lambda_handler(event, context)
        
        assert result["statusCode"] == 200
        assert result["body"]["oshi_posts_detected"] == 1
    
    @patch("src.hokuhoku_imomaru_bot.lambda_handler.boto3")
    def test_lambda_handler_error(self, mock_boto3):
        """Lambda関数でエラーが発生した場合"""
        from src.hokuhoku_imomaru_bot.utils.error_handler import CriticalError
        
        mock_boto3.client.side_effect = Exception("AWS Error")
        
        event = {"source": "aws.events"}
        context = MagicMock()
        
        # CriticalErrorが発生することを確認
        with pytest.raises(CriticalError):
            lambda_handler(event, context)


class TestMultiplePostsDetection:
    """複数投稿検出のテスト"""
    
    def test_multiple_oshi_and_group_posts(self):
        """推しとグループの両方の投稿が検出された場合"""
        state = BotState()
        state_store = MagicMock(spec=StateStore)
        state_store.reset_daily_counts.return_value = state
        
        oshi_tweets = [
            Tweet(id="100", text="推し投稿1", author_id="oshi"),
            Tweet(id="101", text="推し投稿2", author_id="oshi"),
        ]
        group_tweets = [
            Tweet(id="200", text="グループ投稿1", author_id="group"),
        ]
        
        timeline_monitor = MagicMock(spec=TimelineMonitor)
        timeline_monitor.check_oshi_timeline.return_value = oshi_tweets
        timeline_monitor.check_group_timeline.return_value = group_tweets
        timeline_monitor.filter_original_posts.side_effect = lambda t: t
        
        xp_calculator = XPCalculator()
        level_manager = MagicMock(spec=LevelManager)
        level_manager.check_level_up.return_value = (False, 1)
        
        ai_generator = MagicMock(spec=AIGenerator)
        ai_generator.generate_response.return_value = "応答"
        
        image_compositor = MagicMock(spec=ImageCompositor)
        profile_updater = MagicMock(spec=ProfileUpdater)
        
        daily_reporter = MagicMock(spec=DailyReporter)
        daily_reporter.should_post_daily_report.return_value = False
        
        x_api_client = MagicMock()
        x_api_client.post_tweet.return_value = {"data": {"id": "999"}}
        
        result = _process_bot_logic(
            state=state,
            state_store=state_store,
            timeline_monitor=timeline_monitor,
            xp_calculator=xp_calculator,
            level_manager=level_manager,
            ai_generator=ai_generator,
            image_compositor=image_compositor,
            profile_updater=profile_updater,
            daily_reporter=daily_reporter,
            x_api_client=x_api_client,
        )
        
        # 推し2件 + グループ1件
        assert result["oshi_posts_detected"] == 2
        assert result["group_posts_detected"] == 1
        assert result["quotes_posted"] == 3
        # XP: 推し5.0*2 + グループ2.0*1 = 12.0
        assert result["xp_gained"] == 12.0
        assert state.oshi_post_count == 2
        assert state.group_post_count == 1
        assert state.cumulative_xp == 12.0
