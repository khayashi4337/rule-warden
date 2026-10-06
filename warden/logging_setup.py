"""ロギング設定。

監査のため操作ログを残す。DB の audit_log とは別に、
プロセス動作の診断ログとして使う。
"""

from __future__ import annotations

import logging


def setup(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
