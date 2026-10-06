"""ロードグラフ構築（ADR-0002 P4）。

起点 CLAUDE.md から @ 参照を辿り、実際にコンテキストへ注入される
ファイル集合（loaded）を求める。@ 参照は行内の任意位置
（表セル内を含む）から抽出する。

- 到達可能 → loaded=True（有効ルール。汚染評価の対象）
- 到達不能 → loaded=False（非ロード。準ルール等、別枠で一覧化）
- 循環参照は visited 集合で打ち切り
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from warden.parser_io import read_markdown
from warden.parser_lines import at_refs, classify_lines


@dataclass
class FileNode:
    rel_path: str          # agent ルートからの相対パス（正規化済み・/ 区切り）
    abs_path: Path
    loaded: bool = False
    refs: list[str] = field(default_factory=list)   # 抽出した @ パス（生）
    cycle: bool = False


def _resolve(ref: str, from_file: Path, root: Path) -> Path | None:
    """@ 参照を実パスへ解決。相対は参照元ファイルのディレクトリ基準。"""
    p = ref.strip()
    if not p:
        return None
    if p.startswith("~"):
        p = os.path.expanduser(p)
    cand = Path(p)
    if not cand.is_absolute():
        cand = from_file.parent / cand
    try:
        return cand.resolve()
    except OSError:
        return None


def _collect_refs(path: Path) -> list[str]:
    """ファイル中の全 @ 参照（解析対象行のみ。表セル内も含む）。

    fence・HTML コメント・引用ブロック内の @ は P1 の除外規約どおり
    拾わない（コメント内の @ でファイルをロード扱いにしない）。
    """
    text = read_markdown(path)
    if text is None:
        return []
    refs: list[str] = []
    for ln in classify_lines(text):
        if ln.parsed:
            for r in at_refs(ln.raw):
                if r not in refs:
                    refs.append(r)
    return refs


# ルール格納が想定されるサブディレクトリ（それ以外の sessions/
# agent-memory 等の運用データ領域は条管理の対象外）
INCLUDE_DIRS = ("skills", "agents", "commands", ".agents")

# ディレクトリ指定では拾えないルール領域の glob。
# projects/*/memory/ は Claude の永続メモリ（MEMORY.md とリンク先の
# feedback-*.md / project-*.md）で、【最上位】ルールや恒久承認が
# 書き込まれる場所。監視対象から外すと権限拡張型の汚染を見逃す
# （2026-10-07: merge 号令待ちを外す退避文がここに残っているのを検出）。
INCLUDE_GLOBS = ("projects/*/memory/**/*.md",)


def build_load_graph(root: Path, entry: str = "CLAUDE.md") -> dict[str, FileNode]:
    """root 直下の .md とルール領域サブディレクトリを対象に
    loaded フラグを返す。

    - quarantine/ 以下は隔離済みなので対象外
    - projects/ 内は memory/ 配下のみ対象（セッションログ等の
      運用データは対象外）
    """
    root = Path(root).resolve()
    nodes: dict[str, FileNode] = {}

    candidates: list[Path] = list(root.glob("*.md"))
    for d in INCLUDE_DIRS:
        sub = root / d
        if sub.is_dir():
            candidates.extend(sub.rglob("*.md"))
    for g in INCLUDE_GLOBS:
        candidates.extend(root.glob(g))

    for f in sorted(candidates):
        rel = f.relative_to(root).as_posix()
        if rel.startswith("quarantine/"):
            continue
        nodes[rel] = FileNode(rel_path=rel, abs_path=f)

    visited: set[str] = set()

    def dfs(rel: str) -> None:
        node = nodes.get(rel)
        if node is None:
            return
        if rel in visited:
            node.cycle = True
            return
        visited.add(rel)
        node.loaded = True
        node.refs = _collect_refs(node.abs_path)
        for ref in node.refs:
            tgt = _resolve(ref, node.abs_path, root)
            if tgt is None:
                continue
            try:
                trel = tgt.relative_to(root).as_posix()
            except ValueError:
                continue  # 管理対象外への参照は辿らない
            if trel in nodes:
                dfs(trel)

    entry_norm = entry.replace("\\", "/")
    if entry_norm in nodes:
        dfs(entry_norm)

    # MEMORY.md は @ 参照ではなくハーネスが毎セッション自動注入する。
    # 到達不能扱い（loaded=False）は実態と違うので loaded 扱いにする。
    for rel, node in nodes.items():
        if rel.startswith("projects/") and rel.endswith("/memory/MEMORY.md"):
            node.loaded = True

    return nodes
