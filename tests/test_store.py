import tempfile
import unittest
from pathlib import Path

from warden.parser_units import extract_units
from warden.store import WardenStore


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "w.db"
        self.st = WardenStore(self.db)
        self.st.init_schema()
        self.agent = self.st.upsert_agent("local-claude", r"C:\Users\user\.claude")
        self.fid = self.st.upsert_file(self.agent, "CLAUDE.md", True, True)

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def test_schema_version(self):
        v = self.st.conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(v, 1)

    def test_agent_upsert_idempotent(self):
        a2 = self.st.upsert_agent("local-claude", r"C:\Users\user\.claude")
        self.assertEqual(a2, self.agent)

    def test_unit_upsert_new_and_seen(self):
        u = extract_units("## 見出し\n\n- 条A\n")[0]
        uid, is_new = self.st.upsert_unit(self.fid, u)
        self.assertTrue(is_new)
        uid2, is_new2 = self.st.upsert_unit(self.fid, u)
        self.assertEqual(uid2, uid)
        self.assertFalse(is_new2)

    def test_unit_different_hash_new_row(self):
        a = extract_units("## 見出し\n\n- 条A\n")[0]
        b = extract_units("## 見出し\n\n- 条B\n")[0]
        ida, _ = self.st.upsert_unit(self.fid, a)
        idb, _ = self.st.upsert_unit(self.fid, b)
        self.assertNotEqual(ida, idb)

    def test_mark_absent(self):
        us = extract_units("## 見出し\n\n- 条A\n- 条B\n")
        ids = {self.st.upsert_unit(self.fid, u)[0] for u in us}
        gone = self.st.mark_absent_except(self.fid, set())
        self.assertEqual(set(gone), ids)
        rows = self.st.conn.execute(
            "SELECT COUNT(*) c FROM rule_units WHERE present=0"
        ).fetchone()
        self.assertEqual(rows["c"], len(ids))

    def test_status_decided_by_check(self):
        import sqlite3

        u = extract_units("## 見出し\n\n- 条A\n")[0]
        uid, _ = self.st.upsert_unit(self.fid, u)
        # decided_by CHECK は human/ai:* のみ → "system" は弾かれる
        with self.assertRaises(sqlite3.IntegrityError):
            self.st.set_status(uid, "under_review", "system")

    def test_status_history_and_view(self):
        u = extract_units("## 見出し\n\n- 条A\n")[0]
        uid, _ = self.st.upsert_unit(self.fid, u)
        self.st.set_status(uid, "under_review", "ai:scorer")
        self.st.set_status(uid, "provisional_ai", "ai:scorer", reason="auto")
        self.assertEqual(self.st.current_status(uid), "provisional_ai")

    def test_audit(self):
        u = extract_units("## 見出し\n\n- 条A\n")[0]
        uid, _ = self.st.upsert_unit(self.fid, u)
        self.st.audit("ai:scorer", "quarantine", "rule_unit", uid, '{"x":1}')
        rows = self.st.conn.execute("SELECT * FROM audit_log").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "quarantine")


if __name__ == "__main__":
    unittest.main()
