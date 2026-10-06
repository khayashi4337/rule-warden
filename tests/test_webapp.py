import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from warden.orchestrator import scan
from warden.store import WardenStore
from warden.webapp import make_handler, union_list


class TestUnionList(unittest.TestCase):
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

    def test_union_includes_all_origins(self):
        (self.root / "CLAUDE.md").write_text("- 条A\n", encoding="utf-8")
        (self.root / "rules_junrule.md").write_text(
            "## 準ルール\n\n- 準ルール条\n", encoding="utf-8")
        qf = self.root / "quarantine" / "R.md" / "h.md"
        qf.parent.mkdir(parents=True)
        qf.write_text(
            "<!-- warden-quarantine\nsource: R.md\nlines: 1-1\n"
            "heading_path: H\nkind: bullet\n-->\n- 隔離条\n",
            encoding="utf-8")
        scan(self.st, "local-claude", self.root)
        items = union_list(self.st, self.root)
        origins = {i["origin"] for i in items}
        self.assertEqual(origins, {"db", "quarantine", "junrule"})


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "claude"
        cls.root.mkdir()
        (cls.root / "CLAUDE.md").write_text("- 条A\n", encoding="utf-8")
        cls.st = WardenStore(Path(cls.tmp.name) / "w.db")
        cls.st.init_schema()
        scan(cls.st, "local-claude", cls.root)
        cls.srv = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(cls.st, cls.root))
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.st.close()
        cls.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=5) as r:
            return json.loads(r.read())

    def post(self, path, data=None):
        body = json.dumps(data).encode() if data is not None else b""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=body, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_units_api(self):
        d = self.get("/api/units")
        self.assertIn("items", d)
        self.assertTrue(any(i["origin"] == "db" for i in d["items"]))

    def test_bypass_toggle(self):
        d1 = self.get("/api/bypass")
        self.assertEqual(d1["value"], "off")
        d2 = self.post("/api/bypass")
        self.assertEqual(d2["value"], "on")
        d3 = self.post("/api/bypass")
        self.assertEqual(d3["value"], "off")

    def test_review_confirm(self):
        uid = self.st.conn.execute("SELECT id FROM rule_units").fetchone()["id"]
        self.st.set_status(uid, "provisional_ai", "ai:x")
        self.st.commit()
        d = self.post("/api/review", {"unit_id": uid, "action": "confirm"})
        self.assertTrue(d["ok"])
        self.assertEqual(self.st.current_status(uid), "approved")


if __name__ == "__main__":
    unittest.main()
