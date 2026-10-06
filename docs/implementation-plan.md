# 実装計画（詳細版・各単位を 10 サブステップに分解）

- 日付: 2026-10-07
- 状態: ドラフト（林さん確認待ち）
- 前提: ADR-0001〜0005。単位 ≈2h、サブステップ ≈10〜15 分
- スタック: **Python 3.12・標準ライブラリのみ**（sqlite3 / http.server /
  unittest。外部依存を増やさない＝ADR-0002 P9 の供給網方針と一致）

凡例: `x.y` = 単位 `x` のサブステップ `y`。最後のサブステップは
必ず「コミット（+ 許可済みなら push）」。

---

## フェーズ 0: スタック確定と骨格

### 0a. プロジェクト骨格（言語確定込み）

- [x] 0a.1 `warden/` パッケージ作成（`__init__.py`・`__main__.py`。
      ※計画では `src/warden/` だが、インストール不要で `python -m warden`
      が動くようリポジトリ直下に置いた）
- [x] 0a.2 `tests/` 作成・`unittest` が走る最小テストを書く
- [x] 0a.3 `config.py`: 管理対象ルート（`C:\Users\user\.claude`）・DB パス・
       quarantine パスを読む設定層
- [x] 0a.4 `logging` 設定（監査用に行動ログを残す形）
- [x] 0a.5 `.gitignore`: `__pycache__`、`*.db`、`secrets/`
- [x] 0a.6 CLI エントリ骨格（`python -m warden scan|list|apply` の空実装）
- [x] 0a.7 ADR 未決に「Python 3.12・stdlib のみ」を確定値として記録
- [x] 0a.8 HANDOFF にフェーズ 0 着手を記録
- [x] 0a.9 動作確認（`python -m warden` がヘルプを出す）
- [x] 0a.10 コミット + push

## フェーズ 1: パーサー（ADR-0002）

### 1a. 行分類器＋fixture 採取

- [x] 1a.1 fixture: `.claude` の git 管理 4 ファイルを `tests/fixtures/` に複製
- [x] 1a.2 fixture: untracked のルールファイルを数種追加（表・`@`・fence 混在）
- [x] 1a.3 行種別 enum（heading/bullet/numbered/table_row/fence_*/comment/import/quote/blank/text）
- [x] 1a.4 fence 状態機械（` ``` ` の開閉。中身は解析しない）
- [x] 1a.5 HTML コメント検出（`<!--` 〜 `-->`。中身は解析しない）
- [x] 1a.6 引用アーカイブ文の目印ルール（引用符・前後注記で除外）
- [x] 1a.7 表行検出（`|` で始まる行・区切り行の扱い）
- [x] 1a.8 `@` 参照の行内検出（行頭以外・表セル内も拾う）
- [x] 1a.9 行分類の単体テスト
- [x] 1a.10 コミット

### 1b. 条抽出（リーフ bullet 単位）

- [x] 1b.1 見出しツリー構築（`#` レベルで入れ子）
- [x] 1b.2 `heading_path` 生成（例: `核心ルール > 2. ...`）
- [x] 1b.3 bullet ネスト解析 → parent/leaf 判定（子は別条・親隔離は子同梱）
- [x] 1b.4 番号付きリストも同様に扱う
- [x] 1b.5 独立段落（見出し直下の非リスト文）を条に
- [x] 1b.6 `table_row` を条に（ヘッダ・区切り行は除く）
- [x] 1b.7 `import` 条（`@` 参照行）
- [x] 1b.8 `ordinal`（同見出し内の出現順）付与
- [x] 1b.9 条→行範囲対応（raw_text の正確な切り出し）
- [x] 1b.10 fixture 期待値テスト（条数・各条の行範囲）＋コミット

### 1c. 正規化・content_hash・ロードグラフ

