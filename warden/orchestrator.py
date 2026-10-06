"""scan 統合と要確認一覧クエリ（2c/2d）。

scan: ファイル走査 → rule_files/rule_units upsert → 新規条は
under_review 初期状態 → 消えた条は present=0。
要確認一覧: provisional_ai / 未確認 provisional_records を
直近スコア降順で返す（O2）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from warden.loadgraph import build_load_graph
from warden.parser_hash import content_hash
from warden.parser_io import read_markdown
from warden.parser_units import extract_units
from warden.store import WardenStore

SCANNER = "ai:warden-scanner"


def _file_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def scan(store: WardenStore, agent_name: str, root: Path) -> dict:
    """root 配下を走査し、条を upsert。結果サマリを返す。"""
    root = Path(root)
    agent_id = store.upsert_agent(agent_name, str(root))
    nodes = build_load_graph(root)

    stats = {"files": 0, "units": 0, "new_units": 0, "gone_units": 0}
    for rel, node in nodes.items():
        text = read_markdown(node.abs_path)
        if text is None:
            continue
        fid = store.upsert_file(
            agent_id, rel,
            git_tracked=True,  # 実装簡略化: 出自判定は provenance 側で
            loaded=node.loaded,
            sha256=_file_sha256(text),
        )
        stats["files"] += 1
        units = extract_units(text)
        id_by_index: dict[int, int] = {}
        seen: set[int] = set()
        for i, u in enumerate(units):
            parent_db = id_by_index.get(u.parent) if u.parent is not None else None
            uid, is_new = store.upsert_unit(fid, u, parent_id=parent_db)
            id_by_index[i] = uid
            seen.add(uid)
            stats["units"] += 1
            if is_new:
                stats["new_units"] += 1
                store.set_status(uid, "under_review", SCANNER,
                                 reason="scan: new unit")
        gone = store.mark_absent_except(fid, seen)
        stats["gone_units"] += len(gone)
        for gid in gone:
            store.audit(SCANNER, "unit_gone", "rule_unit", gid)
    store.audit("system", "scan", "agent", agent_id,
                f'{{"stats": {stats}}}')
    store.commit()
    return stats


def review_list(store: WardenStore, limit: int = 200) -> list[dict]:
    """要確認一覧: provisional_ai 条 + 未確認暫定記録をスコア降順で返す。"""
    rows = store.conn.execute(
        """
        SELECT ru.id AS unit_id, rf.path, ru.heading_path, ru.kind,
               ru.raw_text, cs.status, cs.decided_by, cs.reason,
               (SELECT sr.total_score FROM score_runs sr
                 WHERE sr.unit_id = ru.id ORDER BY sr.id DESC LIMIT 1) AS score,
               pr.id AS provisional_id, pr.confirmed_at
        FROM rule_units ru
        JOIN rule_files rf ON rf.id = ru.file_id
        JOIN current_status cs ON cs.unit_id = ru.id
        LEFT JOIN provisional_records pr ON pr.unit_id = ru.id
        WHERE cs.status = 'provisional_ai' OR pr.confirmed_at IS NULL
        ORDER BY COALESCE(score, -1) DESC, ru.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
