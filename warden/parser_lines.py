"""行分類器（ADR-0002 P1/P4）。

Markdown を行単位で分類する。解析しない範囲は
コードフェンス内・HTML コメント内・引用テキスト。

引用テキストの判定:
- `>` で始まる Markdown 引用行
- `[<出所>]` ラベル行に続くブロック（rules_junrule.md 形式）。
  ラベル行の次から、空行・見出し・新しいラベル行が来るまで引用扱い
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class LineKind(Enum):
    HEADING = "heading"
    BULLET = "bullet"
    NUMBERED = "numbered"
    TABLE_ROW = "table_row"
    FENCE = "fence"          # ``` の囲い行自体
    FENCE_BODY = "fence_body"  # フェンス内
    COMMENT = "comment"      # HTML コメント（含む行）
    IMPORT = "import"        # 行頭が @ のインポート参照行
    QUOTE = "quote"          # 引用テキスト（> 行・[出所]ブロック）
    QUOTE_LABEL = "quote_label"  # [出所] ラベル行自体
    BLANK = "blank"
    TEXT = "text"            # その他の非空行（段落行）


@dataclass(frozen=True)
class ClassifiedLine:
    lineno: int   # 1始まり
    kind: LineKind
    raw: str
    indent: int = 0  # 先頭空白の個数（tab=1 として数える）

    @property
    def parsed(self) -> bool:
        """条抽出の対象になりうる行か。"""
        return self.kind not in (
            LineKind.FENCE,
            LineKind.FENCE_BODY,
            LineKind.COMMENT,
            LineKind.QUOTE,
            LineKind.QUOTE_LABEL,
            LineKind.BLANK,
        )


_RE_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_RE_BULLET = re.compile(r"^(\s*)([-*+])\s")
_RE_NUMBERED = re.compile(r"^(\s*)(\d+)[.)]\s")
_RE_TABLE = re.compile(r"^\s*\|.*\|\s*$")
_RE_FENCE = re.compile(r"^\s*```")
_RE_TILDE_FENCE = re.compile(r"^\s*~~~")
_RE_COMMENT_OPEN = re.compile(r"<!--")
_RE_COMMENT_CLOSE = re.compile(r"-->")
_RE_IMPORT = re.compile(r"^\s*@")
_RE_QUOTE = re.compile(r"^\s*>")
_RE_QUOTE_LABEL = re.compile(r"^\s*\[[^\]]+\]\s*$")

# @ 参照の抽出（行内の任意位置・表セル内も対象。ADR-0002 P4）
_RE_AT_REF = re.compile(r"@([A-Za-z0-9_\-./\\぀-ヿ一-龥]{2,})")


def at_refs(line: str) -> list[str]:
    """行内の @ 参照パスを全部返す（表セル内も含む）。"""
    refs = []
    for m in _RE_AT_REF.finditer(line):
        path = m.group(1).rstrip(".,;:）)。、")
        if path:
            refs.append(path)
    return refs


def _indent(raw: str) -> int:
    n = 0
    for ch in raw:
        if ch == " " or ch == "\t":
            n += 1
        else:
            break
    return n


def classify_lines(text: str) -> list[ClassifiedLine]:
    """テキスト全体を行単位で分類して返す。"""
    out: list[ClassifiedLine] = []
    in_fence = False
    in_comment = False
    in_quote_block = False  # [出所] ラベルに続く引用ブロック

    for i, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()

        # --- 状態の継続判定 ---
        if in_fence:
            if _RE_FENCE.match(raw) or _RE_TILDE_FENCE.match(raw):
                in_fence = False
                out.append(ClassifiedLine(i, LineKind.FENCE, raw, _indent(raw)))
            else:
                out.append(ClassifiedLine(i, LineKind.FENCE_BODY, raw, _indent(raw)))
            continue

        if in_comment:
            if _RE_COMMENT_CLOSE.search(raw):
                in_comment = False
            out.append(ClassifiedLine(i, LineKind.COMMENT, raw, _indent(raw)))
            continue

        # --- 各行の判定 ---
        if _RE_FENCE.match(raw) or _RE_TILDE_FENCE.match(raw):
            in_fence = True
            out.append(ClassifiedLine(i, LineKind.FENCE, raw, _indent(raw)))
            continue

        opens = list(_RE_COMMENT_OPEN.finditer(raw))
        if opens:
            closes = list(_RE_COMMENT_CLOSE.finditer(raw))
            # <!-- ... --> が同じ行で完結しないならコメント状態へ
            if len(closes) < len(opens) or (
                opens and (not closes or closes[-1].end() < opens[-1].start())
            ):
                in_comment = True
            out.append(ClassifiedLine(i, LineKind.COMMENT, raw, _indent(raw)))
            continue

        # 引用ブロックの継続/終了
        if in_quote_block:
            if stripped == "" or _RE_HEADING.match(raw) or _RE_QUOTE_LABEL.match(raw):
                in_quote_block = False
            else:
                out.append(ClassifiedLine(i, LineKind.QUOTE, raw, _indent(raw)))
                continue

        if stripped == "":
            out.append(ClassifiedLine(i, LineKind.BLANK, raw, 0))
            continue
        if _RE_HEADING.match(raw):
            out.append(ClassifiedLine(i, LineKind.HEADING, raw, _indent(raw)))
            continue
        if _RE_QUOTE_LABEL.match(raw):
            in_quote_block = True
            out.append(ClassifiedLine(i, LineKind.QUOTE_LABEL, raw, _indent(raw)))
            continue
        if _RE_QUOTE.match(raw):
            out.append(ClassifiedLine(i, LineKind.QUOTE, raw, _indent(raw)))
            continue
        if _RE_IMPORT.match(raw):
            out.append(ClassifiedLine(i, LineKind.IMPORT, raw, _indent(raw)))
            continue
        if _RE_TABLE.match(raw):
            out.append(ClassifiedLine(i, LineKind.TABLE_ROW, raw, _indent(raw)))
            continue
        if _RE_BULLET.match(raw):
            out.append(ClassifiedLine(i, LineKind.BULLET, raw, _indent(raw)))
            continue
        if _RE_NUMBERED.match(raw):
            out.append(ClassifiedLine(i, LineKind.NUMBERED, raw, _indent(raw)))
            continue
        out.append(ClassifiedLine(i, LineKind.TEXT, raw, _indent(raw)))

    return out
