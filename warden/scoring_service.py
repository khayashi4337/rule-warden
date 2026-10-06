"""採点適用フロー（3c）。

under_review の条を採点 AI に通し、結果に応じて状態を進める:
- 危険（>= threshold）→ quarantined（O9: AI 自動・復元可能方向）
  かつ root 指定時は物理隔離も行う
- それ以外 → provisional_ai（O4: いつ・なぜを provisional_records に記録）

物理書き込みは dry_run=False かつ root 指定時のみ。
"""

from __future__ import annotations

import json
from pathlib import Path

from warden.ai_gateway import AiGateway
from warden.parser_io import read_markdown
from warden.parser_units import RuleUnit, extract_units
from warden.quarantine import quarantine, with_descendants
from warden.store import WardenStore


def find_unit_by_hash(path: Path, content_hash: str) -> tuple[int, RuleUnit] | None:
    """ファイルを再解析し、content_hash が一致する条の (index, unit) を返す。"""
    from warden.parser_hash import content_hash as ch

    text = read_markdown(path)
    if text is None:
        return None
    for i, u in enumerate(extract_units(text)):
        if ch(u) == content_hash:
            return i, u
    return None


def score_pending(
    store: WardenStore,
    gateway: AiGateway,
    root: Path | None = None,
    threshold: int = 60,
    dry_run: bool = True,
) -> dict:
    """under_review の全条を採点して状態を進める。サマリを返す。"""
    rows = store.conn.execute(
        """
        SELECT ru.id, ru.file_id, ru.content_hash, ru.raw_text,
               rf.path, rf.agent_id
        FROM rule_units ru
        JOIN rule_files rf ON rf.id = ru.file_id
        JOIN current_status cs ON cs.unit_id = ru.id
        WHERE cs.status = 'under_review' AND ru.present = 1
        ORDER BY ru.id
        """
    ).fetchall()

    stats = {"scored": 0, "provisional": 0, "quarantined": 0, "skipped": 0}
    for r in rows:
        res = gateway.score(r["raw_text"], [])
        stats["scored"] += 1

        if dry_run:
            continue  # dry-run は採点のみ（状態もDBも触らない）

        run = store.conn.execute(
            "INSERT INTO score_runs (unit_id, scorer, total_score, rationale) "
            "VALUES (?, ?, ?, ?) RETURNING id",
            (r["id"], gateway.model, res.total, res.rationale),
        ).fetchone()
        store.conn.execute(
            "INSERT INTO recommendations (unit_id, score_run_id, recommended_status) "
            "VALUES (?, ?, ?)",
            (r["id"], run["id"],
             "quarantined" if res.total >= threshold else "provisional_ai"),
        )

        if res.total >= threshold:
            store.set_status(r["id"], "quarantined", gateway.model,
                             reason=f"score={res.total}: {res.rationale}")
            stats["quarantined"] += 1
            store.audit(gateway.model, "auto_quarantine", "rule_unit",
                        r["id"], json.dumps({"score": res.total}))
            if root is not None:
                found = find_unit_by_hash(Path(root) / r["path"],
                                          r["content_hash"])
                if found:
                    i, u = found
                    units = extract_units(
                        read_markdown(Path(root) / r["path"]) or "")
                    qr = quarantine(Path(root), r["path"],
                                    with_descendants(units, i))
                    if not qr.ok:
                        store.audit("system", "quarantine_failed",
                                    "rule_unit", r["id"], qr.error)
        else:
            store.set_status(r["id"], "provisional_ai", gateway.model,
                             reason=f"score={res.total}: {res.rationale}")
            store.conn.execute(
                "INSERT INTO provisional_records "
                "(unit_id, request_ref, adr_path, reason) "
                "VALUES (?, ?, ?, ?)",
                (r["id"], "auto-score", "data/adr/provisional.md",
                 res.rationale),
            )
            stats["provisional"] += 1

    if not dry_run:
        store.commit()
    return stats
