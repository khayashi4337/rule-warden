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
-- SQLite の外部キーは既定で無効。接続ごとに必須:
--   PRAGMA foreign_keys = ON;
-- スキーマバージョンは PRAGMA user_version で管理し、
-- 変更はマイグレーション履歴として残す。

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
  path         TEXT NOT NULL COLLATE NOCASE,  -- Windows FS は大小区別しない
               -- 例: "CLAUDE.md"
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
  kind          TEXT NOT NULL CHECK(kind IN
                  ('bullet','numbered','paragraph','table_row','import')),
  raw_text      TEXT NOT NULL,           -- 原文（改行含む）
  first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen_at  TEXT NOT NULL DEFAULT (datetime('now')),
  present       INTEGER NOT NULL DEFAULT 1,  -- 0=ファイルから消えた（編集/隔離済）
  -- 条の実体キー（ADR-0002 P3: file+heading_path+hash）。再スキャンの二重登録防止。
  -- 注意: 同じ見出しの下に全く同じ文の bullet が2つある場合は区別できない
  -- （実データで起きたら ordinal をキーに含める等の再検討）
  UNIQUE(file_id, content_hash, heading_path)
);
CREATE INDEX idx_units_hash ON rule_units(content_hash);
CREATE INDEX idx_units_file ON rule_units(file_id, present);

-- 編集・改名で「別条」になったときの旧→新の対応付け（設計方針の観測履歴）
CREATE TABLE unit_succession (
  id           INTEGER PRIMARY KEY,
  prev_unit_id INTEGER NOT NULL REFERENCES rule_units(id),
  new_unit_id  INTEGER NOT NULL REFERENCES rule_units(id),
  method       TEXT NOT NULL,            -- 'similarity' | 'rule_unit_trailer'（ADR-0004 C6）
  confidence   REAL,                     -- similarity の場合の類似度
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(prev_unit_id, new_unit_id)
);

-- 出自（P5 の 2 系統を1テーブルで）
CREATE TABLE provenance (
  id          INTEGER PRIMARY KEY,
  unit_id     INTEGER NOT NULL UNIQUE REFERENCES rule_units(id),
  source_kind TEXT NOT NULL,             -- 'git' | 'fs'
  commit_sha  TEXT,                      -- git のみ: 初出コミット
  committed_at TEXT,
  author      TEXT,
  fs_created  TEXT,                      -- fs のみ。birth time が取れない環境では NULL
  fs_modified TEXT,
  note        TEXT                       -- 「履歴なし」「fs時刻は参考値」等
);

