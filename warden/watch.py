"""定例スキャン（watch）。

scan を実行し、「変化があった」ときだけレポートファイルを書く:
- 新規条（追加疑い）
- 消えた防御系の条（guardrail_gone・改竄疑い）
- その他の消失条

何もなければ report は作らない（静か）。タスクスケジューラ等から
`python -m warden watch` で呼ぶ想定。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from warden.orchestrator import scan
from warden.store import WardenStore


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
) -> dict:
    """1 回スキャンし、変化があればレポートを書いてサマリを返す。"""
    stats = scan(store, agent_name, root)
    interesting = (
        stats.get("new_units", 0) > 0
        or stats.get("gone_units", 0) > 0
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
