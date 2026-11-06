# 頭脳・独り言・記憶

[← README に戻る](../README.md)

## 頭脳（AgentCore Runtime）

推し投稿への反応・独り言・リプライ応答は、Lambda から Amazon Bedrock AgentCore Runtime `imomaru_brain`
（Strands Agent）に依頼して生成します（フェーズ2a、2026-09-12。2b-2-1 で `react` に統合、2026-09-16。`autonomous` は 3b-1、2026-09-26）。

| タスク | 入力 | 出力 |
|------|------|------|
| `react` | 投稿本文 ＋ 時刻情報（投稿時刻・現在時刻・公開予定＝次の Buffer 枠、JST） | JSON 提案 `{"action": "post"\|"skip", "text", "emotion_key", "reason"}`。`skip` なら Lambda は Buffer に入れず、理由をメールに載せる |
| `autonomous` | 素案タイプ（A〜D）＋ Lambda が選んだ推しの記憶（id・本文・記録日時）＋ 現在時刻・公開予定 ＋ 直近の独り言 | JSON 提案 `{"action", "text", "emotion_key", "reason", "sources"}`（`sources` は使った記憶の id。下の「独り言」） |
| `reply_response` | 許可ユーザーのリプライ本文・元投稿 | 応答文 |

「考える頭脳・実行する Lambda」（設計書 §10-11）: 頭脳は提案を返すだけで、140 字整形・感情キー検証・Buffer／メール・キャップは Lambda が決定論で行います。
時刻情報は Buffer 予約制で「検知 → 公開」に数時間のラグがあるため、公開時刻に合った挨拶・時制（「昨夜の〜」）にするためのものです。
`react` では推しの記憶（AgentCore Memory の retrieve 結果）も user message に入ります（下の「推しの記憶」）。

