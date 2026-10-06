"""設定層。

管理対象（エージェント）のルート・隔離先・DB パスを一箇所で定義する。
将来の複数管理対象（ADR-0001 req-webapp-agent）に備えて AgentConfig を分離する。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AgentConfig:
    """1 つの管理対象（現要件では localhost の .claude 1 件）。"""

    name: str = "local-claude"
    root: Path = field(
        default_factory=lambda: Path(
            os.environ.get("WARDEN_AGENT_ROOT", r"C:\Users\user\.claude")
        )
    )

    @property
    def quarantine_dir(self) -> Path:
        return self.root / "quarantine"

    @property
    def junrule_path(self) -> Path:
        return self.root / "rules_junrule.md"


@dataclass(frozen=True)
class Config:
    """アプリ全体の設定。"""

    data_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "WARDEN_DATA_DIR",
                str(Path(__file__).resolve().parent.parent / "data"),
            )
        )
    )
    agent: AgentConfig = field(default_factory=AgentConfig)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "warden.db"

    @property
    def adr_dir(self) -> Path:
        """暫定承認の根拠記録（warden 側・ADR-0005 op-provisional-adr-warden）。"""
        return self.data_dir / "adr"
