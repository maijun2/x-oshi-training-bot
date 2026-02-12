"""
Lambda関数のメインハンドラー

EventBridgeからトリガーされ、ボットのメインロジックを実行します。
"""
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3

from .clients import XAPIClient
from .models import BotState
from .services import (
    StateStore,
    TweetAlreadyProcessedError,
    TimelineMonitor,
    Tweet,
    XPCalculator,
    ActivityType,
    LevelManager,
    AIGenerator,
    ImageCompositor,
    ProfileUpdater,
    DailyReporter,
)
from .utils import (
    log_event,
    EventType,
    LogLevel,
    handle_api_error,
    handle_critical_error,
    generate_response_with_fallback,
)


# 環境変数
STATE_TABLE_NAME = os.environ.get("STATE_TABLE_NAME", "imomaru-bot-state")
XP_TABLE_NAME = os.environ.get("XP_TABLE_NAME", "imomaru-bot-xp-table")
PROCESSED_TWEETS_TABLE_NAME = os.environ.get("PROCESSED_TWEETS_TABLE_NAME", "imomaru-bot-processed-tweets")
EMOTION_IMAGES_TABLE_NAME = os.environ.get("EMOTION_IMAGES_TABLE_NAME", "imomaru-bot-emotion-images")
ASSETS_BUCKET_NAME = os.environ.get("ASSETS_BUCKET_NAME", "imomaru-bot-assets")
SECRET_NAME = os.environ.get("SECRET_NAME", "imomaru-bot/x-api-credentials")
OSHI_USER_ID = os.environ.get("OSHI_USER_ID", "")
GROUP_USER_ID = os.environ.get("GROUP_USER_ID", "")
BOT_USER_ID = os.environ.get("BOT_USER_ID", "")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda関数のメインハンドラー
    
    Args:
        event: EventBridgeイベントデータ
        context: Lambda実行コンテキスト
    
    Returns:
        実行結果を含む辞書
    """
    log_event(
        level=LogLevel.INFO,
        event_type=EventType.LAMBDA_START,
        data={"event": event},
        message="Lambda execution started",
    )
    
    # 実行モードを抽出（デフォルト: daily_report）
    execution_mode = event.get("execution_mode", "daily_report")
    
    try:
        # AWSクライアントの初期化
        dynamodb_client = boto3.client("dynamodb")
        s3_client = boto3.client("s3")
        secrets_client = boto3.client("secretsmanager")
        bedrock_client = boto3.client("bedrock-runtime")
        
        # サービスの初期化
        state_store = StateStore(
            dynamodb_client=dynamodb_client,
            state_table_name=STATE_TABLE_NAME,
            xp_table_name=XP_TABLE_NAME,
            processed_tweets_table_name=PROCESSED_TWEETS_TABLE_NAME,
            emotion_images_table_name=EMOTION_IMAGES_TABLE_NAME,
        )
        
        x_api_client = XAPIClient(
            secrets_client=secrets_client,
            secret_name=SECRET_NAME,
        )
        
        timeline_monitor = TimelineMonitor(
            api_client=x_api_client,
            oshi_user_id=OSHI_USER_ID,
            group_user_id=GROUP_USER_ID,
        )
        
        xp_calculator = XPCalculator()
        
        ai_generator = AIGenerator(bedrock_client=bedrock_client)
        
        image_compositor = ImageCompositor(
            s3_client=s3_client,
            bucket_name=ASSETS_BUCKET_NAME,
        )
        
        profile_updater = ProfileUpdater(
            api_client=x_api_client,
            s3_client=s3_client,
            bucket_name=ASSETS_BUCKET_NAME,
        )
        
        daily_reporter = DailyReporter(api_client=x_api_client)
        
        # 状態の読み込み
        state = state_store.load_state()
        
        # XPテーブルの読み込み
        xp_table = state_store.load_xp_table()
        level_manager = LevelManager(xp_table=xp_table)
        
        # メイン処理を実行
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
            s3_client=s3_client,
            bucket_name=ASSETS_BUCKET_NAME,
            execution_mode=execution_mode,
        )
        
        log_event(
            level=LogLevel.INFO,
            event_type=EventType.LAMBDA_END,
            data=result,
            message="Lambda execution completed successfully",
        )
        
        return {
            "statusCode": 200,
            "body": result,
        }
        
    except Exception as e:
        handle_critical_error(e, "lambda_handler", exit_process=False)
        return {
            "statusCode": 500,
            "body": {"error": str(e)},
        }


def _process_bot_logic(
    state: BotState,
    state_store: StateStore,
    timeline_monitor: TimelineMonitor,
    xp_calculator: XPCalculator,
    level_manager: LevelManager,
    ai_generator: AIGenerator,
    image_compositor: ImageCompositor,
    profile_updater: ProfileUpdater,
    daily_reporter: DailyReporter,
    x_api_client: XAPIClient,
    s3_client = None,
    bucket_name: str = None,
    execution_mode: str = "daily_report",
) -> Dict[str, Any]:
    """
    ボットのメインロジックを実行
    
    Args:
        state: 現在のボット状態
        state_store: StateStoreインスタンス
        timeline_monitor: TimelineMonitorインスタンス
        xp_calculator: XPCalculatorインスタンス
        level_manager: LevelManagerインスタンス
        ai_generator: AIGeneratorインスタンス
        image_compositor: ImageCompositorインスタンス
        profile_updater: ProfileUpdaterインスタンス
        daily_reporter: DailyReporterインスタンス
        x_api_client: XAPIClientインスタンス
        s3_client: boto3 S3クライアント（感情画像取得用）
        bucket_name: S3バケット名
    
    Returns:
        処理結果
    """
    result = {
        "execution_mode": execution_mode,
        "oshi_posts_detected": 0,
        "group_posts_detected": 0,
        "xp_gained": 0.0,
        "level_up": False,
        "new_level": state.current_level,
        "daily_report_posted": False,
        "quotes_posted": 0,
        "new_likes": 0,
        "new_retweets": 0,
    }
    
    is_core_time = (execution_mode == "core_time")
    initial_level = state.current_level
    
    # ボット投稿へのエンゲージメントをチェック（daily_reportのみ）
    if not is_core_time:
        engagement_xp = _check_engagement_safe(
            x_api_client=x_api_client,
            xp_calculator=xp_calculator,
            state=state,
            result=result,
            bot_user_id=BOT_USER_ID,
        )
    
    # タイムラインをチェック
    log_event(
        level=LogLevel.INFO,
        event_type=EventType.TIMELINE_CHECK,
        message="Checking timelines",
    )
    
    # 推しのタイムラインをチェック
    oshi_tweets = _check_timeline_safe(
        timeline_monitor.check_oshi_timeline,
        state.latest_tweet_id,
        "oshi_timeline",
    )
    
    # グループのタイムラインをチェック（daily_reportのみ）
    if not is_core_time:
        group_tweets = _check_timeline_safe(
            timeline_monitor.check_group_timeline,
            state.latest_tweet_id,
            "group_timeline",
        )
    else:
        group_tweets = []
    
    # 純粋な投稿のみをフィルタリング
    oshi_original = timeline_monitor.filter_original_posts(oshi_tweets)
    group_original = timeline_monitor.filter_original_posts(group_tweets)
    
    # リツイート（リポスト）をフィルタリング
    oshi_retweets = timeline_monitor.filter_retweets(oshi_tweets)
    group_retweets = timeline_monitor.filter_retweets(group_tweets)
    
    # 検出された投稿を処理
    all_tweets: List[Tweet] = []
    
    for tweet in oshi_original:
        log_event(
            level=LogLevel.INFO,
            event_type=EventType.POST_DETECTED,
            data={"tweet_id": tweet.id, "type": "oshi"},
            message=f"Oshi post detected: {tweet.id}",
        )
        
        # AI応答を生成して引用ポスト（冪等性制御付き）
        posted = _post_quote_safe(
            tweet=tweet,
            post_type="oshi",
            ai_generator=ai_generator,
            x_api_client=x_api_client,
            state_store=state_store,
            state=state,
            s3_client=s3_client,
            bucket_name=bucket_name,
        )
        
        # 投稿成功時のみXPを加算（既に処理済みの場合はスキップ）
        if posted:
            result["quotes_posted"] += 1
            
            # XPを加算
            xp = xp_calculator.calculate_xp(ActivityType.OSHI_POST)
            state.cumulative_xp += xp
            state.daily_xp += xp
            state.oshi_post_count += 1
            state.daily_oshi_count += 1
            result["oshi_posts_detected"] += 1
            result["xp_gained"] += xp
        
        all_tweets.append(tweet)
    
    # 推しのリツイートを処理（XP加算のみ、引用ポストなし）
    for tweet in oshi_retweets:
        log_event(
            level=LogLevel.INFO,
            event_type=EventType.POST_DETECTED,
            data={"tweet_id": tweet.id, "type": "oshi_retweet"},
            message=f"Oshi retweet detected: {tweet.id}",
        )
        
        # 冪等性チェック（既に処理済みならスキップ）
        try:
            state_store.acquire_tweet_lock(tweet.id, "retweet_oshi")
            
            # リポストのXPを加算（引用ポストはしない）
            xp = xp_calculator.calculate_xp(ActivityType.REPOST)
            state.cumulative_xp += xp
            state.daily_xp += xp
            state.repost_count += 1
            state.daily_repost_count += 1
            result["xp_gained"] += xp
            
        except TweetAlreadyProcessedError:
            pass  # 既に処理済み - スキップ
        
        all_tweets.append(tweet)
    
    for tweet in group_original:
        log_event(
            level=LogLevel.INFO,
            event_type=EventType.POST_DETECTED,
            data={"tweet_id": tweet.id, "type": "group"},
            message=f"Group post detected: {tweet.id}",
        )
        
        # AI応答を生成して引用ポスト（冪等性制御付き）
        posted = _post_quote_safe(
            tweet=tweet,
            post_type="group",
            ai_generator=ai_generator,
            x_api_client=x_api_client,
            state_store=state_store,
        )
        
        # 投稿成功時のみXPを加算（既に処理済みの場合はスキップ）
        if posted:
            result["quotes_posted"] += 1
            
            # XPを加算
            xp = xp_calculator.calculate_xp(ActivityType.GROUP_POST)
            state.cumulative_xp += xp
            state.daily_xp += xp
            state.group_post_count += 1
            state.daily_group_count += 1
            result["group_posts_detected"] += 1
            result["xp_gained"] += xp
        
        all_tweets.append(tweet)
    
    # グループのリツイートを処理（XP加算のみ、引用ポストなし）
    for tweet in group_retweets:
        log_event(
            level=LogLevel.INFO,
            event_type=EventType.POST_DETECTED,
            data={"tweet_id": tweet.id, "type": "group_retweet"},
            message=f"Group retweet detected: {tweet.id}",
        )
        
        # 冪等性チェック（既に処理済みならスキップ）
        try:
            state_store.acquire_tweet_lock(tweet.id, "retweet_group")
            
            # リポストのXPを加算（引用ポストはしない）
            xp = xp_calculator.calculate_xp(ActivityType.REPOST)
            state.cumulative_xp += xp
            state.daily_xp += xp
            state.repost_count += 1
            state.daily_repost_count += 1
            result["xp_gained"] += xp
            
        except TweetAlreadyProcessedError:
            pass  # 既に処理済み - スキップ
        
        all_tweets.append(tweet)
    
    # 最新のTweet IDを更新
    if all_tweets:
        latest_id = max(all_tweets, key=lambda t: int(t.id)).id
        state.latest_tweet_id = latest_id
    
    # XP獲得をログ
    if result["xp_gained"] > 0:
        log_event(
            level=LogLevel.INFO,
            event_type=EventType.XP_GAINED,
            data={
                "xp_gained": result["xp_gained"],
                "cumulative_xp": state.cumulative_xp,
            },
            message=f"XP gained: {result['xp_gained']}",
        )
    
    # レベルアップチェック
    leveled_up, new_level = level_manager.check_level_up(
        current_level=state.current_level,
        cumulative_xp=state.cumulative_xp,
    )
    
    if leveled_up:
        state.current_level = new_level
        result["level_up"] = True
        result["new_level"] = new_level
        
        log_event(
            level=LogLevel.INFO,
            event_type=EventType.LEVEL_UP,
            data={
                "old_level": initial_level,
                "new_level": new_level,
                "cumulative_xp": state.cumulative_xp,
            },
            message=f"Level up! {initial_level} -> {new_level}",
        )
        
        # プロフィール更新
        _update_profile_on_level_up(
            state=state,
            level_manager=level_manager,
            xp_calculator=xp_calculator,
            image_compositor=image_compositor,
            profile_updater=profile_updater,
        )
    
    # 日報投稿チェック（daily_reportのみ）
    current_time = datetime.now(timezone.utc)
    if not is_core_time and daily_reporter.should_post_daily_report(state, current_time):
        next_level_xp = level_manager.get_xp_to_next_level(
            state.current_level, state.cumulative_xp
        ) or 0
        
        report_tweet_id = daily_reporter.post_daily_report(state, next_level_xp)
        if report_tweet_id:
            state.last_daily_report_date = daily_reporter.get_today_date_jst(current_time)
            state = state_store.reset_daily_counts(state)
            result["daily_report_posted"] = True
            
            log_event(
                level=LogLevel.INFO,
                event_type=EventType.DAILY_REPORT,
                message="Daily report posted",
            )
    
    # 朝コンテンツ（YouTube検索・翻訳）チェック（core_timeのみ）
    if is_core_time and daily_reporter.should_post_morning_content(
        prev_daily_oshi_count=state.prev_daily_oshi_count,
        current_time=current_time,
    ):
        # YouTube新着検索（新着があれば投稿）
        youtube_posted = daily_reporter.post_youtube_search(
            oshi_user_id=OSHI_USER_ID,
        )
        if youtube_posted:
            result["youtube_posted"] = True
            log_event(
                level=LogLevel.INFO,
                event_type=EventType.DAILY_REPORT,
                message="YouTube search posted",
            )

        # 日曜のみ: 人気ポストの翻訳
        if daily_reporter.should_post_translation(current_time):
            translation_posted = daily_reporter.post_translation(
                oshi_user_id=OSHI_USER_ID,
                latest_tweet_id=state.latest_tweet_id or "0",
            )
            if translation_posted:
                result["translation_posted"] = True
                log_event(
                    level=LogLevel.INFO,
                    event_type=EventType.DAILY_REPORT,
                    message="Translation posted",
                )
    
    # 状態を保存
    state_store.save_state(state)
    
    return result


def _check_timeline_safe(
    check_func,
    since_tweet_id: Optional[str],
    context: str,
) -> List[Tweet]:
    """
    タイムラインを安全にチェック（エラー時は空リストを返す）
    
    Args:
        check_func: タイムラインチェック関数
        since_tweet_id: 前回チェックした最新のTweet ID
        context: コンテキスト情報
    
    Returns:
        ツイートリスト
    """
    return generate_response_with_fallback(
        generator_func=lambda: check_func(since_tweet_id=since_tweet_id),
        fallback_value=[],
        context=context,
    )


def _post_quote_safe(
    tweet: Tweet,
    post_type: str,
    ai_generator: AIGenerator,
    x_api_client: XAPIClient,
    state_store: StateStore,
    state: BotState = None,
    s3_client = None,
    bucket_name: str = None,
) -> bool:
    """
    引用ポストを安全に投稿（冪等性制御付き、感情画像添付対応）
    
    Args:
        tweet: 引用するツイート
        post_type: "oshi" または "group"
        ai_generator: AIGeneratorインスタンス
        x_api_client: XAPIClientインスタンス
        state_store: StateStoreインスタンス
        state: BotStateインスタンス（画像添付判定用）
        s3_client: boto3 S3クライアント（画像取得用）
        bucket_name: S3バケット名
    
    Returns:
        投稿成功の可否（既に処理済みの場合もFalse）
    """
    try:
        # ロックを取得（既に処理済みの場合は例外が発生）
        state_store.acquire_tweet_lock(tweet.id, f"quote_{post_type}")
        
        # AI応答を生成
        response_text = ai_generator.generate_response(
            post_content=tweet.text,
            post_type=post_type,
        )
        
        # 感情画像添付の判定（推し投稿のみ、1日1回限定）
        media_ids = None
        if (
            post_type == "oshi"
            and state is not None
            and not state.daily_image_posted
            and s3_client is not None
            and bucket_name is not None
        ):
            media_id = _get_emotion_image_media_id(
                response_text=response_text,
                ai_generator=ai_generator,
                state_store=state_store,
                x_api_client=x_api_client,
                s3_client=s3_client,
                bucket_name=bucket_name,
            )
            if media_id:
                media_ids = [media_id]
                state.daily_image_posted = True
                log_event(
                    level=LogLevel.INFO,
                    event_type=EventType.POST_DETECTED,
                    data={"media_id": media_id},
                    message="Emotion image attached to quote post",
                )
        
        # 引用ポスト（画像付きの場合あり）
        x_api_client.post_tweet(
            text=response_text,
            quote_tweet_id=tweet.id,
            media_ids=media_ids,
        )
        
        return True
        
    except TweetAlreadyProcessedError:
        # 既に処理済み - スキップ（XP加算もスキップするためFalseを返す）
        return False
        
    except Exception as e:
        handle_api_error(e, f"post_quote_{post_type}")
        return False


def _get_emotion_image_media_id(
    response_text: str,
    ai_generator: AIGenerator,
    state_store: StateStore,
    x_api_client: XAPIClient,
    s3_client,
    bucket_name: str,
) -> Optional[str]:
    """
    応答テキストの感情を分類し、対応する画像をアップロードしてmedia_idを取得
    
    Args:
        response_text: 分類する応答テキスト
        ai_generator: AIGeneratorインスタンス
        state_store: StateStoreインスタンス
        x_api_client: XAPIClientインスタンス
        s3_client: boto3 S3クライアント
        bucket_name: S3バケット名
    
    Returns:
        media_id文字列（失敗時はNone）
    """
    try:
        # 感情を分類
        emotion_key = ai_generator.classify_emotion(response_text)
        if not emotion_key:
            return None
        
        # DynamoDBから画像ファイル名を取得
        filename = state_store.get_emotion_image_filename(emotion_key)
        if not filename:
            return None
        
        # S3から画像を取得
        s3_key = f"emotions/{filename}"
        response = s3_client.get_object(
            Bucket=bucket_name,
            Key=s3_key,
        )
        image_data = response["Body"].read()
        
        # Xにアップロード
        media_id = x_api_client.upload_media(image_data)
        
        log_event(
            level=LogLevel.INFO,
            event_type=EventType.POST_DETECTED,
            data={"emotion_key": emotion_key, "filename": filename},
            message=f"Emotion image uploaded: {emotion_key}",
        )
        
        return media_id
        
    except Exception as e:
        log_event(
            level=LogLevel.WARNING,
            event_type=EventType.POST_DETECTED,
            data={"error": str(e)},
            message="Failed to get emotion image, posting without image",
        )
        return None


def _update_profile_on_level_up(
    state: BotState,
    level_manager: LevelManager,
    xp_calculator: XPCalculator,
    image_compositor: ImageCompositor,
    profile_updater: ProfileUpdater,
) -> None:
    """
    レベルアップ時にプロフィールを更新
    プロフィール画像・名前の更新は月に一度のみ実行
    
    Args:
        state: 現在のボット状態
        level_manager: LevelManagerインスタンス
        xp_calculator: XPCalculatorインスタンス
        image_compositor: ImageCompositorインスタンス
        profile_updater: ProfileUpdaterインスタンス
    """
    try:
        # XP内訳を計算
        xp_breakdown = xp_calculator.calculate_xp_breakdown(
            oshi_post_count=state.oshi_post_count,
            group_post_count=state.group_post_count,
            repost_count=state.repost_count,
            like_count=state.like_count,
        )
        
        # 次のレベルまでのXPを計算
        next_level_xp = level_manager.get_xp_to_next_level(
            state.current_level, state.cumulative_xp
        ) or 0
        
        # プロフィール画像を合成（月次更新が必要な場合のみ）
        image_data = None
        if profile_updater.should_update_profile(state.last_profile_update_month):
            image_data = generate_response_with_fallback(
                generator_func=lambda: image_compositor.composite_level_image(state.current_level),
                fallback_value=None,
                context="image_composition",
            )
        
        # プロフィールを更新
        results = profile_updater.update_profile_on_level_up(
            level=state.current_level,
            image_data=image_data,
            xp_breakdown=xp_breakdown,
            next_level_xp=next_level_xp,
            last_profile_update_month=state.last_profile_update_month,
        )
        
        # プロフィール更新月を状態に反映
        if results.get("profile_update_month"):
            state.last_profile_update_month = results["profile_update_month"]
        
        log_event(
            level=LogLevel.INFO,
            event_type=EventType.PROFILE_UPDATED,
            data=results,
            message=f"Profile updated for level {state.current_level}",
        )
        
    except Exception as e:
        handle_api_error(e, "profile_update_on_level_up")


def _check_engagement_safe(
    x_api_client: XAPIClient,
    xp_calculator: XPCalculator,
    state: BotState,
    result: Dict[str, Any],
    bot_user_id: str,
) -> float:
    """
    ボット投稿へのエンゲージメント（いいね・リポスト）をチェックしてXPを計算
    
    Args:
        x_api_client: XAPIClientインスタンス
        xp_calculator: XPCalculatorインスタンス
        state: 現在のボット状態
        result: 結果辞書（更新される）
        bot_user_id: ボットのユーザーID
    
    Returns:
        獲得したXP
    """
    try:
        # ボットの投稿のエンゲージメント情報を取得
        response = x_api_client.get_my_tweets_with_metrics(
            bot_user_id=bot_user_id,
            max_results=100,
        )
        
        if "data" not in response:
            log_event(
                level=LogLevel.INFO,
                event_type=EventType.TIMELINE_CHECK,
                message="No tweets found for engagement check",
            )
            return 0.0
        
        # 全投稿のいいね数・リポスト数を集計
        total_likes = 0
        total_retweets = 0
        
        for tweet in response["data"]:
            metrics = tweet.get("public_metrics", {})
            total_likes += metrics.get("like_count", 0)
            total_retweets += metrics.get("retweet_count", 0)
        
        # 前回との差分を計算
        new_likes = max(0, total_likes - state.total_received_likes)
        new_retweets = max(0, total_retweets - state.total_received_retweets)
        
        # XPを計算
        like_xp = xp_calculator.calculate_xp(ActivityType.LIKE, new_likes)
        retweet_xp = xp_calculator.calculate_xp(ActivityType.REPOST, new_retweets)
        total_xp = like_xp + retweet_xp
        
        # 状態を更新
        state.total_received_likes = total_likes
        state.total_received_retweets = total_retweets
        state.like_count += new_likes
        state.daily_like_count += new_likes
        state.repost_count += new_retweets
        state.daily_repost_count += new_retweets
        state.cumulative_xp += total_xp
        state.daily_xp += total_xp
        
        # 結果を更新
        result["new_likes"] = new_likes
        result["new_retweets"] = new_retweets
        result["xp_gained"] += total_xp
        
        if new_likes > 0 or new_retweets > 0:
            log_event(
                level=LogLevel.INFO,
                event_type=EventType.XP_GAINED,
                data={
                    "new_likes": new_likes,
                    "new_retweets": new_retweets,
                    "like_xp": like_xp,
                    "retweet_xp": retweet_xp,
                    "total_likes": total_likes,
                    "total_retweets": total_retweets,
                },
                message=f"Engagement XP: {new_likes} likes (+{like_xp} XP), {new_retweets} retweets (+{retweet_xp} XP)",
            )
        
        return total_xp
        
    except Exception as e:
        handle_api_error(e, "check_engagement")
        return 0.0
