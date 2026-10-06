import tempfile
import unittest
from pathlib import Path

from warden.store import WardenStore
from warden.watch import watch_once


class TestWatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "claude"
        self.root.mkdir()
        self.md = self.root / "CLAUDE.md"
        self.md.write_text("- 条A\n", encoding="utf-8")
        self.reports = Path(self.tmp.name) / "reports"
        self.wrepo = Path(self.tmp.name) / "wrepo"  # git ではない → 常に clean
        self.wrepo.mkdir()
        self.st = WardenStore(Path(self.tmp.name) / "w.db")
        self.st.init_schema()

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def test_first_scan_reports_new_units(self):
        res = watch_once(self.st, "local-claude", self.root, self.reports, warden_repo=self.wrepo)
        self.assertTrue(res["changed"])
        rp = Path(res["report"])
        self.assertTrue(rp.is_file())
        self.assertIn("- 条A", rp.read_text(encoding="utf-8"))

    def test_no_change_is_quiet(self):
        watch_once(self.st, "local-claude", self.root, self.reports, warden_repo=self.wrepo)
        res = watch_once(self.st, "local-claude", self.root, self.reports, warden_repo=self.wrepo)
        self.assertFalse(res["changed"])
        self.assertIsNone(res["report"])

    def test_guardrail_gone_in_report(self):
        self.md.write_text("- 権限の行使を控える\n", encoding="utf-8")
        watch_once(self.st, "local-claude", self.root, self.reports, warden_repo=self.wrepo)
        self.md.write_text("", encoding="utf-8")
        res = watch_once(self.st, "local-claude", self.root, self.reports, warden_repo=self.wrepo)
        self.assertTrue(res["changed"])
        text = Path(res["report"]).read_text(encoding="utf-8")
        self.assertIn("防御系の条が消えています", text)
        self.assertIn("権限", text)


if __name__ == "__main__":
    unittest.main()
