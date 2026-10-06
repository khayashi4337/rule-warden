"""Markdown 読み込みの耐故障（負例対応: BOM / UTF-16 / 空）。

- UTF-8 BOM (utf-8-sig)、UTF-16 LE/BE BOM を検出してデコードする
- デコード不能・読み取り不能は None（呼び出し側でスキップ扱い）
"""

from __future__ import annotations

from pathlib import Path


def read_markdown(path: Path) -> str | None:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if not data:
        return ""
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            return None
    if data.startswith(b"\xef\xbb\xbf"):
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None
