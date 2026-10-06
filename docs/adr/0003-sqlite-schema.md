# ADR-0003: SQLite スキーマ設計（承認ステータス・判断履歴）

- 日付: 2026-10-06
- 状態: ドラフト（林さんレビュー待ち）
- 記録者: Devin
- 上位決定: ADR-0001 D3（推奨 vs 最終判断の記録）・D6（承認ステータス・質問キュー）・D7（管理対象＝エージェント概念）

## 目的

条の承認ステータス・スコア・AI 推奨と最終判断の履歴・質問キューを
SQLite に永続化する。D3 の「推奨精度の実測」と D6 の「暫定承認の追跡」が
このスキーマの存在理由。

## 用語

| 用語 | 意味 |
|---|---|
| status の値 | `approved`=承認済み / `provisional_ai`=暫定 AI 承認 / `under_review`=審査中 / `quarantined`=隔離 / `rejected`=却下（ADR-0001 D6 と対応） |
| `decided_by` の `ai:<model>` | AI による判断。コロンの後にモデル識別子を入れる（例: `ai:gpt-5`）。人間は `human` |
| score_runs / score_details | 採点 AI による 1 回の採点実行と、その評価項目別の内訳 |
| criteria | 評価項目。合計 100 点になるよう重み付けする（ADR-0001 D2） |
| 推奨精度 | recommendations（AI の推奨）と decisions（最終判断）の一致率。バイパスモード移行の判定材料（ADR-0001 D3） |
| VIEW（`current_status`） | クエリを名前付きで保存した仮想テーブル。「各条の最新ステータス」を返す想定 |
| UTC / ISO8601 | 協定世界時 / 日時表記の国際標準。DB は UTC で保存し、表示側で JST に変換する |
| 暫定 AI 承認 | 林さん不在時に AI が暫定的に承認した状態。戻ったときに要確認一覧へ上げる（ADR-0001 D6） |

## 設計方針

- **ステータスは履歴テーブル**。最新行が現状態。変更理由と共に全履歴を残す
  （「いつ・誰が・なぜ」その状態にしたかを遡れるようにする）
- **推奨と決定を別々に記録**し、一致率から推奨精度を算出する（D3）
- **条の実体はハッシュ参照**。ファイル内容が変われば別条になるため、
  条テーブルは「現在のスナップショット」と「観測履歴」を分ける
- 将来の複数拠点管理に備え、全データを `agent_id` ぶら下げにする（D7）

## テーブル定義

