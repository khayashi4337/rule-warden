"""人手/エージェント採点のバッチ適用（5b 続き）。

MockGateway のヒューリスティックではなく、文脈を読んで判断した
採点結果（unit_id, score, rationale の列）を既存スキーマに永続化する。

- score_runs / recommendations に記録（scorer='ai:swe-2' 等）
- score >= threshold → quarantined へ遷移（root 指定時は物理隔離も）
- under_review のままの条で score < threshold → provisional_ai + 暫定記録
- すでに provisional_ai/approved の条は採点記録のみ（状態は変えない）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, TypedDict

from warden.parser_io import read_markdown
from warden.parser_units import extract_units
from warden.quarantine import quarantine, with_descendants
from warden.scoring_service import find_unit_by_hash
from warden.store import WardenStore


class ScoreEntry(TypedDict):
    unit_id: int
    score: int
    rationale: str


def register_profile(store: WardenStore, role: str, model: str,
                     vendor: str | None = None) -> None:
    """ai_profiles にスコアラー/レビューアを登録（冪等）。"""
    with store.lock:
        store.conn.execute(
            "INSERT INTO ai_profiles (role, model, vendor) "
            "SELECT ?, ?, ? WHERE NOT EXISTS "
            "(SELECT 1 FROM ai_profiles WHERE role=? AND model=?)",
            (role, model, vendor, role, model),
        )
        store.commit()


def apply_scores(store: WardenStore, entries: Iterable[ScoreEntry],
                 scorer: str = "ai:swe-2",
                 root: Path | None = None,
                 threshold: int = 60,
                 dry_run: bool = True) -> dict:
    """採点結果を一括適用する。サマリを返す。"""
    stats = {"scored": 0, "provisional": 0, "quarantined": 0,
             "kept": 0, "missing": 0}
    for e in entries:
        uid, score = e["unit_id"], e["score"]
        row = store.conn.execute(
            "SELECT ru.id, ru.content_hash, ru.file_id, rf.path, cs.status "
            "FROM rule_units ru JOIN rule_files rf ON rf.id = ru.file_id "
            "LEFT JOIN current_status cs ON cs.unit_id = ru.id "
            "WHERE ru.id = ? AND ru.present = 1",
            (uid,),
        ).fetchone()
        if row is None:
            stats["missing"] += 1
            continue
        stats["scored"] += 1
        if dry_run:
            continue

        run = store.conn.execute(
            "INSERT INTO score_runs (unit_id, scorer, total_score, rationale) "
            "VALUES (?, ?, ?, ?) RETURNING id",
            (uid, scorer, score, e["rationale"]),
        ).fetchone()
        store.conn.execute(
            "INSERT INTO recommendations (unit_id, score_run_id, "
            "recommended_status) VALUES (?, ?, ?)",
            (uid, run["id"],
             "quarantined" if score >= threshold else "provisional_ai"),
        )

        if score >= threshold:
            store.set_status(uid, "quarantined", scorer,
                             reason=f"score={score}: {e['rationale']}")
            stats["quarantined"] += 1
            store.audit(scorer, "auto_quarantine", "rule_unit", uid,
                        json.dumps({"score": score}))
            if root is not None:
                found = find_unit_by_hash(Path(root) / row["path"],
                                          row["content_hash"])
                if found:
                    i, _ = found
                    units = extract_units(
                        read_markdown(Path(root) / row["path"]) or "")
                    qr = quarantine(Path(root), row["path"],
                                    with_descendants(units, i))
                    if not qr.ok:
                        store.audit("system", "quarantine_failed",
                                    "rule_unit", uid, qr.error)
        elif row["status"] in (None, "under_review", "pending"):
            store.set_status(uid, "provisional_ai", scorer,
                             reason=f"score={score}: {e['rationale']}")
            store.conn.execute(
                "INSERT INTO provisional_records "
                "(unit_id, request_ref, adr_path, reason) "
                "VALUES (?, ?, ?, ?)",
                (uid, "manual-score", "docs/adr/0005-operation-decisions.md",
                 e["rationale"]),
            )
            stats["provisional"] += 1
        else:
            stats["kept"] += 1

    if not dry_run:
        store.commit()
    return stats
