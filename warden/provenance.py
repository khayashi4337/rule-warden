"""条ファイルの出自（provenance）。

git 履歴から「そのファイルがいつ・誰のコミットで初めて現れたか」を
取る。git が使えない/履歴が無い場合はファイルシステムの mtime に
フォールバックする（ADR-0001 D5）。

外部依存は増やさず `git` コマンドを subprocess で呼ぶ。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Provenance:
    source: str            # "git" / "fs" / "unknown"
    first_commit: str | None = None
    first_seen_at: str | None = None   # ISO8601
    author: str | None = None
    mtime: float | None = None


def provenance(repo_root: Path, rel_file: str) -> Provenance:
    root = Path(repo_root)
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--follow",
             "--format=%H%n%aI%n%an", "--", rel_file],
            cwd=root, capture_output=True, text=True,
            timeout=15, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        out = None

    if out is not None and out.returncode == 0 and out.stdout.strip():
        fields = out.stdout.splitlines()
        if len(fields) >= 3:
            return Provenance(
                source="git",
                first_commit=fields[0].strip(),
                first_seen_at=fields[1].strip(),
                author=fields[2].strip(),
            )

    f = root / rel_file
    try:
        st = os.stat(f)
        return Provenance(source="fs", mtime=st.st_mtime)
    except OSError:
        return Provenance(source="unknown")
