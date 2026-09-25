"""
Lambda関数のメインハンドラー

EventBridgeからトリガーされ、ボットのメインロジックを実行します。
"""
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import boto3

from .clients import XAPIClient, BufferClient
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
    ReplyMonitor,
    AllowedUsersService,
    ReplyProcessor,
    DraftNotifier,
    BufferScheduler,
    OshiMemoryWriter,
)
from .services.ai_generator import REACTION_SKIP
from .services.autonomous_selector import AutonomousSelection, AutonomousSelector
from .services.post_history_store import HistoryEntry, PostHistoryStore
from .services.buffer_scheduler import DEFAULT_SLOT_TIMES_JST
from .services.daily_reporter import JST
from .services.oshi_memory_writer import parse_created_at
from .utils import (
    log_event,
    EventType,
    LogLevel,
    handle_api_error,
    handle_critical_error,
    generate_response_with_fallback,
    BrainClient,
)


# 環境変数
STATE_TABLE_NAME = os.environ.get("STATE_TABLE_NAME", "imomaru-bot-state")
XP_TABLE_NAME = os.environ.get("XP_TABLE_NAME", "imomaru-bot-xp-table")
PROCESSED_TWEETS_TABLE_NAME = os.environ.get("PROCESSED_TWEETS_TABLE_NAME", "imomaru-bot-processed-tweets")
EMOTION_IMAGES_TABLE_NAME = os.environ.get("EMOTION_IMAGES_TABLE_NAME", "imomaru-bot-emotion-images")
ASSETS_BUCKET_NAME = os.environ.get("ASSETS_BUCKET_NAME", "imomaru-bot-assets")
SECRET_NAME = os.environ.get("SECRET_NAME", "imomaru-bot/x-api-credentials")
OSHI_USER_ID = os.environ.get("OSHI_USER_ID", "")
OSHI_USERNAME = os.environ.get("OSHI_USERNAME", "")
GROUP_USER_ID = os.environ.get("GROUP_USER_ID", "")
BOT_USER_ID = os.environ.get("BOT_USER_ID", "")
ALLOWED_USERS_TABLE_NAME = os.environ.get("ALLOWED_USERS_TABLE_NAME", "imomaru-bot-allowed-users")
PROCESSED_REPLIES_TABLE_NAME = os.environ.get("PROCESSED_REPLIES_TABLE_NAME", "imomaru-bot-processed-replies")
NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "")
# Buffer 半人力投稿（推し投稿への応答を Buffer キューに予約投入）
BUFFER_SECRET_NAME = os.environ.get("BUFFER_SECRET_NAME", "imomaru-bot/buffer-api")
BUFFER_DAILY_CAP = int(os.environ.get("BUFFER_DAILY_CAP", "7"))  # 1日の上限（安全弁）
BUFFER_RUN_CAP = int(os.environ.get("BUFFER_RUN_CAP", "1"))  # 1回の実行あたりの上限（主キャップ）
# Buffer UI のスロット時刻（JST、カンマ区切り）。頭脳に渡す「公開予定時刻」の見込み計算にだけ使う
BUFFER_SLOT_TIMES_JST = os.environ.get("BUFFER_SLOT_TIMES_JST", ",".join(DEFAULT_SLOT_TIMES_JST)).split(",")
BRAIN_RUNTIME_ARN = os.environ.get("BRAIN_RUNTIME_ARN", "")  # 頭脳（AgentCore Runtime）。空なら反応は skip・リプライは固定文（ERROR ログ）
OSHI_MEMORY_ID = os.environ.get("OSHI_MEMORY_ID", "")  # 推しの記憶（AgentCore Memory）。空なら書き込みなし・独り言なし
# 独り言（自律投稿、3b-1）の投稿履歴
POST_HISTORY_TABLE_NAME = os.environ.get("POST_HISTORY_TABLE_NAME", "imomaru-bot-post-history")
# 感情画像の公開バケット（Buffer が投稿公開時に取りに来る）
PUBLIC_ASSETS_BUCKET_NAME = os.environ.get("PUBLIC_ASSETS_BUCKET_NAME", "imomaru-bot-public-assets")
PUBLIC_ASSETS_BASE_URL = (
    f"https://{PUBLIC_ASSETS_BUCKET_NAME}.s3.{os.environ.get('AWS_REGION', 'ap-northeast-1')}.amazonaws.com"
)


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
    # 独り言（自律投稿、3b-1）を許す実行か（EventBridge の 21:00 回だけが true を渡す）。
    # autonomous_dry_run は手動確認用: Buffer・冪等ロック・履歴・状態に触れずメールだけ送る
    autonomous_allowed = event.get("autonomous_allowed") is True
    autonomous_dry_run = event.get("autonomous_dry_run") is True
    
    try:
        # AWSクライアントの初期化
        dynamodb_client = boto3.client("dynamodb")
        s3_client = boto3.client("s3")
        secrets_client = boto3.client("secretsmanager")
        ses_client = boto3.client("ses")
        
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
        
        # 頭脳（AgentCore Runtime）。invocation ごとに BrainClient を作り、1 セッションを使い回す
        brain_client = BrainClient(runtime_arn=BRAIN_RUNTIME_ARN) if BRAIN_RUNTIME_ARN else None
        ai_generator = AIGenerator(brain_client=brain_client)
        
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
        
        reply_monitor = ReplyMonitor(
            api_client=x_api_client,
            bot_user_id=BOT_USER_ID,
        )
        
        allowed_users_service = AllowedUsersService(
            dynamodb_client=dynamodb_client,
            table_name=ALLOWED_USERS_TABLE_NAME,
        )
        
        reply_processor = ReplyProcessor(
            dynamodb_client=dynamodb_client,
            processed_replies_table_name=PROCESSED_REPLIES_TABLE_NAME,
        )

        draft_notifier = DraftNotifier(
            ses_client=ses_client,
            from_email=FROM_EMAIL,
            to_email=NOTIFICATION_EMAIL,
        )

        buffer_scheduler = BufferScheduler(
            buffer_client=BufferClient(
                secrets_client=secrets_client,
                secret_name=BUFFER_SECRET_NAME,
            ),
            state_store=state_store,
            public_image_base_url=PUBLIC_ASSETS_BASE_URL,
            oshi_username=OSHI_USERNAME,
            daily_cap=BUFFER_DAILY_CAP,
            run_cap=BUFFER_RUN_CAP,
            slot_times_jst=BUFFER_SLOT_TIMES_JST,
        )

        # 推しの記憶（AgentCore Memory）。推しの投稿を Lambda から直接書き込む（フェーズ3a-write）
        oshi_memory_writer = (
            OshiMemoryWriter(memory_id=OSHI_MEMORY_ID, actor_id=OSHI_USERNAME)
            if OSHI_MEMORY_ID and OSHI_USERNAME
            else None
        )
        
        # 独り言の材料選び（推しの記憶を一覧）と投稿履歴
        autonomous_selector = (
            AutonomousSelector(memory_id=OSHI_MEMORY_ID, actor_id=OSHI_USERNAME)
            if OSHI_MEMORY_ID and OSHI_USERNAME
            else None
        )
        post_history_store = PostHistoryStore(table_name=POST_HISTORY_TABLE_NAME)

        # 状態の読み込み
        state = state_store.load_state()
        # 前の実行で埋めた Buffer 枠を公開予定時刻の見込みに反映する
        buffer_scheduler.restore_last_due_at(state.last_buffer_due_at)
        
        # XPテーブルの読み込み
        xp_table = state_store.load_xp_table()
        level_manager = LevelManager(xp_table=xp_table)
        
        # メイン処理を実行
        result = _process_bot_logic(
            state=state,
            state_store=state_store,
            timeline_monitor=timeline_monitor,
            reply_monitor=reply_monitor,
            allowed_users_service=allowed_users_service,
            reply_processor=reply_processor,
            xp_calculator=xp_calculator,
            level_manager=level_manager,
            ai_generator=ai_generator,
            image_compositor=image_compositor,
            profile_updater=profile_updater,
            daily_reporter=daily_reporter,
            x_api_client=x_api_client,
            draft_notifier=draft_notifier,
            buffer_scheduler=buffer_scheduler,
            oshi_memory_writer=oshi_memory_writer,
            s3_client=s3_client,
            bucket_name=ASSETS_BUCKET_NAME,
            execution_mode=execution_mode,
            autonomous_allowed=autonomous_allowed,
            autonomous_dry_run=autonomous_dry_run,
            autonomous_selector=autonomous_selector,
            post_history_store=post_history_store,
            remaining_time_ms=getattr(context, "get_remaining_time_in_millis", None),
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
    reply_monitor: ReplyMonitor,
    allowed_users_service: AllowedUsersService,
    reply_processor: ReplyProcessor,
    xp_calculator: XPCalculator,
    level_manager: LevelManager,
    ai_generator: AIGenerator,
    image_compositor: ImageCompositor,
    profile_updater: ProfileUpdater,
    daily_reporter: DailyReporter,
    x_api_client: XAPIClient,
    draft_notifier: DraftNotifier = None,
    buffer_scheduler: BufferScheduler = None,
    oshi_memory_writer: OshiMemoryWriter = None,
    s3_client = None,
    bucket_name: str = None,
    execution_mode: str = "daily_report",
    autonomous_allowed: bool = False,
    autonomous_dry_run: bool = False,
    autonomous_selector: Optional[AutonomousSelector] = None,
    post_history_store: Optional[PostHistoryStore] = None,
    remaining_time_ms: Optional[Callable[[], int]] = None,
) -> Dict[str, Any]:
    """
    ボットのメインロジックを実行
    
    Args:
        state: 現在のボット状態
        state_store: StateStoreインスタンス
        timeline_monitor: TimelineMonitorインスタンス
        reply_monitor: ReplyMonitorインスタンス
        allowed_users_service: AllowedUsersServiceインスタンス
        reply_processor: ReplyProcessorインスタンス
        xp_calculator: XPCalculatorインスタンス
        level_manager: LevelManagerインスタンス
        ai_generator: AIGeneratorインスタンス
        image_compositor: ImageCompositorインスタンス
        profile_updater: ProfileUpdaterインスタンス
        daily_reporter: DailyReporterインスタンス
        x_api_client: XAPIClientインスタンス
        oshi_memory_writer: OshiMemoryWriterインスタンス（None なら推しの記憶を書き込まない）
        s3_client: boto3 S3クライアント（感情画像取得用）
        bucket_name: S3バケット名
        autonomous_allowed: 独り言（自律投稿、3b-1）を許す実行か（core_time のときだけ有効）
        autonomous_dry_run: 独り言を Buffer・ロック・履歴・状態に触れずメールだけで試す
        autonomous_selector: 独り言の材料選び（None なら独り言なし）
        post_history_store: 独り言の投稿履歴
        remaining_time_ms: Lambda の残り時間（ミリ秒）を返す関数
    
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
        "replies_processed": 0,
        "memory_events_recorded": 0,
        "react_calls": 0,
    }
    
    is_core_time = (execution_mode == "core_time")
    initial_level = state.current_level
    
    # ボット投稿へのエンゲージメントをチェック（daily_reportのみ）
    if not is_core_time:
        _check_engagement_safe(
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
    
    # 推しのタイムラインをチェック（推し専用IDを使用）
    oshi_tweets = _check_timeline_safe(
        timeline_monitor.check_oshi_timeline,
        state.latest_oshi_tweet_id,
        "oshi_timeline",
    )
    
    # グループのタイムラインをチェック（daily_reportのみ、グループ専用IDを使用）
    if not is_core_time:
        group_tweets = _check_timeline_safe(
            timeline_monitor.check_group_timeline,
            state.latest_group_tweet_id,
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
        
        # 冪等性チェック（既に処理済みならスキップ）
        try:
            state_store.acquire_tweet_lock(tweet.id, f"quote_oshi")
        except TweetAlreadyProcessedError:
            all_tweets.append(tweet)
            continue  # 既に処理済み - スキップ
        
        # XPを加算（引用ポストの成否に関わらず）
        xp = xp_calculator.calculate_xp(ActivityType.OSHI_POST)
        state.cumulative_xp += xp
        state.daily_xp += xp
        state.oshi_post_count += 1
        state.daily_oshi_count += 1
        result["oshi_posts_detected"] += 1
        result["xp_gained"] += xp

        # 推しの記憶に書き込む（引用ポストも推し自身の言葉なので対象。失敗しても他機能を巻き込まない）
        if oshi_memory_writer is not None and _record_oshi_memory_safe(oshi_memory_writer, tweet):
            result["memory_events_recorded"] += 1
        
        # 推し自身の引用ポストは本文に推しのコメントしか含まれず、引用元の文脈を AI が読めないため
        # 応答がズレる。XP は加算したうえで AI 生成・メール・Buffer 投入はスキップする（2026-09-12 決定）
        if tweet.is_quote_tweet:
            log_event(
                level=LogLevel.INFO,
                event_type=EventType.POST_DETECTED,
                data={"tweet_id": tweet.id, "action": "xp_only", "quote_post_skipped": True},
                message=f"Oshi quote tweet processed (XP only, quote post skipped): {tweet.id}",
            )
            all_tweets.append(tweet)
            continue

        # AI応答を生成し、メール素案通知 ＋ Buffer 予約投入（半人力）
        result["react_calls"] += 1
        posted = _post_quote_safe(
            tweet=tweet,
            post_type="oshi",
            ai_generator=ai_generator,
            x_api_client=x_api_client,
            state_store=state_store,
            state=state,
            s3_client=s3_client,
            bucket_name=bucket_name,
            oshi_username=OSHI_USERNAME,
            draft_notifier=draft_notifier,
            buffer_scheduler=buffer_scheduler,
        )
        
        if posted:
            result["quotes_posted"] += 1
        
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
        
        # 引用ポストをスキップ（AI生成もスキップ）- XP加算のみ実行
        try:
            state_store.acquire_tweet_lock(tweet.id, "group_original_xp_only")
            xp = xp_calculator.calculate_xp(ActivityType.GROUP_POST)
            state.cumulative_xp += xp
            state.daily_xp += xp
            state.group_post_count += 1
            state.daily_group_count += 1
            result["group_posts_detected"] += 1
            result["xp_gained"] += xp
            
            log_event(
                level=LogLevel.INFO,
                event_type=EventType.POST_DETECTED,
                data={
                    "tweet_id": tweet.id,
                    "action": "xp_only",
                    "xp_gained": xp,
                    "quote_post_skipped": True,
                    "ai_generation_skipped": True,
                },
                message=f"Group original post processed (XP only, quote post skipped): {tweet.id}",
            )
        except TweetAlreadyProcessedError:
            pass  # 既に処理済み - スキップ
        
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
    
    # 推しとグループのIDを個別に集計し、それぞれの最大IDで対応するフィールドのみを更新
    # （all_tweetsはログ等で引き続き使用するが、ID更新には使わない）
    oshi_all = oshi_original + oshi_retweets
    if oshi_all:
        state.latest_oshi_tweet_id = max(oshi_all, key=lambda t: int(t.id)).id

    group_all = group_original + group_retweets
    if group_all:
        state.latest_group_tweet_id = max(group_all, key=lambda t: int(t.id)).id
    
    # リプライ検出・処理（Daily Report Mode、Core Time Modeの両方で実行）
    # コアタイム時は短時間しか経過していないため、max_resultsを絞る
    max_results = 20 if is_core_time else 100
    replies = reply_monitor.detect_replies(
        since_tweet_id=state.latest_reply_check_id,
        max_results=max_results,
    )
    
    replies_processed_count = 0
    for reply in replies:
        # 許可ユーザーチェック
        if not allowed_users_service.is_user_allowed(reply.author_id):
            log_event(
                level=LogLevel.INFO,
                event_type=EventType.POST_DETECTED,
                data={"reply_id": reply.id, "author_id": reply.author_id},
                message=f"Reply from non-allowed user, skipping: {reply.id}",
            )
            continue
        
        # リプライ処理
        processed = reply_processor.process_reply(
            reply=reply,
            ai_generator=ai_generator,
            x_api_client=x_api_client,
        )
        if processed:
            replies_processed_count += 1
    
    result["replies_processed"] = replies_processed_count
    
    # latest_reply_check_idを更新
    if replies:
        latest_reply_id = max(replies, key=lambda r: int(r.id)).id
        state.latest_reply_check_id = latest_reply_id
    
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
    
    # 独り言（自律投稿、3b-1 (i)）: 推し投稿に反応しなかった夜の実行だけ
    if is_core_time and autonomous_allowed:
        result["autonomous_status"] = _autonomous_post_safe(
            state=state,
            state_store=state_store,
            ai_generator=ai_generator,
            draft_notifier=draft_notifier,
            buffer_scheduler=buffer_scheduler,
            selector=autonomous_selector,
            history_store=post_history_store,
            react_calls=result["react_calls"],
            dry_run=autonomous_dry_run,
            remaining_time_ms=remaining_time_ms,
        )

    # 状態を保存
    state_store.save_state(state)
    
    return result


# 独り言（自律投稿、3b-1）
AUTONOMOUS_MIN_REMAINING_MS = 120_000   # 頭脳の read timeout（90 秒）＋ Buffer・SES の余裕
AUTONOMOUS_HISTORY_DAYS = 7             # 重複キー（B は同じ記憶を 7 日作らない）と直近本文の参照範囲
AUTONOMOUS_RECENT_TEXTS = 3             # 頭脳に渡す直近の独り言の件数
AUTONOMOUS_LOCK_PREFIX = "autonomous-"  # processed-tweets の冪等ロック（1 日 1 件。数値のツイート ID と衝突しない）


def _autonomous_kind_label(selection: AutonomousSelection) -> str:
    if selection.kind == "A":
        countdown = "明日" if selection.days_left == 1 else f"あと {selection.days_left} 日"
        return f"A. 未来イベント（{selection.event_date:%m/%d} まで{countdown}）"
    return "B. 直近の出来事の余韻"


def _autonomous_skip(reason: str) -> str:
    log_event(
        level=LogLevel.INFO,
        event_type=EventType.POST_DETECTED,
        data={"autonomous_skip": reason},
        message=f"autonomous_skip reason={reason}",
    )
    return reason


def _autonomous_post_safe(**kwargs: Any) -> str:
    """
    独り言（自律投稿）を試みる。失敗は握りつぶし ERROR ログ（アラーム）にして、状態の保存を妨げない

    Returns:
        結果（scheduled / cap / failed / skipped / dry_run / brain_failed / error、または見送り理由）
    """
    try:
        return _autonomous_post(**kwargs)
    except Exception as e:
        handle_api_error(e, "autonomous_post")
        return "error"


def _autonomous_post(
    state: BotState,
    state_store: StateStore,
    ai_generator: AIGenerator,
    draft_notifier: Optional[DraftNotifier],
    buffer_scheduler: Optional[BufferScheduler],
    selector: Optional[AutonomousSelector],
    history_store: Optional[PostHistoryStore],
    react_calls: int,
    dry_run: bool = False,
    remaining_time_ms: Optional[Callable[[], int]] = None,
    now: Optional[datetime] = None,
) -> str:
    """
    推しの投稿に反応しなかった夜に、推しの記憶から独り言を 1 件作って Buffer に入れる（設計書 §10-11）

    発火条件（決定論）: この実行で react 0 件 ＋ 本日未実施 ＋ 次の枠が今日 ＋ Buffer キャップに空き ＋ 残り時間。
    候補は AutonomousSelector が選び、頭脳は 1 回だけ呼ぶ。頭脳の skip はメールで理由を知らせる（候補なしはログのみ）
    """
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(JST).date()
    today_str = today.isoformat()

    if react_calls > 0:
        return _autonomous_skip("reacted")
    if state.last_autonomous_date == today_str:
        return _autonomous_skip("already_done")
    if None in (buffer_scheduler, selector, history_store, draft_notifier):
        return _autonomous_skip("not_configured")
    publish_at = buffer_scheduler.next_slot_at(now)
    if publish_at is None or publish_at.astimezone(JST).date() != today:
        return _autonomous_skip("next_slot_tomorrow")
    if not buffer_scheduler.can_schedule(state):
        return _autonomous_skip("cap")
    if remaining_time_ms is not None and remaining_time_ms() < AUTONOMOUS_MIN_REMAINING_MS:
        return _autonomous_skip("low_time")

    history = history_store.load_recent(today, AUTONOMOUS_HISTORY_DAYS)
    selection = selector.select(now, history_store.used_keys(history))
    if selection is None:
        return _autonomous_skip("no_candidates")

    if not dry_run:
        # タイムアウト時の自動リトライや EventBridge の重複配信で 2 件入らないように、頭脳を呼ぶ前にロックする
        try:
            state_store.acquire_tweet_lock(f"{AUTONOMOUS_LOCK_PREFIX}{today_str}", "autonomous")
        except TweetAlreadyProcessedError:
            return _autonomous_skip("locked")

    reaction = ai_generator.generate_autonomous(
        kind=selection.kind,
        candidates=[c.to_brain() for c in selection.candidates],
        now=now,
        publish_at=publish_at,
        days_left=selection.days_left,
        event_date=selection.event_date,
        recent_texts=[e.text for e in history[:AUTONOMOUS_RECENT_TEXTS]],
    )
    if reaction.source == "error":
        # ERROR ログ（アラーム）は AIGenerator が出している。ロック済みなので今日は再試行しない
        return "brain_failed"

    kind_label = _autonomous_kind_label(selection)
    used = [c for c in selection.candidates if c.record_id in reaction.sources] or selection.candidates
    sources = [(c.record_id, c.text) for c in used]

    if reaction.action == REACTION_SKIP:
        if not dry_run:
            state.last_autonomous_date = today_str
        draft_notifier.send_autonomous_email(
            kind_label=kind_label,
            draft_text="",
            reason=reaction.reason,
            sources=sources,
            buffer_status=DraftNotifier.BUFFER_STATUS_SKIPPED,
        )
        return "skipped"

    if dry_run:
        draft_notifier.send_autonomous_email(
            kind_label=f"{kind_label}［dry run: Buffer には入れていません］",
            draft_text=reaction.text,
            reason=reaction.reason,
            sources=sources,
            emotion_key=reaction.emotion_key,
        )
        return "dry_run"

    scheduled = None
    try:
        scheduled = buffer_scheduler.schedule_autonomous(state, reaction.text, reaction.emotion_key)
        status = DraftNotifier.BUFFER_STATUS_SCHEDULED if scheduled else DraftNotifier.BUFFER_STATUS_CAP
    except Exception as e:
        handle_api_error(e, "buffer_schedule_autonomous")
        status = DraftNotifier.BUFFER_STATUS_FAILED
    state.last_autonomous_date = today_str

    if scheduled is not None:
        try:
            history_store.record(HistoryEntry(
                posted_date=today_str,
                kind=selection.kind,
                text=reaction.text,
                record_ids=[c.record_id for c in used],
                dedupe_keys=selection.keys_for(c.record_id for c in used),
                buffer_post_id=scheduled.post_id,
            ))
        except Exception as e:
            handle_api_error(e, "autonomous_history")

    draft_notifier.send_autonomous_email(
        kind_label=kind_label,
        draft_text=reaction.text,
        reason=reaction.reason,
        sources=sources,
        emotion_key=reaction.emotion_key if scheduled and scheduled.image_attached else None,
        buffer_status=status,
        buffer_due_at=scheduled.due_at if scheduled else None,
        buffer_run_cap=buffer_scheduler.run_cap,
    )
    return status


def _record_oshi_memory_safe(oshi_memory_writer: OshiMemoryWriter, tweet: Tweet) -> bool:
    """
    推しの投稿を AgentCore Memory に書き込む（フェーズ3a-write）

    失敗は握りつぶすが、記憶が育っていないことに気づけるよう ERROR ログ（アラーム対象）を出す。

    Returns:
        書き込み成功の可否
    """
    try:
        event_id = oshi_memory_writer.record_post(tweet)
        log_event(
            level=LogLevel.INFO,
            event_type=EventType.POST_DETECTED,
            data={"tweet_id": tweet.id, "memory_event_id": event_id},
            message=f"Oshi memory event recorded: {tweet.id}",
        )
        return True
    except Exception as e:
        handle_api_error(e, "oshi_memory_write")
        return False


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
    oshi_username: str = "",
    draft_notifier: "DraftNotifier" = None,
    buffer_scheduler: "BufferScheduler" = None,
) -> bool:
    """
    推しの投稿への AI 応答を、メール素案通知 ＋ Buffer 予約投入で処理する（半人力）

    X API の ContentCreateWithUrl 課金を避けるため直接ポストせず、
    ① SES メールで素案を通知（人間の目視・X Intent リンクの非常口）
    ② Buffer のキューに予約投入（次の空きスロットで Buffer が自動投稿。NG なら人間が削除）
    を並列に行う。Buffer 投入の失敗は握りつぶし、XP 計算・日報・リプライを巻き込まない。
    頭脳が「反応を見送る」（action=skip）と判断した場合は Buffer に入れず、理由をメールに載せる。

    Args:
        tweet: 反応する元ツイート
        post_type: "oshi" または "group"
        ai_generator: AIGeneratorインスタンス
        x_api_client: XAPIClientインスタンス
        state_store: StateStoreインスタンス
        state: BotStateインスタンス（キャップ・画像フラグ判定用）
        s3_client: boto3 S3クライアント
        bucket_name: S3バケット名
        oshi_username: 推しのXユーザー名
        draft_notifier: DraftNotifierインスタンス
        buffer_scheduler: BufferSchedulerインスタンス（None なら Buffer 投入なし）

    Returns:
        メール送信成功の可否
    """
    try:
        # 頭脳に反応を提案させる（ロック取得は呼び出し元で実施済み）。
        # 時刻情報（投稿時刻・現在時刻・公開予定＝次の Buffer 枠）を渡し、公開時に読まれる前提の文面にする。
        # 感情キーは提案に含まれるが、使うのは「Buffer に画像付きで投入できる」ときだけ（1日1回）
        now = datetime.now(timezone.utc)
        posted_at = parse_created_at(tweet.created_at) or now
        publish_at = buffer_scheduler.next_slot_at(now) if buffer_scheduler is not None else None
        can_attach_image = (
            post_type == "oshi"
            and state is not None
            and buffer_scheduler is not None
            and buffer_scheduler.can_attach_image(state)
        )
        reaction = ai_generator.generate_reaction(
            post_content=tweet.text,
            posted_at=posted_at,
            now=now,
            publish_at=publish_at,
            post_type=post_type,
        )
        response_text = reaction.text

        emotion_key = reaction.emotion_key if can_attach_image else None
        if emotion_key:
            log_event(
                level=LogLevel.INFO,
                event_type=EventType.POST_DETECTED,
                data={"emotion_key": emotion_key},
                message=f"Emotion classified for draft: {emotion_key}",
            )

        # Buffer 予約投入（失敗しても他機能を巻き込まない）。頭脳が skip と判断したら入れない
        buffer_status = "disabled"
        buffer_due_at = None
        skip_reason = None
        if reaction.action == REACTION_SKIP:
            buffer_status = DraftNotifier.BUFFER_STATUS_SKIPPED
            skip_reason = reaction.reason or None
            emotion_key = None
            log_event(
                level=LogLevel.INFO,
                event_type=EventType.POST_DETECTED,
                data={"tweet_id": tweet.id, "action": "skip", "reason": reaction.reason},
                message=f"Brain skipped reaction for tweet {tweet.id}: {reaction.reason}",
            )
        elif post_type == "oshi" and state is not None and buffer_scheduler is not None:
            try:
                scheduled = buffer_scheduler.schedule_quote(
                    state=state,
                    tweet_id=tweet.id,
                    draft_text=response_text,
                    emotion_key=emotion_key,
                )
                if scheduled is None:
                    buffer_status = "cap"
                else:
                    buffer_status = "scheduled"
                    buffer_due_at = scheduled.due_at
                    if not scheduled.image_attached:
                        emotion_key = None
            except Exception as e:
                handle_api_error(e, "buffer_schedule")
                buffer_status = "failed"
                emotion_key = None

        # メールで素案を通知（目視確認 ＋ X Intent リンクの非常口）
        if draft_notifier is not None:
            sent = draft_notifier.send_draft_email(
                original_tweet_text=tweet.text,
                original_tweet_id=tweet.id,
                oshi_username=oshi_username,
                draft_text=response_text,
                emotion_key=emotion_key,
                buffer_status=buffer_status,
                buffer_due_at=buffer_due_at,
                buffer_run_cap=buffer_scheduler.run_cap if buffer_scheduler else None,
                skip_reason=skip_reason,
            )
            return sent

        return False

    except Exception as e:
        handle_api_error(e, f"post_quote_{post_type}")
        return False


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
        # 1日1回制限チェック（JST基準）
        today_jst = datetime.now(JST).strftime("%Y-%m-%d")
        if state.last_engagement_check_date == today_jst:
            log_event(
                level=LogLevel.INFO,
                event_type=EventType.TIMELINE_CHECK,
                message="本日は集計済みのためエンゲージメントチェックをスキップ",
            )
            return 0.0

        # ボットの投稿のエンゲージメント情報を取得（取得件数を20に制限）
        response = x_api_client.get_my_tweets_with_metrics(
            bot_user_id=bot_user_id,
            max_results=20,
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
        
        # エンゲージメントチェック完了日を更新
        state.last_engagement_check_date = today_jst
        
        return total_xp
        
    except Exception as e:
        handle_api_error(e, "check_engagement")
        return 0.0