| 項目 | 内容 |
|------|------|
| デプロイ方式 | direct code deploy（`dist/brain.zip`、`PYTHON_3_12`、arm64）。`agent/` 配下のコードと `agent/requirements.txt` を `scripts/build_agent_package.sh` が zip 化し、CDK が S3 アセットとして配置 |
| プラットフォーム | `V2`（スナップショットから起動、2026-11-06 移行。`stack.py` の `BRAIN_PLATFORM_VERSION`）。更新は `READY` まで数分かかる。起動時に時刻・乱数・認証情報を保持しない（[Runtime V2 向けの最適化](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-v2-optimize.html)）。戻すときは値を `V1` にして `cdk deploy` |
| モデル | Runtime の環境変数 `BRAIN_MODEL_ID`（`stack.py` の `BRAIN_MODEL_ID`）。既定 `moonshotai.kimi-k2.5`（東京 In-Region）。差し替えは値を変えて `cdk deploy` するだけ。Grok 4.6 はこのアカウントでは提供制限（`AccessDeniedException … not available for this account`）のため未使用 |
| 呼び出し | Lambda の `AIGenerator` → `utils/brain_client.py`（`bedrock-agentcore:InvokeAgentRuntime`）。Lambda 1 回の実行で 1 セッションを使い回す。Runtime 側の Agent はリクエストごとに使い捨て |
| 失敗時 | 頭脳の呼び出しに失敗（JSON 提案の形が崩れた場合、`post` なのに本文が空の場合も含む）すると `[ERROR] Brain failed …` を出して（アラーム発火）、推し投稿への反応は skip 扱い（Buffer に入れず、素案メールに「頭脳の呼び出しに失敗したため素案なし」）、リプライは固定文「@user ありがとうｲﾓ🍠✨」。`BRAIN_RUNTIME_ARN` が空でも同じ（`Brain not configured`）。Bedrock Haiku 4.5 直呼びのフォールバックは 2026-09-25 に撤去（フェーズ2b-3） |
| 公開予定時刻 | Lambda env `BUFFER_SLOT_TIMES_JST`（Buffer UI のスロット時刻の写し、既定 `02:00,08:00,11:15,12:15,14:15,15:15,19:15,20:15,22:00`）から現在時刻の次の枠を算出して頭脳に渡す。最後に投入した投稿の予約時刻（Buffer が返した実スロット）＋30 分より後の枠を渡す。同じ実行の 2 件目以降（2026-09-25）に加え、前の実行で埋めた枠も BotState `last_buffer_due_at` から復元して考慮する（2026-09-26、3b-1。例: 21:00 回の 2 件目が 02:00 を使うと、23:58 回の 1 件目には 08:00 を渡す）。Buffer UI で枠を変えたらこの値も合わせる |
| プロンプト | `src/hokuhoku_imomaru_bot/prompts.py` が単一ソース（`agent/prompts.py` はそのシンボリックリンク）。キャラクター定義は system prompt、反応対象は user message |
| 本文の体裁 | 1 文 1 行 ＋ 空行 ＋ ハッシュタグ（最終行）。プロンプトで指示しつつ、Lambda 側 `AIGenerator.format_post_text` が文末「ｲﾓ🍠」を境に機械的に整える（モデルが 1 行で返したときの保険。2026-09-26 から語尾「ｲﾓ🍠」は 1 投稿 1〜2 回の指示なので、語尾のない文の境界では分割しない）。整形後に改行込みで 140 字に切り詰める（2026-09-15）。語尾の崩れ（全角「イモ🍠」・「ｲﾐ🍠」など）も半角「ｲﾓ🍠」に揃える（2026-09-25。「ｲﾓ🍠🍠」は強調として残す）。リプライも同じ整形を通す |
| 時刻の扱い | 公開予定時刻は挨拶の選択だけに使い、本文に時刻を書かない。投稿の出来事は投稿時刻基準で書き、翌日以降の公開なら「昨日の」で補う。投稿に書かれていないこと（「見せたい」→「公開された」等）は書かない（2026-09-25、時制の逆ぶれ 3 回・「19:15」の漏れへの対処） |
| 挨拶・時間帯（2026-09-28） | 頭脳（`prompts.py`）が時刻から決定論で求めて user message に書く: 投稿時刻・公開予定の時間帯（深夜／朝／昼／夜）、公開予定の日が投稿の翌日か（「明日」→「今日」の言い換え）、公開予定に合う挨拶（5〜10 時 おはよう／11〜17 時 こんにちは／18〜21 時 こんばんは／22〜23 時 こんばんは・おやすみ／0〜4 時 なし）。本文に合わない挨拶（推しの「おはよう」の返し・引用）が残ったら、同じ会話で 1 回だけ書き直させる（09-26〜27 に昼の公開で「おはよう」「おやすみ」が 3 件出たことへの対処）。「ぼくも昨日食べた」「ぼくも大好きなんだ」のようないも丸自身の経験・好み（`own_experience_words`）も同じ書き直しの対象（2026-10-21。独り言 D で 8 件中 5 件出たことへの対処） |
| 見えないこと・未確認のこと（2026-09-30） | 頭脳は画像を受け取らないので、画像の内容や推しの見た目（笑顔・姿・表情・服装）は本文に書かれていない限り書かない。推しの行動・習慣・意図を投稿や記憶にないまま断定せず、ファンとしての習慣や気持ちを書くときは主語「ぼく」を書く（推しの行動と読まれないため）。KiroCrew（プロンプト・判断基準の伴走役）の回答を反映 |
| 生成パラメータ | `temperature=0.6`（Kimi K2.5 Instant の推奨値。Bedrock 経由は推論なしで Instant 相当）、`max_tokens=1024`（`agent/brain.py`） |
| ログ | `/aws/bedrock-agentcore/runtimes/imomaru_brain-*` |

