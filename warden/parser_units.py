"""条抽出（ADR-0002 parse-unit-def/parse-nested-bullets/parse-unit-hash）。

classify_lines の結果から「条（rule unit）」を抽出する。
条の種別: bullet / numbered / paragraph / table_row / import。
- bullet・numbered は全項目が条。子は別条で parent 参照を持つ
  （親の隔離は子孫を含む＝parse-nested-bullets 包含）
- 表は行単位の条。ヘッダ行・区切り行は条にしない（文脈）
- 独立段落は見出し直下の連続した TEXT 行ブロック
- import は行頭 @ の参照行
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from warden.parser_lines import ClassifiedLine, LineKind, classify_lines


@dataclass
class RuleUnit:
    kind: str            # bullet/numbered/paragraph/table_row/import
    raw_text: str
    heading_path: str
    ordinal: int         # 同 heading_path 内での出現順（1始まり）
    start_line: int      # 1始まり・inclusive
    end_line: int        # 1始まり・inclusive
    indent: int = 0
    parent: int | None = None   # units リスト内の親 index（bullet ネスト）
    is_leaf: bool = True
    children: list[int] = field(default_factory=list)

    def norm_text(self) -> str:
        """ADR-0002 parse-unit-hash: 空白・改行を正規化した条本文。"""
        return " ".join(self.raw_text.split())


def _is_table_separator(raw: str) -> bool:
    cells = [c.strip() for c in raw.strip().strip("|").split("|")]
    return all(re.fullmatch(r":?-{1,}:?", c or "-") for c in cells)


def extract_units(text: str) -> list[RuleUnit]:
    """テキストから条を抽出して返す。"""
    lines = classify_lines(text)
    units: list[RuleUnit] = []

    heading_stack: list[str] = []
    ordinal_counter = 0
    bullet_stack: list[tuple[int, int]] = []  # (indent, unit_index)
    last_table_row_unit = -1
    in_table = False
    table_seen_rows = 0
    paragraph_start = -1
    paragraph_lines: list[str] = []
    # 直前の条の継続行吸収用（インデント深い TEXT 行を直前条へ）
    open_unit = -1
    open_indent = -1

    def heading_path() -> str:
        return " > ".join(h for h in heading_stack if h)

    def next_ordinal() -> int:
        nonlocal ordinal_counter
        ordinal_counter += 1
        return ordinal_counter

    def flush_paragraph(end_lineno: int) -> None:
        nonlocal paragraph_start, paragraph_lines
        if paragraph_lines:
            units.append(RuleUnit(
                kind="paragraph",
                raw_text="\n".join(paragraph_lines),
                heading_path=heading_path(),
                ordinal=next_ordinal(),
                start_line=paragraph_start,
                end_line=end_lineno,
            ))
        paragraph_start, paragraph_lines = -1, []

    def close_continuation() -> None:
        nonlocal open_unit, open_indent
        open_unit, open_indent = -1, -1

    for ln in lines:
        if ln.kind == LineKind.HEADING:
            flush_paragraph(ln.lineno - 1)
            close_continuation()
            m = re.match(r"^\s{0,3}(#{1,6})\s+(.*)$", ln.raw)
            level = len(m.group(1))
            title = m.group(2).strip()
            heading_stack = heading_stack[: level - 1]
            while len(heading_stack) < level - 1:
                heading_stack.append("")
            heading_stack.append(title)
            if len(heading_stack) > level:
                heading_stack = heading_stack[:level]
            ordinal_counter = 0
            bullet_stack = []
            in_table = False
            continue

        if not ln.parsed:
            # fence/comment/quote/blank は条をまたがせない
            if ln.kind == LineKind.BLANK:
                flush_paragraph(ln.lineno - 1)
            continue

        if ln.kind == LineKind.TABLE_ROW:
            flush_paragraph(ln.lineno - 1)
            close_continuation()
            if not in_table:
                in_table = True
                table_seen_rows = 0
            table_seen_rows += 1
            if table_seen_rows == 1 or _is_table_separator(ln.raw):
                continue  # ヘッダ行・区切り行は文脈（条にしない）
            units.append(RuleUnit(
                kind="table_row",
                raw_text=ln.raw,
                heading_path=heading_path(),
                ordinal=next_ordinal(),
                start_line=ln.lineno,
                end_line=ln.lineno,
            ))
            last_table_row_unit = len(units) - 1
            continue
        else:
            if in_table:
                in_table = False

        if ln.kind == LineKind.IMPORT:
            flush_paragraph(ln.lineno - 1)
            close_continuation()
            units.append(RuleUnit(
                kind="import",
                raw_text=ln.raw,
                heading_path=heading_path(),
                ordinal=next_ordinal(),
                start_line=ln.lineno,
                end_line=ln.lineno,
            ))
            continue

        if ln.kind in (LineKind.BULLET, LineKind.NUMBERED):
            flush_paragraph(ln.lineno - 1)
            close_continuation()
            # ネスト: indent が浅い親を探す
            while bullet_stack and bullet_stack[-1][0] >= ln.indent:
                bullet_stack.pop()
            parent_idx = bullet_stack[-1][1] if bullet_stack else None
            units.append(RuleUnit(
                kind="bullet" if ln.kind == LineKind.BULLET else "numbered",
                raw_text=ln.raw,
                heading_path=heading_path(),
                ordinal=next_ordinal(),
                start_line=ln.lineno,
                end_line=ln.lineno,
                indent=ln.indent,
                parent=parent_idx,
            ))
            idx = len(units) - 1
            if parent_idx is not None:
                units[parent_idx].is_leaf = False
                units[parent_idx].children.append(idx)
            bullet_stack.append((ln.indent, idx))
            open_unit, open_indent = idx, ln.indent
            continue

        # TEXT 行: 字下げが深いなら直前条の継続行、そうでなければ段落候補
        if ln.kind == LineKind.TEXT:
            if open_unit >= 0 and ln.indent > open_indent:
                u = units[open_unit]
                u.raw_text += "\n" + ln.raw
                u.end_line = ln.lineno
                continue
            close_continuation()
            if paragraph_start < 0:
                paragraph_start = ln.lineno
            paragraph_lines.append(ln.raw)

    flush_paragraph(len(lines))
    return units
