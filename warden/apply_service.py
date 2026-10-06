"""apply — DB 上の決定（status）とファイルの物理状態を一致させる。

方向は 2 つ:
- status=quarantined なのに本文がファイル内に残っている → 物理隔離
  （webapp の revert 等、ステータスだけ先行したケース）
- quarantine/ に隔離ファイルがあるのに status が quarantined でない
  → present=0 なら物理復元して隔離ファイルを削除、
    present=1 なら本文は既にファイル内（stale）なので隔離ファイルのみ削除

dry_run が既定。物理書き込みは dry_run=False のときだけ。
"""

from __future__ import annotations

import json
from pathlib import Path

from warden.parser_io import read_markdown
from warden.parser_units import extract_units
from warden.quarantine import (
    quarantine,
    read_quarantine_meta,
    restore,
    with_descendants,
)
from warden.scoring_service import find_unit_by_hash
from warden.store import WardenStore

ACTOR = "system"  # audit_log.actor の CHECK 制約（human|system|ai:%）に合わせる


def _prune_empty_dirs(qdir: Path) -> None:
    """quarantine/ 配下の空ディレクトリを末端から掃除する。"""
    for d in sorted((p for p in qdir.rglob("*") if p.is_dir()),
                    key=lambda p: len(p.parts), reverse=True):
        try:
            d.rmdir()  # 空でなければ失敗するだけ
        except OSError:
            pass


def apply_decisions(
    store: WardenStore,
    root: Path,
    dry_run: bool = True,
) -> dict:
    """決定と物理状態を照合し、ずれを解消する。結果サマリを返す。"""
    root = Path(root)
    stats: dict[str, list] = {
        "quarantined": [], "restored": [], "stale_removed": [], "skipped": [],
    }

    # A. quarantined だが本文がまだファイル内にある条
    rows = store.conn.execute(
        """
        SELECT ru.id, ru.content_hash, rf.path
        FROM rule_units ru
        JOIN rule_files rf ON rf.id = ru.file_id
        JOIN current_status cs ON cs.unit_id = ru.id
        WHERE cs.status = 'quarantined' AND ru.present = 1
        ORDER BY ru.id
        """
    ).fetchall()
    for r in rows:
        src = root / r["path"]
        found = find_unit_by_hash(src, r["content_hash"])
        if found is None:
            stats["skipped"].append({
                "unit_id": r["id"], "path": r["path"],
                "reason": "本文は既にファイル内に無い（次回 scan で present=0）",
            })
            continue
        i, _u = found
        units = extract_units(read_markdown(src) or "")
        qr = quarantine(root, r["path"], with_descendants(units, i),
                        dry_run=dry_run)
        stats["quarantined"].append({
            "unit_id": r["id"], "path": r["path"], "ok": qr.ok,
            "moved_to": str(qr.moved_to) if qr.moved_to else None,
            "error": qr.error,
        })
        if not dry_run:
            store.audit(ACTOR, "apply_quarantine", "rule_unit", r["id"],
                        json.dumps({"path": r["path"], "ok": qr.ok,
                                    "error": qr.error}, ensure_ascii=False))

    # B. 隔離ファイル側からの照合
    qdir = root / "quarantine"
    if qdir.is_dir():
        for qf in sorted(p for p in qdir.rglob("*.md") if p.is_file()):
            meta = read_quarantine_meta(qf)
            if meta is None:
                stats["skipped"].append({
                    "qfile": str(qf), "reason": "メタデータ無し"})
                continue
            row = store.conn.execute(
                """
                SELECT ru.id, ru.present, cs.status
                FROM rule_units ru
                JOIN rule_files rf ON rf.id = ru.file_id
                LEFT JOIN current_status cs ON cs.unit_id = ru.id
                WHERE ru.content_hash = ? AND rf.path = ?
                """,
                (qf.stem, meta["source"]),
            ).fetchone()
            if row is None or row["status"] == "quarantined":
                continue  # 決定と一致（または未知）— 触らない
            if row["present"] == 1:
                # 本文は既にファイル内 → 隔離ファイルは残骸
                stats["stale_removed"].append({
                    "qfile": str(qf), "unit_id": row["id"],
                    "path": meta["source"],
                })
                if not dry_run:
                    qf.unlink()
                    store.audit(ACTOR, "stale_qfile_removed", "rule_unit",
                                row["id"],
                                json.dumps({"qfile": str(qf)},
                                           ensure_ascii=False))
                continue
            rr = restore(root, qf, dry_run=dry_run)
            stats["restored"].append({
                "unit_id": row["id"], "path": meta["source"],
                "qfile": str(qf), "ok": rr.ok,
                "inserted_at": rr.inserted_at, "error": rr.error,
            })
            if not dry_run and rr.ok:
                qf.unlink()
                store.audit(ACTOR, "apply_restore", "rule_unit", row["id"],
                            json.dumps({"qfile": str(qf),
                                        "inserted_at": rr.inserted_at},
                                       ensure_ascii=False))

    if not dry_run:
        if qdir.is_dir():
            _prune_empty_dirs(qdir)
        store.commit()
    return stats
