"""状態遷移ルール（ADR-0003「状態遷移」節）。

アプリ層で検査する（DDL の CHECK では行間制約を表せない）。
AI 単独の確定は provisional_ai のみ。例外として quarantined も
AI が自動遷移してよい（op-auto-quarantine: 外す方向は無害・復元可能）。
"""

ALLOWED: dict[str, set[str]] = {
    "under_review": {"approved", "rejected", "quarantined", "provisional_ai"},
    "provisional_ai": {"approved", "rejected", "quarantined"},
    "approved": {"quarantined", "under_review"},
    "quarantined": {"approved", "rejected"},
    "rejected": {"under_review"},
}

# 新規条（現状態なし）から入れる初期状態
INITIAL = {"under_review", "provisional_ai"}

# AI が単独で確定してよい遷移（それ以外の ai:* 決定は監査上「要確認」）
AI_AUTO = {("under_review", "provisional_ai"), ("under_review", "quarantined")}


class IllegalTransition(Exception):
    pass


def check_transition(
    from_status: str | None,
    to_status: str,
    decided_by: str,
) -> str | None:
    """遷移可否を検査。合法なら None、AI 自動だが要確認対象なら
    'review'、違法なら IllegalTransition を送出する。"""
    if from_status is None:
        if to_status not in INITIAL:
            raise IllegalTransition(
                f"new unit cannot enter {to_status} (allowed: {INITIAL})"
            )
        return None
    allowed = ALLOWED.get(from_status, set())
    if to_status not in allowed:
        raise IllegalTransition(
            f"{from_status} -> {to_status} is not allowed"
        )
    if decided_by.startswith("ai:") and (from_status, to_status) not in AI_AUTO:
        return "review"  # AI による非自動遷移 → 監査上要確認
    return None