```bash
# ローカルで頭脳を起動して確認（Bedrock を実際に呼びます）。推しの記憶も使うなら環境変数を付ける（未設定なら記憶なし）
OSHI_MEMORY_ID=<OshiMemoryId> OSHI_ACTOR_ID=juri_bigangel uv run python agent/main.py
curl -X POST localhost:8080/invocations -H 'Content-Type: application/json' \
  -d '{"task":"react","input":{"post_content":"今日はライブでした！","post_type":"oshi","posted_at":"2026-09-16(水) 01:42 JST","now":"2026-09-16(水) 10:07 JST","publish_at":"2026-09-16(水) 11:15 JST"}}'

# deploy 後の本番疎通確認（3 タスクを 1 回ずつ invoke。react は注入した記憶の件数 memories=N も表示）
uv run python scripts/test_brain_invoke.py
# react の JSON 提案の安定性（パース成功率・action の分布）
uv run python scripts/test_brain_invoke.py --task react --runs 5
# 独り言（autonomous）。サンプルは 09-28 生誕祭のカウントダウン
uv run python scripts/test_brain_invoke.py --task autonomous --runs 3
```

## 独り言（自律投稿、3b-1、2026-09-26〜）

推しの投稿に反応しなかった回に、いも丸が推しの記憶から独り言をつくって Buffer に入れます（設計書 §10-11）。
2026-09-26 は 21:00 回だけ・タイプ A/B・1 日 1 件（(i)）、2026-09-28 から全コアタイム・タイプ A〜D・1 日 2 件（(ii)）。

| 項目 | 内容 |
|------|------|
| 発火条件 | コアタイム 4 回（10:00 / 13:00 / 18:00 / 21:00、EventBridge 入力 `autonomous_allowed: true`。23:58 回は次の枠が翌 02:00 でレビューできないので対象外）。その実行で `react` 0 件 ＋ 次の Buffer 枠が今日 ＋ キャップに空き ＋ **日次キャップのうち 2 件を推し投稿への反応用に残せる**（`daily_buffer_count ≤ 7 − 3`）＋ Lambda の残り時間 ≥ 120 秒 ＋ **今日の独り言が公開 2 件未満・頭脳呼び出し 3 回未満**（投稿履歴から数える） |
| 材料選び（Lambda、決定論） | facts と preferences を一覧 → ファン視点・生活の細部（睡眠・体調に加え 腹痛/お腹/ヤモリ/忘れ/野菜）を除外 → 優先順に最初に候補が残ったタイプから最大 3 件（C は 1 投稿に話題を詰め込まないよう 2 件）: **A 未来イベント**（本文の日付が 1〜14 日後。当日は対象外。同じ日付の記憶をまとめる）→ **B 直近の出来事**（イベント語 ＋ 抽出 3 日以内 ＋ 今日より前の出来事の日付〔「〜時点」の日付は数えない〕あり、今日以降の日付と告知語〔予定/決定/リリース/キャンペーン/発売〕を含まない）→ **C 進行中・これからの活動**（取り組み語・告知語 ＋ 抽出 14 日以内。A の記憶・今日の日付・日付がすべて 3 日より前の記憶・終わったイベントは除く）→ **D 好み・小ネタ**（preferences の `preference`。苦手/隠して/不満も除外）。候補なしは頭脳を呼ばず `autonomous_skip reason=no_candidates` |
| 重複 | DynamoDB `imomaru-bot-post-history`（PK `posted_date` = `YYYY-MM-DD#HH`〔実行の JST の日と時〕、TTL 30 日、`status` = scheduled / skipped）の重複キー（A = `A:<イベント日>:<残り日数>`、B・C = `<タイプ>:<record_id>` を 7 日、D = 14 日）。**頭脳が skip した候補も記録**し、重複キーの期間は別の候補を選ぶ。直近 7 日・最大 10 件の本文（skip 以外）を頭脳に渡し、同じ出来事・話題（イベント名が同じなら別の切り口でも）なら頭脳が skip、別の話題でも言い回しの重複を避ける（2026-10-21。記憶の統合で同じイベントが別の record_id になり、B が SPARK2026 を 3 日連続で書いたことへの対処） |
| 頭脳 | `autonomous` タスク 1 回（次のタイプには落とさない）。`{action, text, emotion_key, reason, sources}`。`skip` を許す |
| 冪等 | 頭脳を呼ぶ前に processed-tweets に `autonomous-YYYY-MM-DD-HH` をロック（タイムアウト時の再実行で 2 件入らない） |
| 通知 | 件名「【いも丸】独り言の素案ｲﾓ🍠」。素案・判断理由・**根拠にした記憶の本文**・Buffer 状態。頭脳の skip もメール（候補なしはログのみ）。頭脳の失敗は `[ERROR]`（アラーム）のみ |
| 結果 | Lambda の結果 `react_calls` / `autonomous_status`（scheduled / cap / failed / skipped / brain_failed / error、または見送り理由 reacted / next_slot_tomorrow / cap / reserve / low_time / daily_limit / attempt_limit / no_candidates / locked） |

