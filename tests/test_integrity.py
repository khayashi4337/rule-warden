import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from warden.criteria_seed import SEED, seed_criteria
from warden.store import WardenStore
from warden.watch import git_status_entries, watch_once


def _store(tmp: Path) -> WardenStore:
    s = WardenStore(tmp / "w.db")
    s.init_schema()
    return s


class TestAuditChain(unittest.TestCase):
    def test_chain_ok(self):
        with tempfile.TemporaryDirectory() as td:
            st = _store(Path(td))
            st.audit("human", "a1", "x", 1)
            st.audit("ai:test", "a2", "x", 2, "p")
            st.commit()
            res = st.verify_audit_chain()
            self.assertTrue(res["ok"])
            self.assertEqual(res["total"], 2)
            st.close()

    def test_edit_detected(self):
        with tempfile.TemporaryDirectory() as td:
            st = _store(Path(td))
            st.audit("human", "a1", "x", 1)
            st.audit("ai:test", "a2", "x", 2)
            st.commit()
            # 攻撃者が payload を書き換えたと想定
            st.conn.execute(
                "UPDATE audit_log SET payload='forged' WHERE id=1")
            st.commit()
            res = st.verify_audit_chain()
            self.assertFalse(res["ok"])
            self.assertEqual(res["first_bad_id"], 1)
            st.close()

    def test_delete_detected(self):
        with tempfile.TemporaryDirectory() as td:
            st = _store(Path(td))
            for i in range(3):
                st.audit("human", "a", "x", i)
            st.commit()
            # 中間行の削除 → 後続チェーンが壊れる
            st.conn.execute("DELETE FROM audit_log WHERE id=2")
            st.commit()
            res = st.verify_audit_chain()
            self.assertFalse(res["ok"])
            self.assertEqual(res["first_bad_id"], 3)
            st.close()

    def test_migration_backfill(self):
        """旧スキーマ（entry_hash なし）の DB を移行すると全行に hash が付く。"""
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "old.db"
            conn = sqlite3.connect(db)
            conn.executescript("""
            CREATE TABLE audit_log (
              id INTEGER PRIMARY KEY,
              actor TEXT NOT NULL,
              action TEXT NOT NULL,
              entity TEXT NOT NULL,
              entity_id INTEGER NOT NULL,
              payload TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO audit_log (actor, action, entity, entity_id)
            VALUES ('human', 'seed', 'x', 1), ('ai:old', 'seed2', 'x', 2);
            """)
            conn.commit()
            conn.close()

            st = WardenStore(db)
            st.init_schema()
            res = st.verify_audit_chain()
            self.assertTrue(res["ok"])
            self.assertEqual(res["total"], 2)
            st.close()


class TestCriteriaSeed(unittest.TestCase):
    def test_seed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            st = _store(Path(td))
            n1 = seed_criteria(st)
            self.assertEqual(n1, len(SEED))
            n2 = seed_criteria(st)
            self.assertEqual(n2, 0)
            total = st.conn.execute(
                "SELECT SUM(weight) FROM criteria").fetchone()[0]
            self.assertEqual(total, 100)
            st.close()


class TestGitWatch(unittest.TestCase):
    def _git(self, repo: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True,
                       capture_output=True)

    def test_non_repo_is_clean(self):
        with tempfile.TemporaryDirectory() as td:
            tracked, untracked = git_status_entries(Path(td))
            self.assertEqual(tracked, [])
            self.assertEqual(untracked, [])

    def test_dirty_tracked_reported_untracked_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            agent = Path(td) / "agent"
            agent.mkdir()
            (agent / "CLAUDE.md").write_text("# rules\n- a\n",
                                           encoding="utf-8")
            self._git(agent, "init")
            self._git(agent, "-c", "user.email=t@t", "-c",
                      "user.name=t", "add", "CLAUDE.md")
            self._git(agent, "-c", "user.email=t@t", "-c",
                      "user.name=t", "commit", "-m", "init")

            tracked, untracked = git_status_entries(agent)
            self.assertEqual(tracked, [])

            # 追跡ファイルの未コミット変更（改竄形跡）→ 検出
            (agent / "CLAUDE.md").write_text("# rules\n- a\n- b\n",
                                             encoding="utf-8")
            tracked, untracked = git_status_entries(agent)
            self.assertEqual(len(tracked), 1)
            self.assertIn("CLAUDE.md", tracked[0])

            # untracked ファイルは entries としては拾われる
            # （agent 側で無視するのは watch_once 側の判断）
            (agent / "notes.txt").write_text("x", encoding="utf-8")
            tracked, untracked = git_status_entries(agent)
            self.assertEqual(untracked, ["notes.txt"])

    def test_watch_report_includes_git_section(self):
        with tempfile.TemporaryDirectory() as td:
            agent = Path(td) / "agent"
            agent.mkdir()
            (agent / "CLAUDE.md").write_text("# rules\n- a\n",
                                           encoding="utf-8")
            self._git(agent, "init")
            self._git(agent, "-c", "user.email=t@t", "-c",
                      "user.name=t", "add", "CLAUDE.md")
            self._git(agent, "-c", "user.email=t@t", "-c",
                      "user.name=t", "commit", "-m", "init")

            st = _store(Path(td))
            reports = Path(td) / "reports"
            warden_repo = Path(td) / "wrepo"  # git ではない → 常に clean
            warden_repo.mkdir()
            watch_once(st, "a", agent, reports, warden_repo=warden_repo)

            # ベースライン後に追跡ファイルを無断変更。
            # コメント挿入は条にカウントされない → git 差分だけが検出対象
            (agent / "CLAUDE.md").write_text(
                "# rules\n- a\n<!-- tampered -->\n", encoding="utf-8")
            res = watch_once(st, "a", agent, reports,
                             warden_repo=warden_repo)
            self.assertTrue(res["changed"])
            body = Path(res["report"]).read_text(encoding="utf-8")
            self.assertIn("git 追跡ファイルに未コミットの変更", body)
            st.close()


if __name__ == "__main__":
    unittest.main()