-- 承認ステータス履歴（最新行が現状態）
-- status: approved / provisional_ai / under_review / quarantined / rejected
CREATE TABLE status_history (
  id         INTEGER PRIMARY KEY,
  unit_id    INTEGER NOT NULL REFERENCES rule_units(id),
  status     TEXT NOT NULL CHECK(status IN
               ('approved','provisional_ai','under_review','quarantined','rejected')),
  decided_by TEXT NOT NULL CHECK(decided_by = 'human' OR decided_by LIKE 'ai:%'),
  reason     TEXT,
  adr_ref    TEXT,                       -- 暫定承認の根拠 ADR パス（D6）
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_status_unit ON status_history(unit_id, id);  -- 最新行取得は id 順（補足参照）

-- 評価項目（合計100点、Web検索で定期更新。D2）
CREATE TABLE criteria (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  description TEXT,
  weight      INTEGER NOT NULL CHECK(weight BETWEEN 0 AND 100),
               -- active な項目の合計=100 はアプリ層で保証（CHECK では表せない）
  source      TEXT,                      -- 例: "DarkBench ICLR2025"
  active_from TEXT NOT NULL DEFAULT (datetime('now')),
  active_to   TEXT                       -- NULL=現行。項目更新は差し替えで残す
);

-- 採点実行（1回の採点=1行、内訳は子テーブル）
CREATE TABLE score_runs (
  id            INTEGER PRIMARY KEY,
  unit_id       INTEGER NOT NULL REFERENCES rule_units(id),
  scorer        TEXT NOT NULL CHECK(scorer LIKE 'ai:%'),  -- 採点AI識別子（交代可・D8）
  model_version TEXT,
  total_score   INTEGER NOT NULL CHECK(total_score BETWEEN 0 AND 100),
  rationale     TEXT NOT NULL,           -- 人が検査できる採点根拠（D2）
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE score_details (
  id           INTEGER PRIMARY KEY,
  score_run_id INTEGER NOT NULL REFERENCES score_runs(id),
  criterion_id INTEGER NOT NULL REFERENCES criteria(id),
  score        INTEGER NOT NULL CHECK(score >= 0),  -- 上限は criterion.weight
  evidence     TEXT,                     -- 条内の該当箇所の引用
  UNIQUE(score_run_id, criterion_id)     -- 同一項目の二重採点を防ぐ
);

-- 推奨 vs 最終判断（D3 精度実測の根拠）
CREATE TABLE recommendations (
  id            INTEGER PRIMARY KEY,
  unit_id       INTEGER NOT NULL REFERENCES rule_units(id),
  score_run_id  INTEGER REFERENCES score_runs(id),
  recommended_status TEXT NOT NULL CHECK(recommended_status IN
                  ('approved','provisional_ai','under_review','quarantined','rejected')),
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE decisions (
  id                INTEGER PRIMARY KEY,
  recommendation_id INTEGER NOT NULL REFERENCES recommendations(id),
  final_status      TEXT NOT NULL CHECK(final_status IN
                      ('approved','provisional_ai','under_review','quarantined','rejected')),
  -- 推奨との一致は recommended_status = final_status で算出（列は持たない。
  -- 保存すると矛盾した行を許容するため）
  decided_by        TEXT NOT NULL DEFAULT 'human'
                    CHECK(decided_by = 'human' OR decided_by LIKE 'ai:%'),
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 林質問キュー（D6: 1問ずつ・平易・タイムアウト付き）
CREATE TABLE questions (
  id          INTEGER PRIMARY KEY,
  unit_id     INTEGER REFERENCES rule_units(id),  -- 関係する条（あれば）
  retry_of    INTEGER REFERENCES questions(id),  -- タイムアウト後の再質問元
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
  outcome     TEXT CHECK(outcome IN ('confirmed','reverted','modified')),
  confirmed_at TEXT,                     -- 林さんが確認した日時（NULL=未確認）
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  -- outcome と confirmed_at は必ずペア（片方だけ入る矛盾を防ぐ）。
  -- テーブル制約は全列定義の後でないと SQLite がエラーにするので末尾に置く
  CHECK((outcome IS NULL) = (confirmed_at IS NULL))
);

-- 追加フロー: Forgejo PR と審査（D5）
CREATE TABLE pull_requests (
  id           INTEGER PRIMARY KEY,
  agent_id     INTEGER NOT NULL REFERENCES agents(id),
  forgejo_repo TEXT NOT NULL,
  pr_number    INTEGER NOT NULL,
  proposer     TEXT NOT NULL CHECK(proposer = 'human' OR proposer LIKE 'ai:%'),
  state        TEXT NOT NULL DEFAULT 'open'
               CHECK(state IN ('open','merged','rejected','escalated')),
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(forgejo_repo, pr_number)
);
-- PR が提案する条（ファイルに未適用のものも含む。審査対象の実体）
CREATE TABLE proposed_units (
  id             INTEGER PRIMARY KEY,
  pr_id          INTEGER NOT NULL REFERENCES pull_requests(id),
  action         TEXT NOT NULL CHECK(action IN ('add','modify','remove')),
  file_path      TEXT NOT NULL COLLATE NOCASE,  -- 追加/変更先
  heading_path   TEXT,
  raw_text       TEXT NOT NULL,          -- 提案条の本文（未適用なので rule_units には無い）
  norm_hash      TEXT,
  target_unit_id INTEGER REFERENCES rule_units(id),  -- modify/remove の対象既存条
  applied_unit_id INTEGER REFERENCES rule_units(id), -- マージ適用でできた条（追跡用）
  -- add は target 必須でない、modify/remove は target 必須
  CHECK((action = 'add' AND target_unit_id IS NULL)
     OR (action IN ('modify','remove') AND target_unit_id IS NOT NULL))
);

CREATE TABLE reviews (
  id          INTEGER PRIMARY KEY,
  pr_id       INTEGER NOT NULL REFERENCES pull_requests(id),
  reviewer    TEXT NOT NULL CHECK(reviewer LIKE 'ai:%'),  -- 審査AI識別子（採点AIと別系統・D5）
  verdict     TEXT CHECK(verdict IN ('approve','request_changes','escalate')),
  comment     TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 監査ログ（全状態変化の裏取り）
CREATE TABLE audit_log (
  id         INTEGER PRIMARY KEY,
  actor      TEXT NOT NULL CHECK(actor = 'human' OR actor = 'system' OR actor LIKE 'ai:%'),
  action     TEXT NOT NULL,              -- quarantine/restore/status_change/...
  entity     TEXT NOT NULL,              -- 'rule_unit' | 'question' | ...
  entity_id  INTEGER NOT NULL,
  payload    TEXT,                       -- JSON 詳細
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_audit_entity ON audit_log(entity, entity_id);
```

## 状態遷移（status の遷移ルール）

新しい状態への遷移は以下の経路のみ許可する。アプリ層で検査し、
定義外の遷移はエラーにする（DDL の CHECK では行間制約を表せないため）。

```
（新規条）        → under_review
（暫定追加）      → provisional_ai          -- 不在時の先行追加（D6）
under_review     → approved | rejected | quarantined
provisional_ai   → approved | rejected | quarantined   -- 林さんの確認結果
approved         → quarantined | under_review          -- 再審査
quarantined      → approved | rejected                 -- 復元 / 正式却下
rejected         → under_review                        -- 再申請
```

「状態遷移」と「推奨/決定」の同期規約:

- `decisions` への記録と同時に、対応する `status_history` 行を
  同じトランザクションで書く（最終判断＝新しい状態）
- AI が単独で判断を確定するのは `provisional_ai` への遷移のみ。
  それ以外の状態遷移で `decided_by` が `ai:*` の行は監査上「要確認」

## 補足

- **現状態の取得**: `status_history` の unit ごとの最新行。VIEW
  `current_status` を作って UI から使う想定
- **イベントの順序**: `created_at` は秒精度なので、同一秒の順序は
  `id` 順で判断する（全テーブル共通）
- **隔離中の条の物理位置**: `quarantine/<file>/<content_hash>.md`
  （ADR-0002 P6）から導出できるので列は持たない。
  隔離・復元の操作自体は audit_log に記録する
- **「1 問ずつ」はスキーマでは強制しない**: questions に pending が
  複数できても構造上は許容する。同時に出す質問を 1 つに絞るのは
  アプリ層（QuestionQueue）の責務
- **提案条は採点対象外**: `score_runs` は `rule_units`（ファイルに
  存在する条）のみ。`proposed_units` は審査 AI のレビューで評価する
  設計（D5 は採点 AI ではなく審査 AI の領分）
- **条が編集で別条になった場合**: 旧 `rule_units.present=0`、新条が新 id で登場。
  ステータスの引き継ぎは「同 file+heading_path で content_hash が近い」
  対応付け後に行う（対応付けロジックは ADR-0002 未決事項と連動）
- **criteria の改版**: `active_to` を立てて差し替え。過去スコアとの
  比較可能性を保つため項目を物理削除しない
- SQLite の日時は UTC ISO8601 文字列（`datetime('now')`）。表示側で JST 変換

## 未決の細部

- 推奨精度の集計期間・バイパスモード移行の閾値（D3 の運用値）
- 質問タイムアウトの初期値（ADR-0001 未決事項と同じ）
- 状態遷移ルールを SQLite の trigger で強制するかアプリ層のみにするか
- `unit_succession` の対応付けを自動実行するか人の確認を挟むか
- PR マージ時に `proposed_units` → `rule_units` への反映をどの
  トランザクション境界で行うか（適用処理設計と連動）
