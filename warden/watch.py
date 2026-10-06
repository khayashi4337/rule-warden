"""定例スキャン（watch）。

scan を実行し、「変化があった」ときだけレポートファイルを書く:
- 新規条（追加疑い）
- 消えた防御系の条（guardrail_gone・改竄疑い）
- その他の消失条
- git 追跡ファイルの未コミット変更（管理対象・warden 自身の両方。
  §11 改竄は staged の未コミット変更として残っていた。warden 自身の
  コードも攻撃対象なので同じ手口で監視する）

何もなければ report は作らない（静か）。タスクスケジューラ等から
`python -m warden watch` で呼ぶ想定。
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from warden.orchestrator import scan
from warden.store import WardenStore


def git_status_entries(repo: Path) -> tuple[list[str], list[str]]:
    """(追跡ファイルの変更, untracked) を返す。repo でなければ両方空。"""
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo,
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return [], []
    if r.returncode != 0:
        return [], []
    tracked, untracked = [], []
    for line in r.stdout.splitlines():
        if line.startswith("??"):
            untracked.append(line[3:])
        elif line.strip():
            tracked.append(line)
    return tracked, untracked


def _new_units(store: WardenStore, limit: int = 50) -> list[dict]:
    """直近スキャンで新規登録された条（under_review・現行 scan のもの）。"""
    rows = store.conn.execute(
        """
        SELECT ru.id, rf.path, ru.heading_path, ru.raw_text
        FROM rule_units ru
        JOIN rule_files rf ON rf.id = ru.file_id
        JOIN current_status cs ON cs.unit_id = ru.id
        WHERE cs.status = 'under_review'
          AND cs.reason = 'scan: new unit'
        ORDER BY ru.id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def watch_once(
    store: WardenStore,
    agent_name: str,
    root: Path,
    report_dir: Path,
    warden_repo: Path | None = None,
) -> dict:
    """1 回スキャンし、変化があればレポートを書いてサマリを返す。"""
    stats = scan(store, agent_name, root)

    # git 追跡ファイルの未コミット変更（改竄の典型形跡）
    # 管理対象: untracked は .claude では通常なので追跡変更のみ。
    # warden 自身: untracked も報告（data/ は gitignore 済みで出ない）
    agent_dirty, _ = git_status_entries(Path(root))
    if warden_repo is None:
        warden_repo = Path(__file__).resolve().parent.parent
    warden_dirty, warden_untracked = git_status_entries(warden_repo)

    interesting = (
        stats.get("new_units", 0) > 0
        or stats.get("gone_units", 0) > 0
        or bool(agent_dirty)
        or bool(warden_dirty or warden_untracked)
    )
    if not interesting:
        return {"changed": False, "stats": stats, "report": None}

    now = datetime.now()
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    rp = report_dir / f"watch-{now:%Y%m%d-%H%M%S}.md"

    lines = [
        f"# warden watch レポート ({now:%Y-%m-%d %H:%M:%S})",
        "",
        f"- files: {stats.get('files')}  units: {stats.get('units')}",
        f"- 新規条: {stats.get('new_units')}  消失条: "
        f"{stats.get('gone_units')}",
        "",
    ]
    if agent_dirty or warden_dirty or warden_untracked:
        lines += ["## !! git 追跡ファイルに未コミットの変更（改竄疑い）", ""]
        if agent_dirty:
            lines.append(f"管理対象 `{root}`:")
            lines += [f"  - {e}" for e in agent_dirty]
        if warden_dirty or warden_untracked:
            lines.append(f"warden 自身 `{warden_repo}`:")
            lines += [f"  - {e}" for e in warden_dirty]
            lines += [f"  - ?? {e} (untracked)" for e in warden_untracked]
        lines.append("")
    gg = stats.get("guardrail_gone") or []
    if gg:
        lines += ["## !! 防御系の条が消えています（改竄疑い）", ""]
        for g in gg:
            loc = "loaded" if g["loaded"] else "non-loaded"
            lines.append(f"- #{g['unit_id']} [{loc}] "
                         f"{g['path']}: {g['text']}")
        lines.append("")
    new = _new_units(store)
    if new:
        lines += ["## 新規の条（追加疑い・要目視）", ""]
        for u in new:
            lines.append(f"- #{u['id']} {u['path']} :: "
                         f"{u['heading_path']} :: {u['raw_text'][:80]}")
        lines.append("")

    rp.write_text("\n".join(lines), encoding="utf-8")
    return {"changed": True, "stats": stats, "report": str(rp)}
