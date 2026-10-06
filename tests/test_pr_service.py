import tempfile
import unittest
from pathlib import Path

from warden.orchestrator import scan
from warden.parser_io import read_markdown
from warden.pr_service import apply_pr, create_pr, record_review, set_pr_state
from warden.store import WardenStore


class TestPrService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "claude"
        self.root.mkdir()
        (self.root / "CLAUDE.md").write_text(
            "## 見出し\n\n- 条A\n- 条B\n\n## 別節\n\n- 条C\n",
            encoding="utf-8")
        self.st = WardenStore(Path(self.tmp.name) / "w.db")
        self.st.init_schema()
        scan(self.st, "local-claude", self.root)
        self.agent_id = self.st.conn.execute(
            "SELECT id FROM agents").fetchone()["id"]
        self.units = {
            r["raw_text"]: r["id"]
            for r in self.st.conn.execute(
                "SELECT id, raw_text FROM rule_units").fetchall()
        }

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def _approved_pr(self, units):
        pr_id = create_pr(self.st, self.agent_id, "ai:proposer",
                          "warden-admin/claude-rules", 1, units)
        record_review(self.st, pr_id, "ai:reviewer-x", "approve")
        return pr_id

    def test_add_applied_and_provisional(self):
        pr_id = self._approved_pr([{
            "action": "add", "file_path": "CLAUDE.md",
            "heading_path": "見出し", "raw_text": "- 条D",
        }])
        stats = apply_pr(self.st, pr_id, self.root, dry_run=False)
        self.assertEqual(len(stats["added"]), 1)
        text = read_markdown(self.root / "CLAUDE.md")
        self.assertIn("- 条D", text)
        # 見出し節内（別節より前）に挿入されている
        self.assertLess(text.index("- 条D"), text.index("## 別節"))
        row = self.st.conn.execute(
            "SELECT applied_unit_id FROM proposed_units").fetchone()
        self.assertIsNotNone(row["applied_unit_id"])
        status = self.st.current_status(row["applied_unit_id"])
        self.assertEqual(status, "provisional_ai")
        state = self.st.conn.execute(
            "SELECT state FROM pull_requests WHERE id=?",
            (pr_id,)).fetchone()["state"]
        self.assertEqual(state, "merged")

    def test_modify_replaces_text(self):
        uid = self.units["- 条B"]
        pr_id = self._approved_pr([{
            "action": "modify", "file_path": "CLAUDE.md",
            "raw_text": "- 条B改訂", "target_unit_id": uid,
        }])
        apply_pr(self.st, pr_id, self.root, dry_run=False)
        text = read_markdown(self.root / "CLAUDE.md")
        self.assertIn("- 条B改訂", text)
        self.assertNotIn("- 条B\n", text)
        # 原文は quarantine/ に保全
        qfiles = [p for p in (self.root / "quarantine").rglob("*.md")
                  if p.is_file()]
        self.assertEqual(len(qfiles), 1)

    def test_remove_quarantines(self):
        uid = self.units["- 条C"]
        pr_id = self._approved_pr([{
            "action": "remove", "file_path": "CLAUDE.md",
            "raw_text": "- 条C", "target_unit_id": uid,
        }])
        apply_pr(self.st, pr_id, self.root, dry_run=False)
        self.assertNotIn("- 条C", read_markdown(self.root / "CLAUDE.md"))
        self.assertEqual(self.st.current_status(uid), "quarantined")

    def test_not_approved_rejected(self):
        pr_id = create_pr(self.st, self.agent_id, "ai:proposer",
                          "repo", 1, [{
                              "action": "add", "file_path": "CLAUDE.md",
                              "raw_text": "- X"}])
        with self.assertRaises(ValueError):
            apply_pr(self.st, pr_id, self.root, dry_run=False)
        record_review(self.st, pr_id, "ai:reviewer-x", "request_changes")
        with self.assertRaises(ValueError):
            apply_pr(self.st, pr_id, self.root, dry_run=False)

    def test_escalated_not_applied(self):
        pr_id = self._approved_pr([{
            "action": "add", "file_path": "CLAUDE.md",
            "raw_text": "- X"}])
        set_pr_state(self.st, pr_id, "escalated")
        with self.assertRaises(ValueError):
            apply_pr(self.st, pr_id, self.root, dry_run=False)

    def test_dry_run_no_change(self):
        pr_id = self._approved_pr([{
            "action": "add", "file_path": "CLAUDE.md",
            "heading_path": "見出し", "raw_text": "- 条D",
        }])
        stats = apply_pr(self.st, pr_id, self.root, dry_run=True)
        self.assertEqual(len(stats["added"]), 1)
        self.assertNotIn("- 条D", read_markdown(self.root / "CLAUDE.md"))

    def test_error_keeps_open(self):
        # 実在する条だが content_hash を壊して「ファイルに無い」状態にする
        uid = self.units["- 条B"]
        self.st.conn.execute(
            "UPDATE rule_units SET content_hash='zzz' WHERE id=?", (uid,))
        self.st.commit()
        pr_id = self._approved_pr([{
            "action": "remove", "file_path": "CLAUDE.md",
            "raw_text": "- 条B", "target_unit_id": uid,
        }])
        stats = apply_pr(self.st, pr_id, self.root, dry_run=False)
        self.assertEqual(len(stats["errors"]), 1)
        state = self.st.conn.execute(
            "SELECT state FROM pull_requests WHERE id=?",
            (pr_id,)).fetchone()["state"]
        self.assertEqual(state, "open")


if __name__ == "__main__":
    unittest.main()