```bash
# 本番の記憶でどの候補が選ばれるか（読み取り専用。--at で JST の時刻を指定、--brain でローカル頭脳の素案も）
uv run python scripts/autonomous_candidates.py --at "2026-09-27 21:01" --brain --runs 3
# 上位タイプを飛ばして C / D の素案を試す
uv run python scripts/autonomous_candidates.py --kind D --brain --runs 3

# Lambda で試す（Buffer・ロック・履歴・状態に触れずメールだけ。通常の core_time 処理は走る）
aws lambda invoke --function-name imomaru-bot-handler --cli-binary-format raw-in-base64-out \
  --payload '{"execution_mode":"core_time","autonomous_allowed":true,"autonomous_dry_run":true}' /dev/stdout
```

**クレジット相殺の確認**（モデルカードに Marketplace 文言がない ＝ AWS 販売 ＝ クレジット対象。**Kimi K2.5 は 2026-09-19 に実請求で確認済み**:
09-12〜18 の `APN1-moonshotai.kimi-k2.5-{input,output}-tokens` は Usage $0.064 に対し Credit −$0.064 で全額相殺）:

```bash
# Kimi の USAGE_TYPE を Usage / Credit に分けて見る（Credit が Usage と同額の負数なら相殺されている）
aws ce get-cost-and-usage --region us-east-1 \
  --time-period Start=2026-09-12,End=2026-09-19 --granularity MONTHLY --metrics UnblendedCost \
  --filter '{"Dimensions":{"Key":"USAGE_TYPE","Values":["APN1-moonshotai.kimi-k2.5-input-tokens","APN1-moonshotai.kimi-k2.5-output-tokens"]}}' \
  --group-by Type=DIMENSION,Key=RECORD_TYPE
```

## 推しの記憶（AgentCore Memory）

検知した推しの投稿を Amazon Bedrock AgentCore Memory `imomaru_oshi_memory` に書き込み（フェーズ3a-write、2026-09-13）、
頭脳が反応を作るときに読み出します（フェーズ3a-read、2026-09-25）。
いも丸が「推しのことを覚える」ための記憶で、いも丸自身の人格（システムプロンプト）とは分離しています。

| 項目 | 内容 |
|------|------|
| リソース | CDK `CfnMemory`（`stack.py` の `_create_oshi_memory`）。削除時は保持（RETAIN）。イベント保持 365 日 |
| 戦略 | Semantic `/oshi/{actorId}/facts/`（事実）／ User Preference `/oshi/{actorId}/preferences/`（好み・口調）／ Episodic `/oshi/{actorId}/episodes/`（1 日 1 セッションのエピソード＋reflection） |
| 書き込み | `services/oshi_memory_writer.py`。actorId = 推しの X ユーザー名、sessionId = `oshi-YYYY-MM-DD`（JST）、role = USER、`clientToken` = tweet_id（冪等）。対象は `filter_original_posts` 後の推し投稿（引用ポスト含む） |
| 失敗時 | `[ERROR]` ログ（`imomaru-bot-app-errors` で検知）を出して握りつぶし、XP・Buffer・日報は続行。`OSHI_MEMORY_ID` が空なら書き込みなし |
| 読み出し（3a-read、2026-09-25） | 頭脳が `react` のたびに投稿本文をクエリに retrieve し（facts 上位 3 件 ＋ preferences 上位 2 件の `preference`）、user message の「推しの記憶」に入れる（`agent/brain.py:recall_oshi_memory`。Strands の `@tool` ではなく毎回決定論で注入）。「ユーザーは」で始まり「閲覧／転載／運営」を含むファン視点の誤抽出は除外。睡眠・体調など生活の細部（眠・寝・体調・病院 等を含むレコード。設計書 v19 のタイプ E）も除外。Runtime の環境変数 `OSHI_MEMORY_ID` / `OSHI_ACTOR_ID`、ロールは `RetrieveMemoryRecords` のみ |
| 独り言の材料（3b-1、2026-09-26） | Lambda が facts（2026-09-28 から preferences も）を `ListMemoryRecords` で一覧し、決定論で候補を選ぶ（`services/autonomous_selector.py`、下記「独り言」）。除外語・日付抽出は `memory_filters.py`（頭脳と共有。`agent/memory_filters.py` はシンボリックリンク） |
| 読み出し失敗時 | 記憶なしで反応を作り `memory_count=-1` を返す → Lambda が `[ERROR] Brain memory recall failed …`（アラーム）。反応自体は通常どおり Buffer に入る。Lambda ログの `Brain task=react … memories=N` で件数を確認できる |

