import io
import unittest
from contextlib import redirect_stdout

from warden.__main__ import build_parser, main
from warden.config import Config


class TestCli(unittest.TestCase):
    def test_help(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([])
        self.assertEqual(rc, 0)
        self.assertIn("scan", buf.getvalue())

    def test_subcommand_stub(self):
        for cmd in ("apply", "serve"):
            with self.subTest(cmd=cmd):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = main([cmd])
                self.assertEqual(rc, 0)
                self.assertIn("not implemented", buf.getvalue())

    def test_parser_has_commands(self):
        p = build_parser()
        self.assertIsNotNone(p)


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        c = Config()
        self.assertTrue(str(c.db_path).endswith("warden.db"))
        self.assertEqual(c.agent.name, "local-claude")


if __name__ == "__main__":
    unittest.main()
