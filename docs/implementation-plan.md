# 実装計画（1 単位 ≈ 2 時間粒度）

- 日付: 2026-10-07
- 状態: ドラフト（林さん確認待ち）
- 前提: ADR-0001〜0005。各単位 ≈ 2 時間 ≈ 1〜2 コミット
- スタック: **Python 3.12・標準ライブラリのみ**（sqlite3 / http.server /
  unittest。外部依存を増やさない＝ADR-0002 P9 の供給網方針と一致）

## フェーズ 0: スタック確定と骨格

| # | 作業 | 成果物 | 解消する仮の決定 |
|---|---|---|---|
| 0a | プロジェクト骨格（src/ 配置・テストランナー・設定読込）。言語を Python に確定し ADR 未決欄に記録 | `src/warden/` 空パッケージ・`pytest` ではなく `unittest` の最小基盤 | 言語・スタック |

## フェーズ 1: パーサー（ADR-0002 の実装）

| # | 作業 | 成果物 | 検証 |
|---|---|---|---|
| 1a | 行分類器（見出し/bullet/番号付き/表/fence/コメント/引用）＋ `.claude` 現行ファイル群を fixture として採取 | `parser_lines.py`・`tests/fixtures/` | 行分類の単体テスト |
| 1b | 条抽出（リーフ bullet・段落・表行・`@`参照を条に。parent 包含・heading_path・ordinal 付与） | `parser_units.py` | fixture で条数・行範囲を固定テスト |
| 1c | 正規化＋content_hash＋ロードグラフ（CLAUDE.md 起点・`@` を表セル内も拾う） | `parser_hash.py`・`loadgraph.py` | ロード到達=loaded 判定テスト |
| 1d | 隔離/復元（1 条 1 ファイル＋frontmatter・アンカー挿入・atomic 書き戻し・行範囲除去） | `quarantine.py` | 往復テスト（隔離→復元で元の配置） |
| 1e | 出自（git 履歴 or fs 時刻）＋負例（fence 内偽 bullet・壊れた `@`・空・BOM/UTF-16） | `provenance.py` | 負例が意図どおり失敗することを実測 |

解消: Rule-Unit trailer 自動挿入・非ロード棚卸し・succession 対応付け・ロールバック

## フェーズ 2: WardenStore + Orchestrator（ADR-0003/0002.5）

| # | 作業 | 成果物 | 検証 |
|---|---|---|---|
| 2a | DDL 適用（PRAGMA fk=ON・user_version）＋ agents/rule_files/rule_units upsert（present/hash・succession 記録） | `store.py` | DDL 負例テストの再現 |
| 2b | status_history 書込＋遷移検査（アプリ層）・current_status VIEW・provisional_records | `store_status.py` | 許可外遷移がエラーになる |
| 2c | Orchestrator: scan→採点スタブ→暫定適用→隔離実行→audit_log・settings(bypass_mode) | `orchestrator.py` | 一連を統合テスト |
| 2d | questions（1問・タイムアウト）＋要確認一覧クエリ（quarantine∪準ルール・危険度順） | `questions.py`・`views.py` | ソート順・union の確認 |

解消: 状態遷移アプリ層強制・PR 適用トランザクション・タイムアウト初期値・Orchestrator 依存形

## フェーズ 3: AiGateway（D8・O7）

| # | 作業 | 成果物 | 検証 |
|---|---|---|---|
| 3a | AiGateway 抽象＋モック採点（スタブ。score_runs/recommendations 書込） | `ai_gateway.py`（protocol 切替可能な形） | モックで E2E 通す |
| 3b | 実 AI 接続（契約済みサービスの API or MCP・ai_profiles 登録・期限切れ監視） | `ai_profiles` 運用・`expiry watch` | 期限切れ検知テスト |
| 3c | サニタイズ生成（本来意図に整えた版）＋審査 AI（PR verdict ループ） | `sanitize.py`・`reviewer.py` | サニタイズ差分が出る |

解消: AiGateway プロトコル・別系統モデル登録・期限監視

## フェーズ 4: Web UI（サーバ・クライアント型・D7）

| # | 作業 | 成果物 | 検証 |
|---|---|---|---|
| 4a | API エンドポイント（一覧 JSON・操作 POST。stdlib http.server ベース） | `api.py` | curl で一覧取得 |
| 4b | 一覧画面（統合表示・危険度ソート・差分表示・チェック操作） | `ui/`（最小 HTML/JS） | 一覧が quarantine∪準ルールを出す |
| 4c | 要確認/質問画面＋bypass_mode 切替 UI | `ui/` 追加ページ | ON/OFF が settings に書かれる |

## フェーズ 5: 初期運用リハーサル（D4）

| # | 作業 | 成果物 | 検証 |
|---|---|---|---|
| 5a | .claude の**コピー**で全件隔離→採点→サニタイズ→暫定復元をドライラン | 試行結果ログ | 壊れないか確認 |
| 5b | 本番適用＋初回の要確認一覧レビューを林さんと | 初回運用メモ | 一覧が見やすいか |

## マイルストーン

- **M1（フェーズ1 完了）**: 条抽出・隔離/復元が実データで往復する
- **M2（フェーズ2 完了）**: 採点スタブのまま一連の流れが E2E で動く
- **M3（フェーズ3 完了）**: 実 AI で採点・サニタイズ・PR 審査が動く
- **M4（フェーズ4〜5）**: 一覧で運用可能・初期デコンタミ実行

## 未解消で残るもの（実装後に調整）

- 件名の言語・`(proposal)`→`[暫定]` の表記統一（コミット運用開始時に合わせる）
- 質問タイムアウト初期値（運用で調整）
- 別条対応付けの類似度アルゴリズム（実データを見て決める）

## 見積り

13 単位 × ≈2h ≈ **26 時間**の規模（±大きく振れうる。
パーサーの fixture 精緻化と AI 連携の接続方式が不確定要素）。