```bash
MEM=$(aws cloudformation describe-stacks --stack-name ImomaruBotStack \
  --query "Stacks[0].Outputs[?OutputKey=='OshiMemoryId'].OutputValue" --output text)

# 今日書き込まれた推しの投稿（短期記憶）
aws bedrock-agentcore list-events --memory-id "$MEM" --actor-id juri_bigangel \
  --session-id "oshi-$(TZ=Asia/Tokyo date +%F)" --query 'events[].payload[0].conversational.content.text' --output text

# 抽出された長期記憶（事実／好み／エピソード）
for ns in facts preferences episodes; do
  aws bedrock-agentcore list-memory-records --memory-id "$MEM" --namespace "/oshi/juri_bigangel/$ns/" \
    --query 'memoryRecordSummaries[].content.text' --output text
done
```

運用上の注意（2026-09-13 の稼働初日に確認）:

- **イベントは削除・再投入しない**。長期記憶レコードと元イベントを削除して同じ sessionId に再投入しても再抽出されない（セッションごとに処理済み位置を持つと推定）。見出しや本文の形式を変えるときは、変更後の新しい投稿から効くものと考える
- **イベント本文の見出しは「本人の投稿」と書く**。`[推し @xxx の投稿]` のように書くと抽出器が USER ＝ 推しについて語るファンと解釈し、facts が「ユーザーの推し @xxx は…」、preferences が「ユーザーは @xxx を推している」のようにファン側の記憶として残る。現在の形式は `[@juri_bigangel（甘木ジュリ）本人の投稿 YYYY-MM-DD HH:MM JST]`
- **Episodic は会話タスク向けの抽出器**。推しの投稿だけを USER ロールで入れると「ユーザーが指示なしに投稿を貼り付けた」というエージェント視点の reflection になる。推しの記憶として読むのは facts / preferences を主にする
- 長期記憶戦略は Memory 作成時に全部入れておく。後から追加した戦略は追加前のイベントを処理しない
- **ファン視点のレコードが混ざる**（2026-09-14〜18 の実績）。本文がリンク主体の投稿（TikTok 共有）が入るたびに facts の「ユーザーは @juri_bigangel … を運営しており」が統合・更新され、preferences にも「ユーザーは … 閲覧・引用・転載」形式が出る。本人視点の facts（「甘木ジュリ（@juri_bigangel）は…」）は安定して抽出される。読み出し（3a-read）では「ユーザーは」で始まり「閲覧」「転載」「運営」を含むレコードを除外している（`agent/brain.py:_is_fan_view`）
- **睡眠・体調の記憶はプロンプトの指示だけでは本文に出る**（2026-09-25 のローカル確認で「朝の『よく眠れた』も嘘みたい」）。読み出し時にキーワードで除外している（`agent/brain.py:_PRIVATE_LIFE_WORDS`）。出来事と混ざったレコードも丸ごと落とす
