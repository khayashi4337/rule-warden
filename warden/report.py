"""採点対象の内訳レポート。

ルート直下（ルール本体）とサブディレクトリ（skills/commands 等の
参照資料）を分けて、ロード状態と条数を出す。
"""

from __future__ import annotations

from warden.store import WardenStore


def unit_breakdown(store: WardenStore, status: str = "under_review") -> dict:
    rows = store.conn.execute(
        "SELECT rf.path, rf.loaded, COUNT(*) c FROM rule_units ru "
        "JOIN rule_files rf ON rf.id=ru.file_id "
        "JOIN current_status cs ON cs.unit_id=ru.id "
        "WHERE ru.present=1 AND cs.status=? "
        "GROUP BY rf.path ORDER BY rf.loaded DESC, c DESC",
        (status,),
    ).fetchall()
    files = [
        {"path": r["path"], "loaded": bool(r["loaded"]), "units": r["c"]}
        for r in rows
    ]
    root_u = sum(f["units"] for f in files if "/" not in f["path"])
    sub_u = sum(f["units"] for f in files if "/" in f["path"])
    loaded_u = sum(f["units"] for f in files if f["loaded"])
    return {
        "files": files,
        "root_units": root_u,
        "subtree_units": sub_u,
        "loaded_units": loaded_u,
    }