- [x] 1c.1 正規化ルール（末尾空白・連続空白・改行コードの正規化方針を決める）
- [x] 1c.2 `content_hash` = sha256(正規化文) 先頭 16 hex
- [x] 1c.3 起点 `CLAUDE.md` をロードグラフの根に
- [x] 1c.4 `@` パス解決（相対・絶対・`~`）
- [x] 1c.5 表セル内の `@` を参照として拾う
- [x] 1c.6 到達 → `loaded=1`、未到達 → `loaded=0`
- [x] 1c.7 未到達ファイル一覧（準ルール `rules_junrule.md` 等も含める）
- [x] 1c.8 循環参照検出（`@` の輪）
- [x] 1c.9 ロードグラフの単体テスト
- [x] 1c.10 コミット

### 1d. 隔離/復元（物理移動・atomic）

- [x] 1d.1 隔離パス生成 `quarantine/<file>/<content_hash>.md`
- [x] 1d.2 frontmatter 生成（source_file/heading_path/ordinal/prev/next hash/reason）
- [x] 1d.3 行範囲の除去（対象行だけ削除・改行コード保存）
- [x] 1d.4 atomic 書き戻し（一時ファイルへ書いて rename）
- [x] 1d.5 親隔離時に子 bullet を同梱する包含処理
- [x] 1d.6 復元: frontmatter を読みアンカー（前後 hash）で挿入位置を決める
- [x] 1d.7 アンカー喪失時 → 見出し末尾へ退避＋「位置ずれあり」を記録
- [x] 1d.8 復元本文を差し替えられる I/F（サニタイズ版挿入の口・O10）
- [x] 1d.9 往復テスト（隔離→復元で元の配置に戻る。差分が最小）
- [x] 1d.10 コミット

### 1e. 出自（provenance）＋負例

- [x] 1e.1 git 履歴から初出コミット検出（`git log -S`/`-L`）
- [x] 1e.2 作者・コミット時刻の取得
- [x] 1e.3 非 git ファイルは fs 時刻フォールバック＋「履歴なし」記録
- [x] 1e.4 birth time 取れない環境での扱い（NULL＋note）
- [x] 1e.5 負例: fence 内の偽 bullet が条にならないこと
- [x] 1e.6 負例: 壊れた `@` 参照（存在しない先・循環）
- [x] 1e.7 負例: 空ファイル
- [x] 1e.8 負例: BOM / UTF-16 ファイル
- [x] 1e.9 出自表示の形（UI 出し方は後。データ形を確定）
- [x] 1e.10 負例が意図どおり失敗することを実測＋コミット

## フェーズ 2: WardenStore + Orchestrator

### 2a. DB 初期化＋条 upsert

- [x] 2a.1 `PRAGMA foreign_keys=ON`・`user_version` でスキーマ適用
- [x] 2a.2 `agents` upsert（local-claude）
- [x] 2a.3 `rule_files` upsert（path NOCASE・loaded・sha256）
- [x] 2a.4 `rule_units` upsert（自然キー file+hash+heading_path）
- [x] 2a.5 present 差分（消えた条 → `present=0`）
- [x] 2a.6 succession 検出の枠（旧→新の対応付け口）
- [x] 2a.7 `provenance` 書込
- [x] 2a.8 `criteria`/`score_runs`/`score_details` 書込の枠
- [x] 2a.9 DDL 負例テスト再現（CHECK/UNIQUE/FK が効くことを確認）
- [x] 2a.10 コミット

### 2b. ステータス・推奨・判断

- [x] 2b.1 `status_history` append（最新行=現状態）
- [x] 2b.2 遷移表の実装＋許可外遷移をエラーに
- [x] 2b.3 「AI 単独は provisional_ai / quarantined のみ」を検査
- [x] 2b.4 `recommendations`/`decisions` 書込（決定→同時に status_history）
- [x] 2b.5 `provisional_records`（reason・outcome/confirmed_at ペア）
- [x] 2b.6 `current_status` VIEW
- [x] 2b.7 `audit_log` 書込フック（全状態変化）
- [x] 2b.8 `settings` get/set（`bypass_mode` 等）
- [x] 2b.9 遷移・ペア制約のテスト
- [x] 2b.10 コミット

### 2c. Orchestrator（段取り・暫定適用・隔離実行）

