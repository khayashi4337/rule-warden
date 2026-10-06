"""quarantine/ 内の全隔離条を復元し、ステータスを approved に戻す。

誤隔離の一括復旧用。使い方:
    python scripts/restore_quarantined.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warden.config import Config
from warden.orchestrator import scan
from warden.quarantine import read_quarantine_meta, restore
from warden.store import WardenStore


def main() -> int:
    cfg = Config()
    root = Path(cfg.agent.root)
    st = WardenStore(cfg.db_path)
    st.init_schema()

    qdir = root / "quarantine"
    restored = []
    if qdir.is_dir():
        for qf in sorted(qdir.rglob("*.md")):
            meta = read_quarantine_meta(qf)
            if not meta:
                print(f"skip (no meta): {qf}")
                continue
            rr = restore(root, qf)  # new_text=None → 原文を戻す
            print(("OK " if rr.ok else "NG ") + f"{meta['source']} "
                  f"<- {qf.name} @line {rr.inserted_at}")
            if rr.ok:
                restored.append((meta["source"], qf))

    # 再スキャンで条を present=1 に戻す
    stats = scan(st, cfg.agent.name, root)
    print("rescan:", stats)

    # 復元した条のステータスを quarantined -> approved（ai:swe-2 の判断。
    # AI 非自動遷移は監査上「要確認」として記録される）
    for source, qf in restored:
        h = qf.stem  # quarantine ファイル名 = content_hash
        row = st.conn.execute(
            "SELECT ru.id FROM rule_units ru JOIN rule_files rf "
            "ON rf.id=ru.file_id WHERE ru.content_hash=? AND rf.path=?",
            (h, source),
        ).fetchone()
        if row:
            st.set_status(row["id"], "approved", "ai:swe-2",
                          reason="mock false positive: restored")
    st.commit()
    print(f"restored {len(restored)} unit(s)")
    st.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
