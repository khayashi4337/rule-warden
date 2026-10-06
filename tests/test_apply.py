import tempfile
import unittest
from pathlib import Path

from warden.apply_service import apply_decisions
from warden.orchestrator import scan
from warden.parser_io import read_markdown
from warden.store import WardenStore


class TestApply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "claude"
        self.root.mkdir()
        self.md = self.root / "CLAUDE.md"
        self.md.write_text(
            "## 見出し\n\n- 条A\n- 条B\n", encoding="utf-8")
        self.st = WardenStore(Path(self.tmp.name) / "w.db")
        self.st.init_schema()
        scan(self.st, "local-claude", self.root)
        self.ids = {
            r["raw_text"]: r["id"]
            for r in self.st.conn.execute(
                "SELECT id, raw_text FROM rule_units").fetchall()
        }

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def _apply(self, write=True):
        return apply_decisions(self.st, self.root, dry_run=not write)

    def test_quarantine_apply(self):
        """quarantined 決定済みなのに本文が残る条を物理隔離する。"""
        uid = self.ids["- 条B"]
        self.st.set_status(uid, "quarantined", "human",
                           reason="reviewed: revert")
        self.st.commit()
        stats = self._apply()
        self.assertEqual(len(stats["quarantined"]), 1)
        self.assertNotIn("- 条B", read_markdown(self.md))
        qfiles = [p for p in (self.root / "quarantine").rglob("*.md")
                  if p.is_file()]
        self.assertEqual(len(qfiles), 1)

    def test_restore_apply(self):
        """隔離済み条が quarantined 以外に戻ったら物理復元する。"""
        uid = self.ids["- 条B"]
        self.st.set_status(uid, "quarantined", "human",
                           reason="reviewed: revert")
        self.st.commit()
        self._apply()
        scan(self.st, "local-claude", self.root)  # present=0 反映
        self.st.set_status(uid, "approved", "human",
                           reason="reviewed: confirm")
        self.st.commit()
        stats = self._apply()
        self.assertEqual(len(stats["restored"]), 1)
        self.assertIn("- 条B", read_markdown(self.md))
        self.assertFalse(
            list((self.root / "quarantine").rglob("*.md")))

    def test_stale_qfile_removed(self):
        """present=1 なのに隔離ファイルが残る → 残骸のみ削除。"""
        uid = self.ids["- 条B"]
        self.st.set_status(uid, "quarantined", "human",
                           reason="r")
        self.st.commit()
        self._apply()
        # 本文を手で戻した状態（外部で復元された）を再現
        self.md.write_text(
            "## 見出し\n\n- 条A\n- 条B\n", encoding="utf-8")
        scan(self.st, "local-claude", self.root)  # present=1 に戻る
        self.st.set_status(uid, "approved", "human", reason="r")
        self.st.commit()
        before = read_markdown(self.md)
        stats = self._apply()
        self.assertEqual(len(stats["stale_removed"]), 1)
        self.assertEqual(read_markdown(self.md), before)  # 本文は不変
        self.assertFalse(
            list((self.root / "quarantine").rglob("*.md")))

    def test_dry_run_no_change(self):
        uid = self.ids["- 条B"]
        self.st.set_status(uid, "quarantined", "human", reason="r")
        self.st.commit()
        stats = self._apply(write=False)
        self.assertEqual(len(stats["quarantined"]), 1)  # 計画は出る
        self.assertIn("- 条B", read_markdown(self.md))    # 実体は不変
        self.assertFalse((self.root / "quarantine").exists())

    def test_consistent_state_noop(self):
        stats = self._apply()
        self.assertEqual(
            stats, {"quarantined": [], "restored": [],
                    "stale_removed": [], "skipped": []})


if __name__ == "__main__":
    unittest.main()
