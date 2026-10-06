"""一文字記号（D1/O9/P3/S1/C6/M2 等）を意味のある slug に一括リネーム。

対象: docs/ warden/ tests/ HANDOFF.md 配下の .md/.py
使い方: python scripts/rename_ids.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 長い ID から先に置換する必要は \b で不要だが、読みやすさのため定義順に並べる
MAP = {
    # ADR-0001 要件決定（D 群）
    "D1": "req-unit-physical-quarantine",
    "D2": "req-contamination-score",
    "D3": "req-gradual-automation",
    "D4": "req-decontamination",
    "D5": "req-pr-review",
    "D6": "req-status-question",
    "D7": "req-webapp-agent",
    "D8": "req-ai-gateway",
    # ADR-0002 パーサー設計（P 群）
    "P1": "parse-unit-def",
    "P2": "parse-nested-bullets",
    "P3": "parse-unit-hash",
    "P4": "parse-load-graph",
    "P5": "parse-provenance",
    "P6": "parse-quarantine-format",
    "P7": "parse-restore",
    "P8": "parse-rewrite-nature",
    "P9": "parse-impl-policy",
    # ADR-0004 コミットルール（C 群）
    "C1": "commit-subject",
    "C2": "commit-body",
    "C3": "commit-directive-source",
    "C4": "commit-ai-attribution",
    "C5": "commit-provisional-tag",
    "C6": "commit-rule-unit-trailer",
    "C7": "commit-quarantine-prefix",
    "C8": "commit-format-violation",
    # ADR-0005 運用決定（O 群）
    "O1": "op-proceed-default",
    "O2": "op-reviewlist-riskorder",
    "O3": "op-bypass-manual",
    "O4": "op-add-provisional",
    "O5": "op-rewrite-recheck",
    "O6": "op-provisional-adr-warden",
    "O7": "op-ai-separate",
    "O8": "op-junrule-unified-list",
    "O9": "op-auto-quarantine",
    "O10": "op-sanitize-restore",
    "O11": "op-modify-provisional",
    # ADR-0002.5 シーケンス（S 群）
    "S1": "seq-scan-score",
    "S2": "seq-decontam",
    "S3": "seq-proposal",
    "S4": "seq-question",
    # implementation-plan マイルストーン（M 群）
    "M1": "ms-parse-done",
    "M2": "ms-store-done",
    "M3": "ms-ai-done",
    "M4": "ms-ops-done",
}

PATTERNS = [(re.compile(rf"\b{k}\b"), v) for k, v in MAP.items()]

TARGET_DIRS = ["docs", "warden", "tests", "scripts"]
TARGET_FILES = ["HANDOFF.md"]
EXTS = {".md", ".py"}


def main() -> int:
    total = 0
    files = []
    for d in TARGET_DIRS:
        files += [p for p in (ROOT / d).rglob("*")
                  if p.is_file() and p.suffix in EXTS]
    files += [ROOT / f for f in TARGET_FILES if (ROOT / f).exists()]

    for path in sorted(files):
        if path.name == "rename_ids.py":
            continue
        text = path.read_text(encoding="utf-8")
        new, n_file = text, 0
        for pat, slug in PATTERNS:
            new, n = pat.subn(slug, new)
            n_file += n
        if new != text:
            path.write_text(new, encoding="utf-8")
            rel = path.relative_to(ROOT)
            print(f"{rel}: {n_file} replacement(s)")
            total += n_file
    print(f"total: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
