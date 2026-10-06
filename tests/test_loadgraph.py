import tempfile
import unittest
from pathlib import Path

from warden.loadgraph import _collect_refs, build_load_graph
from warden.parser_hash import content_hash
from warden.parser_units import extract_units

FIXTURES = Path(__file__).parent / "fixtures"


class TestHash(unittest.TestCase):
    def test_hash_stable(self):
        us = extract_units("## 見出し\n\n- テスト条\n")
        h1 = content_hash(us[0])
        h2 = content_hash(us[0])
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 16)

    def test_hash_changes_on_edit(self):
        a = extract_units("## 見出し\n\n- 条A\n")[0]
        b = extract_units("## 見出し\n\n- 条B\n")[0]
        self.assertNotEqual(content_hash(a), content_hash(b))

    def test_hash_normalizes_whitespace(self):
        a = extract_units("## 見出し\n\n- 条  に  空白\n")[0]
        b = extract_units("## 見出し\n\n- 条 に 空白\n")[0]
        self.assertEqual(content_hash(a), content_hash(b))


class TestLoadGraph(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel: str, text: str):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_basic_reach(self):
        self.write("CLAUDE.md", "@rules_a.md\n")
        self.write("rules_a.md", "- 条\n")
        self.write("rules_b.md", "- 非ロード\n")
        nodes = build_load_graph(self.root)
        self.assertTrue(nodes["CLAUDE.md"].loaded)
        self.assertTrue(nodes["rules_a.md"].loaded)
        self.assertFalse(nodes["rules_b.md"].loaded)

    def test_table_cell_ref(self):
        self.write("CLAUDE.md", "| 作業 | @rules_a.md |\n")
        self.write("rules_a.md", "- 条\n")
        nodes = build_load_graph(self.root)
        self.assertTrue(nodes["rules_a.md"].loaded)

    def test_cycle(self):
        self.write("CLAUDE.md", "@a.md\n")
        self.write("a.md", "@b.md\n")
        self.write("b.md", "@a.md\n")
        nodes = build_load_graph(self.root)
        self.assertTrue(nodes["a.md"].loaded)
        self.assertTrue(nodes["b.md"].loaded)
        self.assertTrue(nodes["a.md"].cycle)

    def test_broken_ref(self):
        self.write("CLAUDE.md", "@missing.md\n")
        nodes = build_load_graph(self.root)
        self.assertNotIn("missing.md", nodes)
        self.assertTrue(nodes["CLAUDE.md"].loaded)

    def test_quarantine_excluded(self):
        self.write("CLAUDE.md", "- 条\n")
        self.write("quarantine/CLAUDE.md/ab12.md", "- 隔離済\n")
        nodes = build_load_graph(self.root)
        self.assertNotIn("quarantine/CLAUDE.md/ab12.md", nodes)

    def test_collect_refs(self):
        self.write("CLAUDE.md", "前文\n@a.md\n| x | @b.md |\n")
        refs = _collect_refs(self.root / "CLAUDE.md")
        self.assertIn("a.md", refs)
        self.assertIn("b.md", refs)

    def test_refs_in_comment_and_fence_ignored(self):
        self.write("CLAUDE.md", "<!-- @hidden1.md -->\n\n```\n@hidden2.md\n```\n")
        self.write("hidden1.md", "- 条\n")
        self.write("hidden2.md", "- 条\n")
        refs = _collect_refs(self.root / "CLAUDE.md")
        self.assertEqual(refs, [])
        nodes = build_load_graph(self.root)
        self.assertFalse(nodes["hidden1.md"].loaded)
        self.assertFalse(nodes["hidden2.md"].loaded)


class TestFixtureGraph(unittest.TestCase):
    """実 fixture で CLAUDE.md 起点の到達を確認。

    fixture の CLAUDE.md から実在ファイルへ届く参照は rules_git.md のみ。
    rules_dots_charter.md は fixture 版では参照されず（非ロード）。
    rules_explain/rules_paper/rules_deep_think/PROFILE は fixture 内に
    存在しない（壊れた @ 参照の負例としても機能する）。
    """

    def test_fixture_loaded_set(self):
        nodes = build_load_graph(FIXTURES)
        loaded = {r for r, n in nodes.items() if n.loaded}
        self.assertEqual(loaded, {"CLAUDE.md", "rules_git.md"})
        self.assertFalse(nodes["rules_dots_charter.md"].loaded)


if __name__ == "__main__":
    unittest.main()
