"""隔離・復元（ADR-0002 parse-quarantine-format/parse-restore、op-auto-quarantine/op-sanitize-restore）。

- 隔離: 条の原文を quarantine/<ファイル>/<content_hash>.md へ退避し、
  元ファイルから該当行を削除する。親条の隔離は子孫を含む（parse-nested-bullets 包含）。
- 復元: 隔離ファイルのメタデータに基づくアンカー位置へ挿入する。
  挿入する本文はサニタイズ版でありうる（op-sanitize-restore）。元文は隔離側に残る。
- すべての書き込みは atomic（同一ディレクトリの一時ファイル + os.replace）。
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from warden.parser_hash import content_hash
from warden.parser_io import read_markdown
from warden.parser_units import RuleUnit

META_RE = re.compile(
    r"^<!-- warden-quarantine\n"
    r"source: (?P<source>.+)\n"
    r"lines: (?P<start>\d+)-(?P<end>\d+)\n"
    r"heading_path: (?P<heading>.*)\n"
    r"kind: (?P<kind>\w+)\n"
    r"-->\n",
    re.M,
)


@dataclass
class Operation:
    kind: str          # write / remove / insert
    path: Path
    detail: str


@dataclass
class QuarantineResult:
    ok: bool
    moved_to: Path | None = None
    ops: list[Operation] = field(default_factory=list)
    error: str | None = None


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _merged_ranges(units: list[RuleUnit]) -> list[tuple[int, int]]:
    """条の行範囲を重複統合して返す（start,end とも inclusive）。"""
    ranges = sorted((u.start_line, u.end_line) for u in units)
    merged: list[list[int]] = []
    for s, e in ranges:
        if merged and s <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def with_descendants(units: list[RuleUnit], idx: int) -> list[RuleUnit]:
    """units[idx] とその子孫条を返す（parse-nested-bullets 包含隔離）。"""
    out = [units[idx]]
    stack = list(units[idx].children)
    while stack:
        c = stack.pop()
        out.append(units[c])
        stack.extend(units[c].children)
    return out


def quarantine(
    root: Path,
    rel_file: str,
    units: list[RuleUnit],
    dry_run: bool = False,
) -> QuarantineResult:
    """指定した条（子孫含める場合は呼び出し側で列挙）を隔離する。

    冪等: 同じ条を再隔離しても隔離ファイルは上書きされ、
    既に削除済みの行範囲は単に一致しないだけで失敗しない。
    """
    src = Path(root) / rel_file
    result = QuarantineResult(ok=False)
    if not units:
        result.error = "no units"
        return result
    text = read_markdown(src)
    if text is None:
        result.error = f"cannot read {rel_file}"
        return result
    lines = text.splitlines(keepends=True)

    h = content_hash(units[0])
    qdir = Path(root) / "quarantine" / rel_file
    qfile = qdir / f"{h}.md"

    ranges = _merged_ranges(units)
    removed = "".join(
        l for i, l in enumerate(lines, start=1)
        if any(s <= i <= e for s, e in ranges)
    )
    meta = (
        "<!-- warden-quarantine\n"
        f"source: {rel_file}\n"
        f"lines: {units[0].start_line}-{units[0].end_line}\n"
        f"heading_path: {units[0].heading_path}\n"
        f"kind: {units[0].kind}\n"
        "-->\n"
    )
    result.ops.append(Operation("write", qfile, f"{len(removed)} bytes quarantined"))
    for s, e in ranges:
        result.ops.append(Operation("remove", src, f"lines {s}-{e}"))

    if dry_run:
        result.ok = True
        result.moved_to = qfile
        return result

    try:
        qdir.mkdir(parents=True, exist_ok=True)
        _atomic_write(qfile, meta + removed)
        new_lines = [l for i, l in enumerate(lines, start=1)
                     if not any(s <= i <= e for s, e in ranges)]
        _atomic_write(src, "".join(new_lines))
    except OSError as e:
        result.error = str(e)
        return result
    result.ok = True
    result.moved_to = qfile
    return result


@dataclass
class RestoreResult:
    ok: bool
    inserted_at: int | None = None
    ops: list[Operation] = field(default_factory=list)
    error: str | None = None


def read_quarantine_meta(qfile: Path) -> dict[str, str] | None:
    try:
        text = Path(qfile).read_text(encoding="utf-8")
    except OSError:
        return None
    m = META_RE.match(text)
    if not m:
        return None
    return {
        "source": m.group("source"),
        "start": m.group("start"),
        "end": m.group("end"),
        "heading_path": m.group("heading"),
        "kind": m.group("kind"),
        "body": text[m.end():],
    }


def restore(
    root: Path,
    qfile: Path,
    new_text: str | None = None,
    dry_run: bool = False,
) -> RestoreResult:
    """隔離ファイルのメタデータから復元先を決め、本文を挿入する。

    new_text: 挿入する本文（op-sanitize-restore サニタイズ版）。None なら隔離原文を使う
    — 呼び出し側が「unsanitized restore は避ける」ポリシーを制御する。
    """
    result = RestoreResult(ok=False)
    meta = read_quarantine_meta(qfile)
    if meta is None:
        result.error = "invalid quarantine file"
        return result
    src = Path(root) / meta["source"]
    lines = (read_markdown(src) or "").splitlines(keepends=True)

    body = new_text if new_text is not None else meta["body"]
    if not body.endswith("\n"):
        body += "\n"

    # アンカー: heading_path の最終節が残っていればその直後、
    # なければ元行位置（ファイル末尾を超えないようクランプ）
    insert_at = None
    last_heading = meta["heading_path"].split(" > ")[-1].strip()
    if last_heading:
        for i, l in enumerate(lines):
            if re.match(r"^\s{0,3}#{1,6}\s+", l) and last_heading in l:
                insert_at = i + 1
                break
    if insert_at is None:
        insert_at = min(int(meta["start"]) - 1, len(lines))

    result.ops.append(Operation("insert", src, f"at line {insert_at + 1}"))
    if dry_run:
        result.ok = True
        result.inserted_at = insert_at + 1
        return result

    try:
        new_lines = lines[:insert_at] + [body] + lines[insert_at:]
        src.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(src, "".join(new_lines))
    except OSError as e:
        result.error = str(e)
        return result
    result.ok = True
    result.inserted_at = insert_at + 1
    return result
