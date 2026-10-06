import sqlite3
import tempfile
import unittest
from pathlib import Path

from warden.orchestrator import review_list, scan
from warden.store import WardenStore
from warden.transitions import IllegalTransition, check_transition


class TestTransitions(unittest.TestCase):
    def test_initial_allowed(self):
        self.assertIsNone(check_transition(None, "under_review", "ai:x"))
        self.assertIsNone(check_transition(None, "provisional_ai", "ai:x"))

    def test_initial_rejected(self):
        with self.assertRaises(IllegalTransition):
            check_transition(None, "approved", "ai:x")

    def test_illegal(self):
        with self.assertRaises(IllegalTransition):
            check_transition("approved", "provisional_ai", "human")

    def test_ai_auto_quarantine(self):
        self.assertIsNone(
            check_transition("under_review", "quarantined", "ai:scorer"))

    def test_ai_nonauto_flags_review(self):
        self.assertEqual(
            check_transition("quarantined", "approved", "ai:scorer"),
            "review")

    def test_human_no_flag(self):
        self.assertIsNone(
            check_transition("quarantined", "approved", "human"))


class TestScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "claude"
        self.root.mkdir()
        self.db = Path(self.tmp.name) / "w.db"
        self.st = WardenStore(self.db)
        self.st.init_schema()

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def test_scan_registers_units(self):
        (self.root / "CLAUDE.md").write_text(
            "## 見出し\n\n- 条A\n- 条B\n", encoding="utf-8")
        stats = scan(self.st, "local-claude", self.root)
        self.assertEqual(stats["files"], 1)
        self.assertEqual(stats["units"], 2)
        self.assertEqual(stats["new_units"], 2)
        # 新規条は under_review
        rows = self.st.conn.execute(
            "SELECT status, decided_by FROM status_history").fetchall()
        self.assertEqual({r["status"] for r in rows}, {"under_review"})

    def test_scan_rescan_stable(self):
        p = self.root / "CLAUDE.md"
        p.write_text("## 見出し\n\n- 条A\n", encoding="utf-8")
        scan(self.st, "local-claude", self.root)
        stats2 = scan(self.st, "local-claude", self.root)
        self.assertEqual(stats2["new_units"], 0)

    def test_scan_marks_gone(self):
        p = self.root / "CLAUDE.md"
        p.write_text("## 見出し\n\n- 条A\n- 条B\n", encoding="utf-8")
        scan(self.st, "local-claude", self.root)
        p.write_text("## 見出し\n\n- 条A\n", encoding="utf-8")
        stats = scan(self.st, "local-claude", self.root)
        self.assertEqual(stats["gone_units"], 1)

    def test_illegal_transition_rejected_by_store(self):
        (self.root / "CLAUDE.md").write_text("- 条A\n", encoding="utf-8")
        scan(self.st, "local-claude", self.root)
        uid = self.st.conn.execute("SELECT id FROM rule_units").fetchone()["id"]
        # under_review -> provisional_ai は AI 自動可
        self.st.set_status(uid, "provisional_ai", "ai:scorer")
        self.assertEqual(self.st.current_status(uid), "provisional_ai")
        # provisional_ai -> under_review は定義外 → 違法
        with self.assertRaises(IllegalTransition):
            self.st.set_status(uid, "under_review", "human")

    def test_review_list_sort(self):
        (self.root / "CLAUDE.md").write_text(
            "- 条A\n- 条B\n", encoding="utf-8")
        scan(self.st, "local-claude", self.root)
        ids = [r["id"] for r in self.st.conn.execute(
            "SELECT id FROM rule_units ORDER BY id").fetchall()]
        for uid in ids:
            self.st.set_status(uid, "provisional_ai", "ai:scorer")
        items = review_list(self.st)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["status"], "provisional_ai")


if __name__ == "__main__":
    unittest.main()
