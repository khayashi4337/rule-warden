"""PR 適用フロー（ADR-0002.5 S3 のローカル部分）。

提案（PullRequest + ProposedUnit の記録）→ 審査（Review）
→ 承認時の適用（ファイル書込 + 状態遷移 + merged）。

- add: heading_path の節末尾（またはファイル末尾）へ本文挿入
- modify: 対象条を隔離してから隔離メタのアンカーへ新本文を挿入
  （原文は quarantine/ に残る）
- remove: 対象条を隔離
- 適用は「state=open かつ最新 verdict=approve」のみ。
  add/modify でできた条は provisional_ai、remove は quarantined。

Forgejo 上のブランチ・PR 作成（S3 の GitClient 部分）は別段階。
dry_run が既定。物理書き込みは dry_run=False のときだけ。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from warden.orchestrator import scan
from warden.parser_io import read_markdown
from warden.parser_units import extract_units
from warden.quarantine import (
    _atomic_write,
    quarantine,
    restore,
    with_descendants,
)
from warden.scoring_service import find_unit_by_hash
from warden.store import WardenStore

HEADING_RE = re.compile(r"^(#{1,6})\s+")


def create_pr(
    store: WardenStore,
    agent_id: int,
    proposer: str,
    forgejo_repo: str,
    pr_number: int,
    units: list[dict],
) -> int:
    """提案を記録して pr_id を返す。

    units: [{"action","file_path","raw_text","heading_path",
             "target_unit_id"}...]
    """
    pr_id = store.conn.execute(
        "INSERT INTO pull_requests (agent_id, forgejo_repo, pr_number, "
        "proposer) VALUES (?, ?, ?, ?) RETURNING id",
        (agent_id, forgejo_repo, pr_number, proposer),
    ).fetchone()["id"]
    for u in units:
        store.conn.execute(
            "INSERT INTO proposed_units "
            "(pr_id, action, file_path, heading_path, raw_text, "
            " target_unit_id) VALUES (?, ?, ?, ?, ?, ?)",
            (pr_id, u["action"], u["file_path"], u.get("heading_path"),
             u["raw_text"], u.get("target_unit_id")),
        )
    store.audit(proposer, "pr_created", "pull_request", pr_id,
                json.dumps({"units": len(units)}, ensure_ascii=False))
    store.commit()
    return pr_id


def record_review(
    store: WardenStore,
    pr_id: int,
    reviewer: str,
    verdict: str,
    comment: str | None = None,
) -> None:
    """審査結果を記録。escalate は PR も escalated にする。"""
    store.conn.execute(
        "INSERT INTO reviews (pr_id, reviewer, verdict, comment) "
        "VALUES (?, ?, ?, ?)",
        (pr_id, reviewer, verdict, comment),
    )
    if verdict == "escalate":
        store.conn.execute(
            "UPDATE pull_requests SET state='escalated' WHERE id=?",
            (pr_id,),
        )
    store.audit(reviewer, "pr_reviewed", "pull_request", pr_id,
                json.dumps({"verdict": verdict}, ensure_ascii=False))
    store.commit()


def set_pr_state(store: WardenStore, pr_id: int, state: str,
                 actor: str = "human") -> None:
    """人間による state 操作（rejected / escalated 等）。"""
    store.conn.execute(
        "UPDATE pull_requests SET state=? WHERE id=?", (state, pr_id))
    store.audit(actor, "pr_state", "pull_request", pr_id,
                json.dumps({"state": state}))
    store.commit()


def _insert_text(root: Path, file_path: str, heading_path: str | None,
                 text: str, dry_run: bool) -> int:
    """heading_path の節末尾に本文を挿入する。戻り値は挿入行(1始)。"""
    src = Path(root) / file_path
    lines = (read_markdown(src) or "").splitlines(keepends=True)
    insert_at = len(lines)
    if heading_path:
        last = heading_path.split(" > ")[-1].strip()
        for i, line in enumerate(lines):
            m = HEADING_RE.match(line)
            if m and last in line:
                level = len(m.group(1))
                j = i + 1
                while j < len(lines):
                    m2 = HEADING_RE.match(lines[j])
                    if m2 and len(m2.group(1)) <= level:
                        break
                    j += 1
                insert_at = j
                break
    body = text if text.endswith("\n") else text + "\n"
    if not dry_run:
        src.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(src, "".join(
            lines[:insert_at] + [body] + lines[insert_at:]))
    return insert_at + 1


def _find_unit_id(store: WardenStore, file_path: str,
                  raw_text: str) -> int | None:
    row = store.conn.execute(
        "SELECT ru.id FROM rule_units ru JOIN rule_files rf "
        "ON rf.id = ru.file_id "
        "WHERE rf.path = ? AND ru.raw_text = ? ORDER BY ru.id DESC",
        (file_path, raw_text.strip()),
    ).fetchone()
    return row["id"] if row else None


def apply_pr(
    store: WardenStore,
    pr_id: int,
    root: Path,
    dry_run: bool = True,
) -> dict:
    """承認済み PR の提案条をファイルに適用する。サマリを返す。"""
    root = Path(root)
    pr = store.conn.execute(
        "SELECT pr.id, pr.state, pr.agent_id, a.name AS agent_name "
        "FROM pull_requests pr JOIN agents a ON a.id = pr.agent_id "
        "WHERE pr.id = ?", (pr_id,)).fetchone()
    if pr is None:
        raise ValueError(f"pr {pr_id} not found")
    if pr["state"] != "open":
        raise ValueError(f"pr {pr_id} state={pr['state']} (open のみ適用可)")
    verdict = store.conn.execute(
        "SELECT verdict, reviewer FROM reviews WHERE pr_id=? "
        "ORDER BY id DESC LIMIT 1", (pr_id,)).fetchone()
    if verdict is None or verdict["verdict"] != "approve":
        raise ValueError(f"pr {pr_id}: 最新 verdict が approve ではない")
    reviewer = verdict["reviewer"]

    units = store.conn.execute(
        "SELECT * FROM proposed_units WHERE pr_id=? ORDER BY id",
        (pr_id,)).fetchall()
    stats: dict[str, list] = {"added": [], "modified": [],
                              "removed": [], "errors": []}
    for u in units:
        try:
            if u["action"] == "add":
                at = _insert_text(root, u["file_path"], u["heading_path"],
                                  u["raw_text"], dry_run)
                stats["added"].append({"file": u["file_path"], "at": at})
            else:
                t = store.conn.execute(
                    "SELECT ru.id, ru.content_hash, rf.path FROM rule_units ru "
                    "JOIN rule_files rf ON rf.id = ru.file_id "
                    "WHERE ru.id = ?", (u["target_unit_id"],)).fetchone()
                if t is None:
                    raise ValueError("target_unit not found")
                src = root / t["path"]
                found = find_unit_by_hash(src, t["content_hash"])
                if found is None:
                    raise ValueError("target unit not in file")
                i, _u = found
                all_units = extract_units(read_markdown(src) or "")
                qr = quarantine(root, t["path"],
                                with_descendants(all_units, i),
                                dry_run=dry_run)
                if not qr.ok:
                    raise ValueError(f"quarantine failed: {qr.error}")
                if u["action"] == "modify":
                    rr = restore(root, qr.moved_to, new_text=u["raw_text"],
                                 dry_run=dry_run)
                    if not rr.ok:
                        raise ValueError(f"restore failed: {rr.error}")
                    stats["modified"].append(
                        {"unit": t["id"], "at": rr.inserted_at})
                else:
                    stats["removed"].append({"unit": t["id"]})
        except (ValueError, OSError) as e:
            stats["errors"].append({"unit": u["id"], "error": str(e)})

    if dry_run:
        return stats

    # 実適用: rescan で条を確定させ、applied_unit_id と状態を進める
    scan(store, pr["agent_name"], root)
    for u in units:
        if u["action"] == "remove":
            store.set_status(u["target_unit_id"], "quarantined", reviewer,
                             reason=f"pr#{pr_id} remove")
            store.commit()
            continue
        uid = _find_unit_id(store, u["file_path"], u["raw_text"])
        if uid is not None:
            store.conn.execute(
                "UPDATE proposed_units SET applied_unit_id=? WHERE id=?",
                (uid, u["id"]))
            store.set_status(uid, "provisional_ai", reviewer,
                             reason=f"pr#{pr_id} {u['action']}")
    if not stats["errors"]:
        store.conn.execute(
            "UPDATE pull_requests SET state='merged' WHERE id=?", (pr_id,))
    store.audit("system", "pr_applied", "pull_request", pr_id,
                json.dumps({"errors": len(stats["errors"]),
                            "merged": not stats["errors"]}))
    store.commit()
    return stats
