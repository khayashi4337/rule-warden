import tempfile
import unittest
from pathlib import Path

from warden.parser_units import extract_units
from warden.quarantine import (
    quarantine,
    read_quarantine_meta,
    restore,
    with_descendants,
)


class TestQuarantine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel: str, text: str):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def test_quarantine_removes_lines(self):
        src = self.write("RULES.md", "## 見出し\n\n- 条A\n- 条B\n- 条C\n")
        us = extract_units(src.read_text(encoding="utf-8"))
        target = [u for u in us if u.kind == "bullet"][1]  # 条B
        r = quarantine(self.root, "RULES.md", [target])
        self.assertTrue(r.ok)
        remaining = src.read_text(encoding="utf-8")
        self.assertNotIn("条B", remaining)
        self.assertIn("条A", remaining)
        self.assertIn("条C", remaining)
        self.assertTrue(r.moved_to.exists())
        self.assertIn("条B", r.moved_to.read_text(encoding="utf-8"))

    def test_quarantine_with_descendants(self):
        src = self.write("RULES.md", "## 見出し\n\n- 親\n  - 子1\n  - 子2\n- 別\n")
        us = extract_units(src.read_text(encoding="utf-8"))
        parent = next(u for u in us if "親" in u.raw_text)
        targets = with_descendants(us, us.index(parent))
        r = quarantine(self.root, "RULES.md", targets)
        self.assertTrue(r.ok)
        remaining = src.read_text(encoding="utf-8")
        self.assertNotIn("親", remaining)
        self.assertNotIn("子1", remaining)
        self.assertIn("別", remaining)

    def test_quarantine_idempotent(self):
        src = self.write("RULES.md", "## 見出し\n\n- 条A\n")
        us = extract_units(src.read_text(encoding="utf-8"))
        r1 = quarantine(self.root, "RULES.md", [us[0]])
        self.assertTrue(r1.ok)
        # 同じ条（行範囲はずれているが隔離側は同じハッシュ）
        r2 = quarantine(self.root, "RULES.md", [us[0]])
        self.assertTrue(r2.ok)
        self.assertEqual(r1.moved_to, r2.moved_to)

    def test_dry_run_no_write(self):
        src = self.write("RULES.md", "## 見出し\n\n- 条A\n")
        us = extract_units(src.read_text(encoding="utf-8"))
        r = quarantine(self.root, "RULES.md", [us[0]], dry_run=True)
        self.assertTrue(r.ok)
        self.assertIn("条A", src.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "quarantine").exists())

    def test_restore_anchor_heading(self):
        src = self.write("RULES.md", "## 見出しA\n\n- 残る\n\n## 見出しB\n\n- 消す\n")
        us = extract_units(src.read_text(encoding="utf-8"))
        target = next(u for u in us if "消す" in u.raw_text)
        r = quarantine(self.root, "RULES.md", [target])
        self.assertTrue(r.ok)
        rr = restore(self.root, r.moved_to)
        self.assertTrue(rr.ok)
        text = src.read_text(encoding="utf-8")
        self.assertIn("消す", text)
        # 見出しB の直後に戻る
        lines = text.splitlines()
        idx_b = next(i for i, l in enumerate(lines) if "見出しB" in l)
        self.assertIn("消す", lines[idx_b + 2] if lines[idx_b + 1] == "" else lines[idx_b + 1])

    def test_restore_sanitized(self):
        src = self.write("RULES.md", "- 危ない条\n")
        us = extract_units(src.read_text(encoding="utf-8"))
        r = quarantine(self.root, "RULES.md", [us[0]])
        rr = restore(self.root, r.moved_to, new_text="- 直した条\n")
        self.assertTrue(rr.ok)
        text = src.read_text(encoding="utf-8")
        self.assertIn("直した条", text)
        self.assertNotIn("危ない条", text)
        # 原文は隔離側に残る
        self.assertIn("危ない条", r.moved_to.read_text(encoding="utf-8"))

    def test_restore_missing_source(self):
        q = self.write("quarantine/x.md/h.md",
                       "<!-- warden-quarantine\nsource: gone.md\nlines: 1-2\n"
                       "heading_path: \nkind: bullet\n-->\n- 条\n")
        rr = restore(self.root, q)
        self.assertTrue(rr.ok)  # 新規にファイルが作られる
        self.assertIn("条", (self.root / "gone.md").read_text(encoding="utf-8"))

    def test_meta_roundtrip(self):
        src = self.write("RULES.md", "## H\n\n- 条A\n")
        us = extract_units(src.read_text(encoding="utf-8"))
        r = quarantine(self.root, "RULES.md", [us[0]])
        meta = read_quarantine_meta(r.moved_to)
        self.assertEqual(meta["source"], "RULES.md")
        self.assertEqual(meta["kind"], "bullet")
        self.assertEqual(meta["heading_path"], "H")


if __name__ == "__main__":
    unittest.main()
