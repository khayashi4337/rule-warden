import unittest
from pathlib import Path

from warden.parser_lines import LineKind, at_refs, classify_lines

FIXTURES = Path(__file__).parent / "fixtures"


def kinds(text: str):
    return [ln.kind for ln in classify_lines(text)]


class TestClassify(unittest.TestCase):
    def test_fence_body_not_bullet(self):
        text = "```\n- これはコード中の偽bullet\n```\n- 本物\n"
        ks = kinds(text)
        self.assertEqual(ks[0], LineKind.FENCE)
        self.assertEqual(ks[1], LineKind.FENCE_BODY)
        self.assertEqual(ks[3], LineKind.BULLET)

    def test_html_comment(self):
        text = "<!-- コメント - 偽bullet -->\n- 本物\n"
        ks = kinds(text)
        self.assertEqual(ks[0], LineKind.COMMENT)
        self.assertEqual(ks[1], LineKind.BULLET)

    def test_multiline_comment(self):
        text = "<!-- 開始\n- 中身\n-->\n- 本物\n"
        ks = kinds(text)
        self.assertEqual(ks[0], LineKind.COMMENT)
        self.assertEqual(ks[1], LineKind.COMMENT)
        self.assertEqual(ks[2], LineKind.COMMENT)
        self.assertEqual(ks[3], LineKind.BULLET)

    def test_quote_block_after_label(self):
        text = "[CLAUDE.md §2]\n- 引用された条\n1. 引用された番号\n\n- 本物\n"
        ks = kinds(text)
        self.assertEqual(ks[0], LineKind.QUOTE_LABEL)
        self.assertEqual(ks[1], LineKind.QUOTE)
        self.assertEqual(ks[2], LineKind.QUOTE)
        self.assertEqual(ks[3], LineKind.BLANK)
        self.assertEqual(ks[4], LineKind.BULLET)

    def test_table_row_and_import(self):
        text = "| 作業 | ルール |\n|---|---|\n| git | @rules_git.md |\n@rules_dots_charter.md\n"
        ks = kinds(text)
        self.assertEqual(ks[0], LineKind.TABLE_ROW)
        self.assertEqual(ks[2], LineKind.TABLE_ROW)
        self.assertEqual(ks[3], LineKind.IMPORT)

    def test_at_refs_in_table_cell(self):
        refs = at_refs("| git | @rules_git.md |")
        self.assertEqual(refs, ["rules_git.md"])

    def test_at_refs_line_start(self):
        refs = at_refs("@rules_dots_charter.md")
        self.assertEqual(refs, ["rules_dots_charter.md"])

    def test_no_at_refs(self):
        self.assertEqual(at_refs("普通の行"), [])
        self.assertEqual(at_refs("@"), [])


class TestFixtures(unittest.TestCase):
    def test_claude_md_classifies(self):
        text = (FIXTURES / "CLAUDE.md").read_text(encoding="utf-8")
        ls = classify_lines(text)
        kinds_set = {ln.kind for ln in ls}
        self.assertIn(LineKind.HEADING, kinds_set)
        self.assertIn(LineKind.BULLET, kinds_set)
        self.assertIn(LineKind.NUMBERED, kinds_set)
        self.assertIn(LineKind.TABLE_ROW, kinds_set)
        self.assertIn(LineKind.IMPORT, kinds_set)

    def test_junrule_quotes_excluded(self):
        text = (FIXTURES / "rules_junrule.md").read_text(encoding="utf-8")
        ls = classify_lines(text)
        quote_labels = [ln for ln in ls if ln.kind == LineKind.QUOTE_LABEL]
        quotes = [ln for ln in ls if ln.kind == LineKind.QUOTE]
        self.assertGreater(len(quote_labels), 0)
        self.assertGreater(len(quotes), 0)

    def test_all_fixtures_parse(self):
        for f in FIXTURES.rglob("*.md"):
            with self.subTest(f=f.name):
                ls = classify_lines(f.read_text(encoding="utf-8"))
                self.assertEqual(len(ls), len(f.read_text(encoding="utf-8").splitlines()))


if __name__ == "__main__":
    unittest.main()
