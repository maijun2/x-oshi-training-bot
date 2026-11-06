# Buffer の設定と運用

[← README に戻る](../README.md)

## Buffer API認証情報の設定

Buffer の Settings → API → Personal Access で発行した Personal Access Token と、投稿先チャンネルの ID を
`imomaru-bot/buffer-api` シークレットに格納します（値はチャット・ログ・リポジトリに出さないこと）。

```bash
# 値はファイル経由で渡す（シェル履歴に残さない）
cat > /tmp/buffer-secret.json <<'JSON'
{
  "access_token": "YOUR_BUFFER_PERSONAL_ACCESS_TOKEN",
  "channel_id": "YOUR_CHANNEL_ID",
  "organization_id": "YOUR_ORGANIZATION_ID"
}
JSON
aws secretsmanager put-secret-value \
  --secret-id imomaru-bot/buffer-api \
  --secret-string file:///tmp/buffer-secret.json \
  --region ap-northeast-1
rm /tmp/buffer-secret.json
```

`channel_id` / `organization_id` は Buffer GraphQL API（`POST https://api.buffer.com`、
`Authorization: Bearer <token>`）で `account { organizations { id } }` →
`channels(input: {organizationId: ...}) { id name service }` を実行して取得します。
参考: https://developers.buffer.com/guides/getting-started.html

**運用パラメータ（Lambda 環境変数、`stack.py` で設定）**

| 変数 | 初期値 | 意味 |
|------|--------|------|
| `BUFFER_RUN_CAP` | `2` | **主キャップ**。Lambda 1 回の実行で Buffer へ予約投入する上限件数。超えた分はメール素案のみ（X Intent リンクから手動投稿可）。各実行の検知分が均等に Buffer に載るよう「1日合計」ではなく「実行ごと」で数える。2026-09-25 に 1 → 2（02:00 枠の追加と同時） |
| `BUFFER_DAILY_CAP` | `7` | **安全弁**。1日の投入上限。スロット数/日（9）より小さくしてキューが必ず毎日減るようにし、Buffer 無料枠（キュー 10 件）を溢れさせない。`BUFFER_RUN_CAP` を上げるときはこの値とスロット数も見直す |
| `FROM_EMAIL` | `NOTIFICATION_EMAIL` と同じ | 素案メールの送信元。独自ドメインの認証後に `.env` で設定する（「デプロイ後の設定 1-c」） |
| `BUFFER_SLOT_TIMES_JST` | `02:00,08:00,11:15,12:15,14:15,15:15,19:15,20:15,22:00` | Buffer UI のスロット時刻（JST）の**名目値**。頭脳に渡す「公開予定時刻」（現在時刻の次の枠）の見込み計算にだけ使い、実際の予約時刻は Buffer が決める。実スロットは曜日ごとに名目値から ±数分ずらしてある（最大 12 分差）ので完全一致はしない。UI で枠の時間帯そのものを変えたら合わせる |
| `PUBLIC_ASSETS_BUCKET_NAME` | CDK が設定 | 感情画像の公開バケット（`imomaru-bot-public-assets-<account>`）。Buffer は**投稿公開時**に画像 URL を取りに来るため、署名付き URL ではなく公開 URL が必要 |

**Buffer 側のスロット設定（予約時刻は Buffer に任せる）**

- 投稿時刻はボット側で計算せず、Buffer チャンネルの posting schedule（スロット）に `addToQueue` で載せます。
  スロットは Buffer の Settings → Posting Schedule で変更でき、deploy 不要です