- [x] 2c.1 `scan()`: parse→upsert→新旧差分検出
- [x] 2c.2 採点呼出 → `Recommendation` 保存（スタブ採点で先に通す）
- [x] 2c.3 暫定適用: `provisional_ai`＋`ProvisionalRecord`（いつ・なぜ）
- [x] 2c.4 隔離実行: RE の物理移動＋`隔離:` コミット＋`quarantined`
- [x] 2c.5 `bypass_mode=ON` 時は推奨どおり直確定
- [x] 2c.6 「確実に質問して」検知 → `questions` へ（例外的経路）
- [x] 2c.7 `AdrRecorder`: 暫定承認の根拠を warden 側 ADR に記録
- [x] 2c.8 `audit_log` 一貫記録
- [x] 2c.9 scan→採点→暫定→隔離の E2E 統合テスト
- [x] 2c.10 コミット

### 2d. 質問キュー＋要確認一覧クエリ

- [x] 2d.1 `questions` enqueue（同時 1 問のアプリ層強制）
- [x] 2d.2 タイムアウト監視（`timeout_at` 超過→`timed_out`）
- [x] 2d.3 回答の反映（`answered`→StatusChange 確定）
- [x] 2d.4 `timed_out` → 暫定承認せず要確認へ留まる
- [x] 2d.5 一覧クエリ: `provisional_ai`＋`confirmed_at IS NULL` の条
- [x] 2d.6 直近 `score_runs` 結合 → 危険度順ソート
- [x] 2d.7 準ルール条（`rules_junrule.md`）を union で混ぜる
- [x] 2d.8 出所バッジ用フラグ（隔離/準ルールの区別）
- [x] 2d.9 一覧クエリのテスト（件数・順序・union）
- [x] 2d.10 コミット

## フェーズ 3: AiGateway（D8・O7）

### 3a. 抽象＋モック採点

- [x] 3a.1 `call_scorer`/`call_reviewer`/`call_sanitizer` の I/F 定義
- [x] 3a.2 `ai_profiles` から scorer/reviewer を解決（別系統の確認）
- [x] 3a.3 モック採点器（固定 or 簡易ヒューリスティックで点数を出す）
- [x] 3a.4 `score_runs`+`score_details`+`recommendations` の書込結線
- [x] 3a.5 `rationale`（人が検査できる根拠文）の形を確定
- [x] 3a.6 エラー/タイムアウト時の扱い（リトライ方針）
- [x] 3a.7 呼出し記録（いつ・どのモデル・所要時間）
- [x] 3a.8 モックで scan→採点→暫定の E2E
- [x] 3a.9 モック採点のテスト
- [x] 3a.10 コミット

### 3b. 実 AI 接続（契約済み・別系統・期限監視）

- [x] 3b.1 接続方式の選定（MCP or API。契約中サービスを調査して決める）
- [x] 3b.2 scorer モデルの選定・`ai_profiles` 登録
- [x] 3b.3 reviewer モデルの選定・登録（別系統＝別ベンダー優先）
- [x] 3b.4 `credential_ref` の取り方（env/ファイル参照。値は置かない）
- [x] 3b.5 `expires_at` 登録
- [x] 3b.6 期限切れ監視（期限接近→要確認・切れ→採点を止めて通知）
- [x] 3b.7 実呼出の疎通テスト（1 条を採点してみる）
- [x] 3b.8 レート/リトライ/バックオフ
- [x] 3b.9 プロンプトテンプレ（採点・審査・サニタイズ各種）
- [x] 3b.10 コミット

### 3c. サニタイズ＋PR 審査

- [x] 3c.1 本来意図推定: git 履歴の旧版を取得
- [x] 3c.2 採点根拠と照合して「危ない部分」を特定
- [x] 3c.3 sanitize プロンプト → 本来意図に整えた代替文を生成
- [x] 3c.4 整え前後の差分（before/after）生成
- [x] 3c.5 `unit_succession.method='sanitize'` で新旧対応を記録
- [x] 3c.6 意図が読めない条は戻さず要確認へ（仮の決定どおり）
- [x] 3c.7 PR 審査プロンプト → `verdict`（approve/request_changes/escalate）
- [x] 3c.8 `escalate` 判定（まとまらない場合は自動マージしない）
- [x] 3c.9 サニタイズ差分・審査 verdict のテスト
- [x] 3c.10 コミット

