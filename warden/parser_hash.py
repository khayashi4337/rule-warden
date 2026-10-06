"""条の正規化と content_hash（ADR-0002 parse-unit-hash）。

norm_text = 空白・改行を正規化した条本文（RuleUnit.norm_text()）
content_hash = sha256(norm_text) の先頭 16 hex
"""

from __future__ import annotations

import hashlib

from warden.parser_units import RuleUnit


def content_hash(unit: RuleUnit) -> str:
    return hashlib.sha256(unit.norm_text().encode("utf-8")).hexdigest()[:16]