- レビュー猶予はスロットまでの時間です。スロットは**全曜日 9 枠**、名目値 `02:00 08:00 11:15 12:15 14:15 15:15 19:15 20:15 22:00` JST
  （2026-09-12 設定、2026-09-19 に 21:15 → 22:00。夜の実行 21:00 の追加に合わせた。2026-09-25 に 02:00（26:00）を追加。`BUFFER_RUN_CAP=2` と同時）。
  実際の UI 設定は機械的に見えないよう曜日ごとに名目値から ±数分ずらしてある（2026-09-19、下表）。設計原則は次の 2 つ:
  1. 各 Lambda 実行（10:00 / 13:00 / 18:00 / 21:00、flexible window はそれぞれ +15 / +23 / +3 / +5 分）の後、
     最初のスロットまで **レビュー猶予 50 分以上** を空ける
  2. 各実行の後、**当日中に `BUFFER_RUN_CAP`（2）枠以上**残す → 日中に検知した分が翌日に繰り越さない
     （23:58 実行の検知分は構造上、02:00 と翌 08:00 になる。21:00 実行の 2 件目は 02:00 に入る）

  02:00 の公開はレビューの時間外になるので、23:58 回の素案メールは寝る前に見る（NG なら Buffer UI で削除）

  | Lambda 実行（最遅） | 当日の残りスロット（名目） | 猶予（最悪ケース。実スロットの最短で計算） |
  |---|---|---|
  | 23:58（23:59） | 02:00 08:00〜 | 2 時間以上 |
  | 10:00（10:15） | 11:15 12:15 14:15 15:15 19:15 20:15 22:00 | 57 分（Mon 11:12） |
  | 13:00（13:23） | 14:15 15:15 19:15 20:15 22:00 | 54 分（Wed/Sat 14:17） |
  | 18:00（18:03） | 19:15 20:15 22:00 | 70 分（Fri 19:13） |
  | 21:00（21:05） | 22:00（2 件目は 02:00） | 56 分（Thu 22:01） |

  実スロット（Buffer UI、JST。名目値の行に対応）:

  | 名目 | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
  |---|---|---|---|---|---|---|---|
  | 02:00 | 02:01 | 02:03 | 02:01 | 02:03 | 02:05 | 02:02 | 02:06 |
  | 08:00 | 08:03 | 08:01 | 08:02 | 08:03 | 08:01 | 08:03 | 08:05 |
  | 11:15 | 11:12 | 11:20 | 11:14 | 11:23 | 11:17 | 11:19 | 11:16 |
  | 12:15 | 12:17 | 12:16 | 12:14 | 12:11 | 12:05 | 12:08 | 12:21 |
  | 14:15 | 14:21 | 14:24 | 14:17 | 14:20 | 14:18 | 14:17 | 14:20 |
  | 15:15 | 15:18 | 15:17 | 15:16 | 15:12 | 15:20 | 15:03 | 15:07 |
  | 19:15 | 19:16 | 19:18 | 19:17 | 19:14 | 19:13 | 19:20 | 19:18 |
  | 20:15 | 20:17 | 20:16 | 20:15 | 20:21 | 20:10 | 20:07 | 20:05 |
  | 22:00 | 22:04 | 22:02 | 22:03 | 22:01 | 22:04 | 22:02 | 22:05 |

  スロットをずらすときの上限: 原則 1 を守るため、11:xx は 11:05 より、14:xx は 14:13 より、19:xx は 18:53 より、22:xx は 21:55 より早くしない。
  `BUFFER_SLOT_TIMES_JST` は曜日別の値を持てないので名目値のまま。頭脳に渡す見込み時刻は最大 12 分ずれるが「HH:MM 頃」表現なので実害なし
  （名目値と実スロットの隙間に Lambda 実行時刻帯が掛からないことも確認済み）。

  Buffer はキューが空のスロットを素通りし、投入された投稿は「投入時点より後の最初の空き枠」に先着順で入ります。
  日報とレベルアップ告知は X API 直投稿で Buffer を通りません。Buffer に載るのは推し投稿への引用と独り言（URL なし）です。
  独り言も `BUFFER_RUN_CAP` / `BUFFER_DAILY_CAP` を推し投稿への反応と共有し、1 日 2 件まで・日次キャップのうち 2 件は反応用に残します（2026-09-28）
- スロット数/日（9）> `BUFFER_DAILY_CAP`（7）にしておくとキューが滞留しません（この不等式は崩さないこと）
- 実測（2026-08-13〜09-12 の 30 日）: 推しのオリジナル投稿は平均 6.6 件/日。実行別の平均は 10:00 → 2.3、13:00 → 1.0、
  18:00 → 0.7、23:58 → 2.7 件。`BUFFER_RUN_CAP=1` で実効 3 件/日程度だった。夜の実行 21:00 は 2026-09-19 に追加済み（18:00→23:58 の検知空白を埋める）。2026-09-25 に `BUFFER_RUN_CAP=2` ＋ 02:00 枠（当日中に残り枠 ≥ キャップ、9 枠 > 日次キャップの不等式は維持）
- スロットは Buffer の公開 API では変更できません（GraphQL は `Channel.postingSchedule` の読み取りのみ。
  旧 REST API は Public API トークンを拒否）。変更は Buffer の Web UI で行い、API で読み直して検証します。
  読み出しは `BufferClient._graphql` に次のクエリを投げる（`channel_id` はシークレットの値）:
  スロット `channel(input:{id}){postingSchedule{day times paused}}`（`times` は `"HH:MM"` の配列）、
  投稿の状態 `post(input:{id}){id status dueAt sentAt text}`（`status` は `sent` / `scheduled` 等。id はログの `Buffer post queued: id=…`）。
  この 2 つは `scripts/buffer_status.py` にまとめてある:

  ```bash
  uv run python scripts/buffer_status.py --from-logs 24   # 直近 24 時間に投入した投稿の状態・予約/送信時刻（JST）・本文
  uv run python scripts/buffer_status.py <post_id> ...    # post id を指定
  uv run python scripts/buffer_status.py --slots          # 曜日ごとのスロット（JST）
  ```
- 動作確認済み（2026-09-12）: Buffer 経由の投稿で感情画像が添付され、末尾の x.com URL は X 側で引用ポストとして展開される

**動作確認**

```bash
# 本番の Buffer キューに 1 件投入して post id / 予約時刻 / 画像コピー状況を表示
uv run python scripts/test_buffer_post.py --text "テストｲﾓ🍠" --tweet-id <推しの投稿ID> --emotion cheer
# 後片付け
uv run python scripts/test_buffer_post.py --delete <post_id>
```