```sql
-- 管理対象（現要件では localhost の .claude 1 件）
CREATE TABLE agents (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,      -- 例: "local-claude"
  root_path   TEXT NOT NULL,             -- 例: "C:\Users\user\.claude"
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ルールファイル（出自判定の基点）
CREATE TABLE rule_files (
  id           INTEGER PRIMARY KEY,
  agent_id     INTEGER NOT NULL REFERENCES agents(id),
  path         TEXT NOT NULL,            -- 例: "CLAUDE.md"
  git_tracked  INTEGER NOT NULL,         -- 0/1: 出自情報の取り方が変わる
  loaded       INTEGER NOT NULL,         -- 0/1: @グラフ到達可否
  sha256       TEXT,                     -- 前回スキャン時の内容ハッシュ
  mtime        TEXT,
  UNIQUE(agent_id, path)
);

-- 条の現在スナップショット（最新スキャン状態）
CREATE TABLE rule_units (
  id            INTEGER PRIMARY KEY,
  file_id       INTEGER NOT NULL REFERENCES rule_files(id),
  content_hash  TEXT NOT NULL,           -- ADR-0002 P3: sha256(norm_text) 先頭16
  heading_path  TEXT NOT NULL,           -- 文脈（例 "核心ルール > 2. ..."）
  ordinal       INTEGER NOT NULL,        -- 同見出し内での出現順
  parent_id     INTEGER REFERENCES rule_units(id),  -- 親 bullet（P2 包含用）
  kind          TEXT NOT NULL,           -- bullet/numbered/paragraph/table_row/import
  raw_text      TEXT NOT NULL,           -- 原文（改行含む）
  first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen_at  TEXT NOT NULL DEFAULT (datetime('now')),
  present       INTEGER NOT NULL DEFAULT 1   -- 0=ファイルから消えた（編集/隔離済）
);
CREATE INDEX idx_units_hash ON rule_units(content_hash);
CREATE INDEX idx_units_file ON rule_units(file_id, present);

-- 出自（P5 の 2 系統を1テーブルで）
CREATE TABLE provenance (
  id          INTEGER PRIMARY KEY,
  unit_id     INTEGER NOT NULL REFERENCES rule_units(id),
  source_kind TEXT NOT NULL,             -- 'git' | 'fs'
  commit_sha  TEXT,                      -- git のみ: 初出コミット
  committed_at TEXT,
  author      TEXT,
  fs_created  TEXT,                      -- fs のみ
  fs_modified TEXT,
  note        TEXT                       -- 「履歴なし」等
);

-- 承認ステータス履歴（最新行が現状態）
-- status: approved / provisional_ai / under_review / quarantined / rejected
CREATE TABLE status_history (
  id         INTEGER PRIMARY KEY,
  unit_id    INTEGER NOT NULL REFERENCES rule_units(id),
  status     TEXT NOT NULL CHECK(status IN
               ('approved','provisional_ai','under_review','quarantined','rejected')),
  decided_by TEXT NOT NULL,              -- 'human' | 'ai:<model>' 
  reason     TEXT,
  adr_ref    TEXT,                       -- 暫定承認の根拠 ADR パス（D6）
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_status_unit ON status_history(unit_id, created_at);

-- 評価項目（合計100点、Web検索で定期更新。D2）
CREATE TABLE criteria (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  description TEXT,
  weight      INTEGER NOT NULL,          -- 合計100になるよう管理
  source      TEXT,                      -- 例: "DarkBench ICLR2025"
  active_from TEXT NOT NULL DEFAULT (datetime('now')),
  active_to   TEXT                       -- NULL=現行。項目更新は差し替えで残す
);

-- 採点実行（1回の採点=1行、内訳は子テーブル）
CREATE TABLE score_runs (
  id            INTEGER PRIMARY KEY,
  unit_id       INTEGER NOT NULL REFERENCES rule_units(id),
  scorer        TEXT NOT NULL,           -- 採点AI識別子（交代可・D8）
  model_version TEXT,
  total_score   INTEGER NOT NULL,        -- 0-100
  rationale     TEXT NOT NULL,           -- 人が検査できる採点根拠（D2）
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE score_details (
  id           INTEGER PRIMARY KEY,
  score_run_id INTEGER NOT NULL REFERENCES score_runs(id),
  criterion_id INTEGER NOT NULL REFERENCES criteria(id),
  score        INTEGER NOT NULL,
  evidence     TEXT                      -- 条内の該当箇所の引用
);

-- 推奨 vs 最終判断（D3 精度実測の根拠）
CREATE TABLE recommendations (
  id            INTEGER PRIMARY KEY,
  unit_id       INTEGER NOT NULL REFERENCES rule_units(id),
  score_run_id  INTEGER REFERENCES score_runs(id),
  recommended_status TEXT NOT NULL,      -- AI の推奨
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE decisions (
  id                INTEGER PRIMARY KEY,
  recommendation_id INTEGER NOT NULL REFERENCES recommendations(id),
  final_status      TEXT NOT NULL,       -- 林さんの最終決定
  agreed            INTEGER NOT NULL,    -- 1=推奨どおり 0=覆した（精度算出）
  decided_by        TEXT NOT NULL DEFAULT 'human',
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 林質問キュー（D6: 1問ずつ・平易・タイムアウト付き）
CREATE TABLE questions (
  id          INTEGER PRIMARY KEY,
  unit_id     INTEGER REFERENCES rule_units(id),  -- 関係する条（あれば）
  question    TEXT NOT NULL,             -- 林質問ルール準拠の文
  status      TEXT NOT NULL DEFAULT 'pending'
              CHECK(status IN ('pending','answered','timed_out','cancelled')),
  timeout_at  TEXT NOT NULL,
  answer      TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  answered_at TEXT
);

-- 暫定承認の記録（不在時に先行追加した経緯。D6）
CREATE TABLE provisional_records (
  id          INTEGER PRIMARY KEY,
  unit_id     INTEGER NOT NULL REFERENCES rule_units(id),
  question_id INTEGER REFERENCES questions(id),  -- タイムアウトした質問
  request_ref TEXT NOT NULL,             -- 「進めてほしい依頼」の識別
  adr_path    TEXT NOT NULL,             -- 暫定ルールを記録した ADR
  confirmed   INTEGER NOT NULL DEFAULT 0, -- 林さんが要確認一覧で確認済みか
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 追加フロー: Forgejo PR と審査（D5）
CREATE TABLE pull_requests (
  id           INTEGER PRIMARY KEY,
  agent_id     INTEGER NOT NULL REFERENCES agents(id),
  forgejo_repo TEXT NOT NULL,
  pr_number    INTEGER NOT NULL,
  proposer     TEXT NOT NULL,            -- 'human' | 'ai:<model>'
  state        TEXT NOT NULL DEFAULT 'open'
               CHECK(state IN ('open','merged','rejected','escalated')),
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(forgejo_repo, pr_number)
);
CREATE TABLE reviews (
  id          INTEGER PRIMARY KEY,
  pr_id       INTEGER NOT NULL REFERENCES pull_requests(id),
  reviewer    TEXT NOT NULL,             -- 審査AI識別子（採点AIと別系統・D5）
  verdict     TEXT CHECK(verdict IN ('approve','request_changes','escalate')),
  comment     TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 監査ログ（全状態変化の裏取り）
CREATE TABLE audit_log (
  id         INTEGER PRIMARY KEY,
  actor      TEXT NOT NULL,              -- 'human' | 'ai:<model>' | 'system'
  action     TEXT NOT NULL,              -- quarantine/restore/status_change/...
  entity     TEXT NOT NULL,              -- 'rule_unit' | 'question' | ...
  entity_id  INTEGER NOT NULL,
  payload    TEXT,                       -- JSON 詳細
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## 補足

- **現状態の取得**: `status_history` の unit ごとの最新行。VIEW
  `current_status` を作って UI から使う想定
- **条が編集で別条になった場合**: 旧 `rule_units.present=0`、新条が新 id で登場。
  ステータスの引き継ぎは「同 file+heading_path で content_hash が近い」
  対応付け後に行う（対応付けロジックは ADR-0002 未決事項と連動）
- **criteria の改版**: `active_to` を立てて差し替え。過去スコアとの
  比較可能性を保つため項目を物理削除しない
- SQLite の日時は UTC ISO8601 文字列（`datetime('now')`）。表示側で JST 変換

## 未決の細部

- 推奨精度の集計期間・バイパスモード移行の閾値（D3 の運用値）
- `decisions.agreed` を自動算出するか手動記録するか（推奨と最終の一致比較で
  自動算出可。ただし「推奨に無い判断」も記録できる形は残す）
- 質問タイムアウトの初期値（ADR-0001 未決事項と同じ）
