import subprocess
import tempfile
import unittest
from pathlib import Path

from warden.parser_io import read_markdown
from warden.parser_units import extract_units
from warden.provenance import provenance


class TestReadMarkdown(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_utf8_bom(self):
        p = self.root / "bom.md"
        p.write_bytes(b"\xef\xbb\xbf- \xe6\x9d\xa1\n")
        text = read_markdown(p)
        self.assertIsNotNone(text)
        us = extract_units(text)
        self.assertEqual(len(us), 1)

    def test_utf16le(self):
        p = self.root / "u16.md"
        p.write_bytes("- 条\n".encode("utf-16"))
        text = read_markdown(p)
        self.assertIsNotNone(text)
        us = extract_units(text)
        self.assertEqual(len(us), 1)

    def test_empty(self):
        p = self.root / "empty.md"
        p.write_bytes(b"")
        self.assertEqual(read_markdown(p), "")
        self.assertEqual(extract_units(""), [])

    def test_binary_garbage(self):
        p = self.root / "bad.md"
        p.write_bytes(bytes(range(256)))
        self.assertIsNone(read_markdown(p))

    def test_missing(self):
        self.assertIsNone(read_markdown(self.root / "nope.md"))

    def test_crlf(self):
        p = self.root / "crlf.md"
        p.write_bytes("## H\r\n\r\n- 条\r\n".encode("utf-8"))
        text = read_markdown(p)
        self.assertIsNotNone(text)
        self.assertEqual(len(extract_units(text)), 1)


class TestProvenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fs_fallback_no_repo(self):
        (self.root / "f.md").write_text("- x\n", encoding="utf-8")
        p = provenance(self.root, "f.md")
        self.assertIn(p.source, ("fs", "git"))  # 非repoでもgitが拾う環境があり得る
        self.assertNotEqual(p.source, "unknown")

    def test_git_first_commit(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "tester"], cwd=self.root, check=True)
        (self.root / "f.md").write_text("- x\n", encoding="utf-8")
        subprocess.run(["git", "add", "f.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "add f"], cwd=self.root, check=True)
        p = provenance(self.root, "f.md")
        self.assertEqual(p.source, "git")
        self.assertIsNotNone(p.first_commit)
        self.assertEqual(p.author, "tester")

    def test_missing_file(self):
        p = provenance(self.root, "nope.md")
        self.assertEqual(p.source, "unknown")


if __name__ == "__main__":
    unittest.main()
