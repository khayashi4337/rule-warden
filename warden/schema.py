"""SQLite スキーマ（ADR-0003 の DDL をそのまま埋め込み）。

スキーマバージョンは PRAGMA user_version で管理。
接続ごとに PRAGMA foreign_keys = ON が必須（WardenStore が実施）。
"""

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS agents (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  root_path   TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rule_files (
  id           INTEGER PRIMARY KEY,
  agent_id     INTEGER NOT NULL REFERENCES agents(id),
  path         TEXT NOT NULL COLLATE NOCASE,
  git_tracked  INTEGER NOT NULL,
  loaded       INTEGER NOT NULL,
  sha256       TEXT,
  mtime        TEXT,
  UNIQUE(agent_id, path)
);

CREATE TABLE IF NOT EXISTS rule_units (
  id            INTEGER PRIMARY KEY,
  file_id       INTEGER NOT NULL REFERENCES rule_files(id),
  content_hash  TEXT NOT NULL,
  heading_path  TEXT NOT NULL,
  ordinal       INTEGER NOT NULL,
  parent_id     INTEGER REFERENCES rule_units(id),
  kind          TEXT NOT NULL CHECK(kind IN
                  ('bullet','numbered','paragraph','table_row','import')),
  raw_text      TEXT NOT NULL,
  first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen_at  TEXT NOT NULL DEFAULT (datetime('now')),
  present       INTEGER NOT NULL DEFAULT 1,
  UNIQUE(file_id, content_hash, heading_path)
);
CREATE INDEX IF NOT EXISTS idx_units_hash ON rule_units(content_hash);
CREATE INDEX IF NOT EXISTS idx_units_file ON rule_units(file_id, present);

CREATE TABLE IF NOT EXISTS unit_succession (
  id           INTEGER PRIMARY KEY,
  prev_unit_id INTEGER NOT NULL REFERENCES rule_units(id),
  new_unit_id  INTEGER NOT NULL REFERENCES rule_units(id),
  method       TEXT NOT NULL,
  confidence   REAL,
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(prev_unit_id, new_unit_id)
);

CREATE TABLE IF NOT EXISTS provenance (
  id          INTEGER PRIMARY KEY,
  unit_id     INTEGER NOT NULL UNIQUE REFERENCES rule_units(id),
  source_kind TEXT NOT NULL,
  commit_sha  TEXT,
  committed_at TEXT,
  author      TEXT,
  fs_created  TEXT,
  fs_modified TEXT,
  note        TEXT
);

CREATE TABLE IF NOT EXISTS status_history (
  id         INTEGER PRIMARY KEY,
  unit_id    INTEGER NOT NULL REFERENCES rule_units(id),
  status     TEXT NOT NULL CHECK(status IN
               ('approved','provisional_ai','under_review','quarantined','rejected')),
  decided_by TEXT NOT NULL CHECK(decided_by = 'human' OR decided_by LIKE 'ai:%'),
  reason     TEXT,
  adr_ref    TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_status_unit ON status_history(unit_id, id);

CREATE TABLE IF NOT EXISTS criteria (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  description TEXT,
  weight      INTEGER NOT NULL CHECK(weight BETWEEN 0 AND 100),
  source      TEXT,
  active_from TEXT NOT NULL DEFAULT (datetime('now')),
  active_to   TEXT
);

CREATE TABLE IF NOT EXISTS score_runs (
  id            INTEGER PRIMARY KEY,
  unit_id       INTEGER NOT NULL REFERENCES rule_units(id),
  scorer        TEXT NOT NULL CHECK(scorer LIKE 'ai:%'),
  model_version TEXT,
  total_score   INTEGER NOT NULL CHECK(total_score BETWEEN 0 AND 100),
  rationale     TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS score_details (
  id           INTEGER PRIMARY KEY,
  score_run_id INTEGER NOT NULL REFERENCES score_runs(id),
  criterion_id INTEGER NOT NULL REFERENCES criteria(id),
  score        INTEGER NOT NULL CHECK(score >= 0),
  evidence     TEXT,
  UNIQUE(score_run_id, criterion_id)
);

CREATE TABLE IF NOT EXISTS recommendations (
  id            INTEGER PRIMARY KEY,
  unit_id       INTEGER NOT NULL REFERENCES rule_units(id),
  score_run_id  INTEGER REFERENCES score_runs(id),
  recommended_status TEXT NOT NULL CHECK(recommended_status IN
                  ('approved','provisional_ai','under_review','quarantined','rejected')),
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS decisions (
  id                INTEGER PRIMARY KEY,
  recommendation_id INTEGER NOT NULL REFERENCES recommendations(id),
  final_status      TEXT NOT NULL CHECK(final_status IN
                      ('approved','provisional_ai','under_review','quarantined','rejected')),
  decided_by        TEXT NOT NULL DEFAULT 'human'
                    CHECK(decided_by = 'human' OR decided_by LIKE 'ai:%'),
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS questions (
  id          INTEGER PRIMARY KEY,
  unit_id     INTEGER REFERENCES rule_units(id),
  retry_of    INTEGER REFERENCES questions(id),
  question    TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending'
              CHECK(status IN ('pending','answered','timed_out','cancelled')),
  timeout_at  TEXT NOT NULL,
  answer      TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  answered_at TEXT
);

CREATE TABLE IF NOT EXISTS provisional_records (
  id          INTEGER PRIMARY KEY,
  unit_id     INTEGER NOT NULL REFERENCES rule_units(id),
  question_id INTEGER REFERENCES questions(id),
  request_ref TEXT NOT NULL,
  adr_path    TEXT NOT NULL,
  reason      TEXT,
  outcome     TEXT CHECK(outcome IN ('confirmed','reverted','modified')),
  confirmed_at TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  CHECK((outcome IS NULL) = (confirmed_at IS NULL))
);

CREATE TABLE IF NOT EXISTS pull_requests (
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
CREATE TABLE IF NOT EXISTS proposed_units (
  id             INTEGER PRIMARY KEY,
  pr_id          INTEGER NOT NULL REFERENCES pull_requests(id),
  action         TEXT NOT NULL CHECK(action IN ('add','modify','remove')),
  file_path      TEXT NOT NULL COLLATE NOCASE,
  heading_path   TEXT,
  raw_text       TEXT NOT NULL,
  norm_hash      TEXT,
  target_unit_id INTEGER REFERENCES rule_units(id),
  applied_unit_id INTEGER REFERENCES rule_units(id),
  CHECK((action = 'add' AND target_unit_id IS NULL)
     OR (action IN ('modify','remove') AND target_unit_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS reviews (
  id          INTEGER PRIMARY KEY,
  pr_id       INTEGER NOT NULL REFERENCES pull_requests(id),
  reviewer    TEXT NOT NULL CHECK(reviewer LIKE 'ai:%'),
  verdict     TEXT CHECK(verdict IN ('approve','request_changes','escalate')),
  comment     TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ai_profiles (
  id             INTEGER PRIMARY KEY,
  role           TEXT NOT NULL CHECK(role IN ('scorer','reviewer')),
  model          TEXT NOT NULL,
  vendor         TEXT,
  credential_ref TEXT,
  expires_at     TEXT,
  active         INTEGER NOT NULL DEFAULT 1,
  created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_by TEXT NOT NULL
             CHECK(updated_by = 'human' OR updated_by LIKE 'ai:%'),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
  id         INTEGER PRIMARY KEY,
  actor      TEXT NOT NULL CHECK(actor = 'human' OR actor = 'system' OR actor LIKE 'ai:%'),
  action     TEXT NOT NULL,
  entity     TEXT NOT NULL,
  entity_id  INTEGER NOT NULL,
  payload    TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity, entity_id);

-- 各条の最新ステータス（id 順の最新行）
CREATE VIEW IF NOT EXISTS current_status AS
SELECT sh.unit_id, sh.status, sh.decided_by, sh.reason, sh.adr_ref, sh.created_at
FROM status_history sh
JOIN (
  SELECT unit_id, MAX(id) AS max_id
  FROM status_history GROUP BY unit_id
) latest ON sh.id = latest.max_id;
"""
