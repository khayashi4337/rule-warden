"""Web UI — stdlib http.server による軽量 API＋画面（4a/4b/4c）。

- GET  /api/units     : 統合一覧（DB条 ∪ quarantine/ ∪ rules_junrule.md・op-junrule-unified-list）
- GET  /api/review    : 要確認一覧（provisional_ai・危険度順・op-reviewlist-riskorder）
- POST /api/review    : {"unit_id":N, "action":"confirm|revert"} 林さん判断
- GET/POST /api/bypass: バイパスモード手動切替（op-bypass-manual）
- GET  /              : 最小 HTML（一覧＋ソート）
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from warden.orchestrator import review_list
from warden.parser_io import read_markdown
from warden.parser_units import extract_units
from warden.quarantine import read_quarantine_meta
from warden.store import WardenStore


def union_list(store: WardenStore, root: Path) -> list[dict]:
    """DB 登録条 ∪ quarantine/ 内条 ∪ rules_junrule.md の条を返す。"""
    items: list[dict] = []
    rows = store.conn.execute(
        """
        SELECT ru.id, rf.path, ru.heading_path, ru.kind, ru.raw_text,
               cs.status,
               (SELECT sr.total_score FROM score_runs sr
                 WHERE sr.unit_id=ru.id ORDER BY sr.id DESC LIMIT 1) AS score
        FROM rule_units ru
        JOIN rule_files rf ON rf.id=ru.file_id
        LEFT JOIN current_status cs ON cs.unit_id=ru.id
        WHERE ru.present = 1
        """
    ).fetchall()
    for r in rows:
        items.append({
            "origin": "db",
            "unit_id": r["id"], "path": r["path"],
            "heading_path": r["heading_path"], "kind": r["kind"],
            "text": r["raw_text"][:200],
            "status": r["status"] or "unscored",
            "score": r["score"],
        })

    qdir = Path(root) / "quarantine"
    if qdir.is_dir():
        for qf in qdir.rglob("*.md"):
            if not qf.is_file():  # quarantine/<file>.md/ は同名ディレクトリ
                continue
            meta = read_quarantine_meta(qf)
            if meta:
                items.append({
                    "origin": "quarantine", "unit_id": None,
                    "path": meta["source"],
                    "heading_path": meta["heading_path"],
                    "kind": meta["kind"],
                    "text": meta["body"][:200],
                    "status": "quarantined",
                    "score": None,
                    "qfile": str(qf),
                })

    junrule = Path(root) / "rules_junrule.md"
    junrule_in_db = any(
        i["path"] == "rules_junrule.md" and i["origin"] == "db" for i in items
    )
    for i in items:
        if i["path"] == "rules_junrule.md" and i["origin"] == "db":
            i["origin"] = "junrule"  # 準ルール棚として表示（op-junrule-unified-list）
    text = read_markdown(junrule) if junrule.exists() else None
    if text is not None and not junrule_in_db:
        for u in extract_units(text):
            items.append({
                "origin": "junrule", "unit_id": None,
                "path": "rules_junrule.md",
                "heading_path": u.heading_path, "kind": u.kind,
                "text": u.raw_text[:200],
                "status": "junrule",
                "score": None,
            })
    items.sort(key=lambda x: (-(x["score"] if x["score"] is not None else -1),
                              x["path"], x["heading_path"]))
    return items


INDEX_HTML = """<!doctype html><meta charset="utf-8"><title>rule-warden</title>
<style>body{font-family:monospace}table{border-collapse:collapse}
td,th{border:1px solid #999;padding:2px 6px;font-size:12px}
.quarantined{background:#fdd}.provisional_ai{background:#ffd}</style>
<h1>rule-warden 統合一覧</h1>
<p>バイパス: <b id="bp"></b> <button onclick="toggle()">切替</button></p>
<table><tr><th>score</th><th>status</th><th>origin</th><th>path</th>
<th>heading</th><th>text</th></tr></table>
<script>
async function load(){
 const r=await fetch('/api/units'); const d=await r.json();
 const t=document.querySelector('table');
 d.items.forEach(i=>{const tr=t.insertRow();tr.className=i.status;
  tr.insertCell().textContent=i.score??'';
  tr.insertCell().textContent=i.status;
  tr.insertCell().textContent=i.origin;
  tr.insertCell().textContent=i.path;
  tr.insertCell().textContent=i.heading_path;
  tr.insertCell().textContent=i.text;});
 const b=await (await fetch('/api/bypass')).json();
 document.getElementById('bp').textContent=b.value;}
async function toggle(){await fetch('/api/bypass',{method:'POST'});location.reload();}
load();
</script>"""


def make_handler(store: WardenStore, root: Path):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                body = INDEX_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/api/units":
                self._json({"items": union_list(store, root)})
            elif u.path == "/api/review":
                self._json({"items": review_list(store)})
            elif u.path == "/api/bypass":
                row = store.conn.execute(
                    "SELECT value FROM settings WHERE key='bypass_mode'"
                ).fetchone()
                self._json({"key": "bypass_mode",
                            "value": row["value"] if row else "off"})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            u = urlparse(self.path)
            if u.path == "/api/bypass":
                row = store.conn.execute(
                    "SELECT value FROM settings WHERE key='bypass_mode'"
                ).fetchone()
                new = "off" if (row and row["value"] == "on") else "on"
                store.conn.execute(
                    "INSERT INTO settings (key, value, updated_by) "
                    "VALUES ('bypass_mode', ?, 'human') "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                    "updated_by='human', updated_at=datetime('now')",
                    (new,))
                store.commit()
                self._json({"key": "bypass_mode", "value": new})
            elif u.path == "/api/review":
                n = int(self.headers.get("Content-Length", 0))
                try:
                    data = json.loads(self.rfile.read(n) or b"{}")
                    uid = int(data["unit_id"])
                    action = data["action"]
                except (ValueError, KeyError):
                    self._json({"error": "bad request"}, 400)
                    return
                with store.lock:
                    if action == "confirm":
                        store.set_status(uid, "approved", "human",
                                         reason="reviewed: confirm")
                        store.conn.execute(
                            "UPDATE provisional_records SET outcome='confirmed', "
                            "confirmed_at=datetime('now') WHERE unit_id=? "
                            "AND confirmed_at IS NULL", (uid,))
                    elif action == "revert":
                        store.set_status(uid, "quarantined", "human",
                                         reason="reviewed: revert")
                        store.conn.execute(
                            "UPDATE provisional_records SET outcome='reverted', "
                            "confirmed_at=datetime('now') WHERE unit_id=? "
                            "AND confirmed_at IS NULL", (uid,))
                    else:
                        self._json({"error": "unknown action"}, 400)
                        return
                    store.commit()
                self._json({"ok": True, "unit_id": uid, "action": action})
            else:
                self._json({"error": "not found"}, 404)

        def log_message(self, fmt, *args):
            pass  # 標準エラーへの逐次ログは logging_setup 側に任せる

    return Handler


def serve(store: WardenStore, root: Path, host="127.0.0.1", port=8080):
    srv = ThreadingHTTPServer((host, port), make_handler(store, root))
    print(f"warden UI: http://{host}:{port}/")
    srv.serve_forever()
