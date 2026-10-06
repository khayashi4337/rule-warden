"""WardenStore — SQLite 永続化層（ADR-0003）。

- 接続ごとに PRAGMA foreign_keys = ON
- 条は (file_id, content_hash, heading_path) を実体キーとして upsert
- ステータスは status_history に追記のみ（最新行が現状態）
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from warden.parser_hash import content_hash
from warden.parser_units import RuleUnit
from warden.schema import DDL, SCHEMA_VERSION


class WardenStore:
    def __init__(self, db_path: Path | str):
        import threading

        self.db_path = str(db_path)
        # Web サーバ（別スレッド）からの利用を許可。直列化は lock で担保
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.lock = threading.RLock()
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self.conn.executescript(DDL)
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---- agents / files ----

    def upsert_agent(self, name: str, root_path: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO agents (name, root_path) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET root_path=excluded.root_path "
            "RETURNING id",
            (name, root_path),
        )
        return cur.fetchone()["id"]

    def upsert_file(
        self,
        agent_id: int,
        path: str,
        git_tracked: bool,
        loaded: bool,
        sha256: str | None = None,
        mtime: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO rule_files (agent_id, path, git_tracked, loaded, sha256, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(agent_id, path) DO UPDATE SET "
            "  git_tracked=excluded.git_tracked, loaded=excluded.loaded, "
            "  sha256=excluded.sha256, mtime=excluded.mtime "
            "RETURNING id",
            (agent_id, path, int(git_tracked), int(loaded), sha256, mtime),
        )
        return cur.fetchone()["id"]

    # ---- rule units ----

    def upsert_unit(
        self,
        file_id: int,
        unit: RuleUnit,
        parent_id: int | None = None,
    ) -> tuple[int, bool]:
        """条を upsert。(unit_id, is_new) を返す。

        実体キー: (file_id, content_hash, heading_path)（ADR-0003）。
        既存行は last_seen_at と present=1、ordinal/parent_id を更新。
        """
        h = content_hash(unit)
        existing = self.conn.execute(
            "SELECT id FROM rule_units "
            "WHERE file_id=? AND content_hash=? AND heading_path=?",
            (file_id, h, unit.heading_path),
        ).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE rule_units SET last_seen_at=datetime('now'), present=1, "
                "  ordinal=?, parent_id=?, kind=?, raw_text=? WHERE id=?",
                (unit.ordinal, parent_id, unit.kind, unit.raw_text,
                 existing["id"]),
            )
            return existing["id"], False
        cur = self.conn.execute(
            "INSERT INTO rule_units "
            "(file_id, content_hash, heading_path, ordinal, parent_id, kind, raw_text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
            (file_id, h, unit.heading_path, unit.ordinal, parent_id,
             unit.kind, unit.raw_text),
        )
        return cur.fetchone()["id"], True

    def mark_absent_except(self, file_id: int, seen_unit_ids: set[int]) -> list[int]:
        """file_id 配下で seen に無い条を present=0 にする。消えた id を返す。"""
        if seen_unit_ids:
            marks = ",".join("?" for _ in seen_unit_ids)
            rows = self.conn.execute(
                f"SELECT id FROM rule_units WHERE file_id=? AND present=1 "
                f"AND id NOT IN ({marks})",
                (file_id, *seen_unit_ids),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id FROM rule_units WHERE file_id=? AND present=1",
                (file_id,),
            ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            marks = ",".join("?" for _ in ids)
            self.conn.execute(
                f"UPDATE rule_units SET present=0 WHERE id IN ({marks})", ids
            )
        return ids

    # ---- status ----

    def set_status(
        self,
        unit_id: int,
        status: str,
        decided_by: str,
        reason: str | None = None,
        adr_ref: str | None = None,
    ) -> None:
        """状態遷移を検査してから status_history に追記する。

        AI による非自動遷移（provisional_ai・quarantined 以外）は
        監査ログに 'nonauto_ai_transition' を残す（要確認マーク）。
        """
        from warden.transitions import IllegalTransition, check_transition

        flag = check_transition(self.current_status(unit_id), status, decided_by)
        self.conn.execute(
            "INSERT INTO status_history (unit_id, status, decided_by, reason, adr_ref) "
            "VALUES (?, ?, ?, ?, ?)",
            (unit_id, status, decided_by, reason, adr_ref),
        )
        if flag == "review":
            self.audit(decided_by, "nonauto_ai_transition", "rule_unit",
                       unit_id, f'{{"to": "{status}"}}')

    def current_status(self, unit_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM current_status WHERE unit_id=?", (unit_id,)
        ).fetchone()
        return row["status"] if row else None

    # ---- audit ----

    def audit(self, actor: str, action: str, entity: str,
              entity_id: int, payload: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO audit_log (actor, action, entity, entity_id, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (actor, action, entity, entity_id, payload),
        )

    def commit(self) -> None:
        with self.lock:
            self.conn.commit()
