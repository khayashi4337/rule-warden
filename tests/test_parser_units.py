import unittest
from collections import Counter
from pathlib import Path

from warden.parser_units import extract_units

FIXTURES = Path(__file__).parent / "fixtures"


class TestExtract(unittest.TestCase):
    def test_nested_bullets_parent(self):
        text = "## 見出し\n\n- 親1\n  - 子1a\n  - 子1b\n- 親2\n"
        us = extract_units(text)
        bullets = [u for u in us if u.kind == "bullet"]
        self.assertEqual(len(bullets), 4)
        self.assertFalse(bullets[0].is_leaf)
        self.assertTrue(bullets[1].is_leaf)
        self.assertEqual(bullets[1].parent, 0)
        self.assertEqual(bullets[2].parent, 0)
        self.assertTrue(bullets[3].is_leaf)

    def test_continuation_line(self):
        text = "## 見出し\n\n- 親\n  継続行\n- 次\n"
        us = extract_units(text)
        bullets = [u for u in us if u.kind == "bullet"]
        self.assertIn("継続行", bullets[0].raw_text)
        self.assertEqual(bullets[0].end_line, 4)

    def test_paragraph(self):
        text = "## 見出し\n\n段落1行目\n段落2行目\n\n- 箇条書き\n"
        us = extract_units(text)
        kinds = [u.kind for u in us]
        self.assertIn("paragraph", kinds)
        self.assertIn("bullet", kinds)
        para = next(u for u in us if u.kind == "paragraph")
        self.assertIn("段落2行目", para.raw_text)

    def test_table_rows(self):
        text = "## 見出し\n\n| A | B |\n|---|---|\n| 1 | x |\n| 2 | y |\n"
        us = extract_units(text)
        rows = [u for u in us if u.kind == "table_row"]
        self.assertEqual(len(rows), 2)  # ヘッダと区切り行は条にしない
        self.assertIn("| 1 | x |", rows[0].raw_text)

    def test_import(self):
        text = "@rules_a.md\n\n## 見出し\n\n| 作業 | ルール |\n|---|---|\n| git | @rules_b.md |\n"
        us = extract_units(text)
        imports = [u for u in us if u.kind == "import"]
        self.assertEqual(len(imports), 1)
        rows = [u for u in us if u.kind == "table_row"]
        self.assertEqual(len(rows), 1)

    def test_heading_path(self):
        text = "# 大\n\n## 中\n\n- 条\n\n### 小\n\n- 条2\n"
        us = extract_units(text)
        bullets = [u for u in us if u.kind == "bullet"]
        self.assertEqual(bullets[0].heading_path, "大 > 中")
        self.assertEqual(bullets[1].heading_path, "大 > 中 > 小")

    def test_ordinal(self):
        text = "## 見出し\n\n- 1\n- 2\n- 3\n\n## 次\n\n- 1\n"
        us = extract_units(text)
        bullets = [u for u in us if u.kind == "bullet"]
        self.assertEqual([b.ordinal for b in bullets], [1, 2, 3, 1])

    def test_line_ranges(self):
        text = "## 見出し\n\n- 条A\n- 条B\n"
        us = extract_units(text)
        bullets = [u for u in us if u.kind == "bullet"]
        self.assertEqual(bullets[0].start_line, 3)
        self.assertEqual(bullets[0].end_line, 3)
        self.assertEqual(bullets[1].start_line, 4)


class TestFixtureCounts(unittest.TestCase):
    """実データ fixture の条数を固定（退行検知）。"""

    EXPECTED = {
        "CLAUDE.md": 57,
        "MCP_Sequential.md": 15,
        "RULES.md": 141,
        "rules_dots_charter.md": 102,
        "rules_git.md": 10,
        "rules_iterate.md": 14,
        "rules_junrule.md": 9,
        "SKILL.md": 46,
        "始末書_2026-10-04_Sonnet5.5.md": 92,
    }

    def test_unit_counts(self):
        for name, expected in self.EXPECTED.items():
            with self.subTest(name=name):
                for f in FIXTURES.rglob(name):
                    us = extract_units(f.read_text(encoding="utf-8"))
                    self.assertEqual(len(us), expected, f.name)

    def test_junrule_quote_units_not_bullets(self):
        f = FIXTURES / "rules_junrule.md"
        us = extract_units(f.read_text(encoding="utf-8"))
        kinds = Counter(u.kind for u in us)
        # 引用ブロック内の条が混ざっていないか: 引用元の 5 行は除外済み
        self.assertEqual(kinds["bullet"], 3)

    def test_claude_imports(self):
        f = FIXTURES / "CLAUDE.md"
        us = extract_units(f.read_text(encoding="utf-8"))
        imports = [u for u in us if u.kind == "import"]
        self.assertEqual(len(imports), 2)


if __name__ == "__main__":
    unittest.main()