## フェーズ 4: Web UI（D7・サーバ・クライアント型）

### 4a. API エンドポイント

- [ ] 4a.1 `http.server` ベースの起動/停止（オンデマンド起動方針）
- [ ] 4a.2 `GET /api/units`（status フィルタ）
- [ ] 4a.3 `GET /api/review-queue`（要確認・危険度順）
- [ ] 4a.4 `GET /api/units/{id}` 詳細＋差分（サニタイズ前後）
- [ ] 4a.5 `POST /api/decisions`（確定/覆し）
- [ ] 4a.6 `POST /api/settings`（bypass_mode 切替）
- [ ] 4a.7 `POST /api/scan`（手動スキャン起動）
- [ ] 4a.8 `POST /api/questions/{id}/answer`
- [ ] 4a.9 エラーハンドリングと JSON 応答の形
- [ ] 4a.10 curl で疎通確認＋コミット

### 4b. 一覧画面（統合表示）

- [ ] 4b.1 `index.html` 骨格（最小の HTML/JS。フレームワークなし）
- [ ] 4b.2 一覧表示（条・出所・スコア・ステータス）
- [ ] 4b.3 危険度順ソート＋他列でも並べ替え
- [ ] 4b.4 出所バッジ（隔離/準ルール/新規の区別）
- [ ] 4b.5 サニタイズ差分の表示（整え前→後）
- [ ] 4b.6 チェック → 確定/覆しの操作
- [ ] 4b.7 復元/隔離ボタン
- [ ] 4b.8 空状態・エラー表示
- [ ] 4b.9 手動で一覧を操作して確認
- [ ] 4b.10 コミット

### 4c. 要確認・質問・バイパス画面

- [ ] 4c.1 要確認タブ（暫定承認の溜まり場）
- [ ] 4c.2 暫定承認の「いつ・なぜ」を表示
- [ ] 4c.3 質問表示（1 問・回答フォーム）
- [ ] 4c.4 タイムアウト表示
- [ ] 4c.5 bypass ON/OFF トグル
- [ ] 4c.6 推奨精度の参考表示（一致率）
- [ ] 4c.7 `ai_profiles` の期限警告表示
- [ ] 4c.8 未確認残数の表示
- [ ] 4c.9 手動で一巡操作確認
- [ ] 4c.10 コミット

## フェーズ 5: 初期運用リハーサル（D4）

### 5a. `.claude` コピーでドライラン

- [ ] 5a.1 `.claude` を作業ディレクトリへフルコピー（本番を触らない）
- [ ] 5a.2 コピー上で全件隔離を実行
- [ ] 5a.3 コピー上で全件採点（モック→実 AI）
- [ ] 5a.4 コピー上でサニタイズ生成
- [ ] 5a.5 コピー上で暫定復元
- [ ] 5a.6 要確認一覧の表示確認
- [ ] 5a.7 異常検出・ログ解析
- [ ] 5a.8 `git diff` で差分を目視
- [ ] 5a.9 問題点をリスト化して直す
- [ ] 5a.10 記録・コミット

### 5b. 本番適用＋初回レビュー

- [ ] 5b.1 本番 `.claude` のバックアップ確認（Forgejo push 済みを再確認）
- [ ] 5b.2 本番で全件隔離を実行
- [ ] 5b.3 本番で採点＋サニタイズ
- [ ] 5b.4 本番で暫定復元
- [ ] 5b.5 要確認一覧を林さんに見てもらう
- [ ] 5b.6 確定/覆しの反映
- [ ] 5b.7 初回運用メモ作成
- [ ] 5b.8 HANDOFF を現状に更新
- [ ] 5b.9 ADR-0002〜0004 をドラフト→承認済みに格上げ
- [ ] 5b.10 記録・コミット・push

---

## 集計

- 単位 13（0a/1a〜1e/2a〜2d/3a〜3c/4a〜4c/5a〜5b）
- サブステップ 130
- マイルストーン: M1=1e 完了 / M2=2d 完了 / M3=3c 完了 / M4=5b 完了
