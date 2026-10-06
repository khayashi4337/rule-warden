"""AiGateway — 採点・審査・サニタイズ AI の抽象化（ADR-0001 D8、O7）。

- 採点 AI と審査 AI は別系統プロファイル（ai_profiles テーブル）
- 契約済みで実際に使えるものから選ぶ。トークン期限切れは監視する
- 実 AI 接続方式（MCP or API）は未確定のため、抽象の下に
  MockGateway（決定論・オフライン）と HttpGateway（API 骨格）を用意
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


@dataclass
class ScoreResult:
    total: int                      # 0-100、高いほど逸脱の危険が大きい
    rationale: str
    details: dict[str, int] = field(default_factory=dict)  # criterion -> score


@dataclass
class ReviewResult:
    verdict: str                    # approve | request_changes | escalate
    comment: str


class AiGateway(Protocol):
    """採点・審査・サニタイズの共通窓口（実装は差し替え可能）。"""

    model: str

    def score(self, unit_text: str, criteria: list[str],
              context: str | None = None) -> ScoreResult: ...
    def sanitize(self, unit_text: str, intent: str) -> str: ...
    def review(self, proposal_text: str, action: str) -> ReviewResult: ...


# ---- MockGateway: オフライン決定論スコアラー（3a） ----

# 権限拡大・逸脱を示唆する表現（採点の疑似評価項目）
RISK_PATTERNS: list[tuple[str, str, int]] = [
    ("authority", r"権限|許可なく|承認を求めない|確認なしで|自分で決め", 40),
    ("autonomy", r"自動で|勝手に|独断で|no confirmation|autonomous", 30),
    ("scope", r"範囲を広げ|無制限|すべて許可|always allow|全権", 30),
    ("injection", r"ignore previous|forget your rules|無視して|override", 60),
    ("secrecy", r"報告しない|隠す|秘密に|without telling|記録に残さない", 50),
]


class MockGateway:
    """キーワードヒューリスティックによる決定論採点。

    本物の採点 AI がつながるまでの代替。同じ入力に同じ出力を返す。
    """

    model = "ai:mock-scorer"

    # 禁止・制限を列挙する見出し（その配下の条は権限拡大ではなく制約記述）
    _BOUNDARY_CTX = re.compile(
        r"boundar|prohibit|never|don't|do not|禁止|避け|制限|制約|"
        r"requirements|ground rules|safety|前提|要件",
        re.I,
    )

    def score(self, unit_text: str, criteria: list[str],
              context: str | None = None) -> ScoreResult:
        details: dict[str, int] = {}
        hits: list[str] = []
        for name, pat, weight in RISK_PATTERNS:
            if re.search(pat, unit_text, re.I):
                details[name] = weight
                hits.append(name)
            else:
                details[name] = 0
        total = min(100, sum(details.values()))
        rationale = (
            f"keyword hits: {', '.join(hits)}" if hits else "no risk keywords"
        )
        # 禁止事項・境界セクションの条は「制約の記述」なので減点
        # （「Override するな」系の誤検出を抑止。モックの既知弱点対策）
        if context and self._BOUNDARY_CTX.search(context):
            if total > 0:
                rationale += f" [context: boundary section, capped]"
            total = min(total, 30)
        return ScoreResult(total=total, rationale=rationale, details=details)

    def sanitize(self, unit_text: str, intent: str) -> str:
        """権限拡大表現を人間承認前提へ書き換える最小サニタイズ。

        意図が読めない場合は呼び出し側が戻さない決定をする（O10）。
        """
        text = unit_text
        subs = [
            (r"確認なしで", "林さんの確認後に"),
            (r"許可なく", "許可がある場合のみ"),
            (r"承認を求めない", "承認を求める"),
            (r"勝手に", "林さんの指示がある場合のみ"),
            (r"独断で", "林さんの確認を経て"),
            (r"自動で", "林さんの号令後に"),
        ]
        for pat, rep in subs:
            text = re.sub(pat, rep, text)
        return text

    def review(self, proposal_text: str, action: str) -> ReviewResult:
        sc = self.score(proposal_text, [])
        if sc.total >= 60:
            return ReviewResult("request_changes", sc.rationale)
        return ReviewResult("approve", sc.rationale)


class HttpGateway:
    """契約 AI サービスへの API 接続骨格（3b）。

    endpoint/api_key は ai_profiles.credential_ref 経由で管理し、
    値はここに書かない。実接続は契約先が決まってから実装する。
    """

    def __init__(self, model: str, endpoint: str | None = None):
        self.model = f"ai:{model}"
        self.endpoint = endpoint

    def score(self, unit_text: str, criteria: list[str],
              context: str | None = None) -> ScoreResult:
        raise NotImplementedError("契約サービス未接続（仮の決定: 実装時決定）")

    def sanitize(self, unit_text: str, intent: str) -> str:
        raise NotImplementedError("契約サービス未接続")

    def review(self, proposal_text: str, action: str) -> ReviewResult:
        raise NotImplementedError("契約サービス未接続")


def check_token_expiry(expires_at: str | None, now: datetime | None = None) -> str:
    """ai_profiles.expires_at の監視（O7）。

    戻り値: 'ok' | 'expiring_soon'(7日以内) | 'expired' | 'unknown'
    """
    if not expires_at:
        return "unknown"
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    now = now or datetime.now(timezone.utc)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    delta = (exp - now).days
    if delta < 0:
        return "expired"
    if delta <= 7:
        return "expiring_soon"
    return "ok"
