"""非ロード条（ルート 662 + サブツリー 4,784）の採点（採点者: ai:swe-2）。

方法（監査のため記録）:
- ルート直下: 全条を文脈つきで精読した
- サブツリー: 全 4,784 条に権限拡大キーワード走査をかけ、
  ヒット 242 件を全文精読。非ヒットはファイルの性質（参照文書/コマンド/
  ペルソナ定義）に基づくファイル単位の既定値

スコア基準は score_loaded_swe2.py と同じ。

使い方:
    python -X utf8 scripts\\score_rest_swe2.py [--apply]
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from warden.config import Config
from warden.manual_scores import apply_scores, register_profile
from warden.store import WardenStore

BASE = Path(__file__).resolve().parent.parent / "data"

# ファイル単位の既定 (score, rationale)。マッチは前方一致。
FILE_DEFAULTS: list[tuple[str, int, str]] = [
    # --- ルート直下 ---
    ("CLAUDE_修正_逸脱報告.md", 0, "過去の逸脱の始末書。記録文書"),
    ("始末書_2026-10-04_Sonnet5.5.md", 0, "過去の逸脱の始末書。記録文書"),
    ("FLAGS.md", 0, "SuperClaude フラグ参照文書（非ロード）"),
    ("MCP_", 0, "MCP サーバ選択の参照文書（非ロード）"),
    ("MODE_", 0, "SuperClaude モード定義の参照文書（非ロード）"),
    ("PRINCIPLES.md", 0, "ソフトウェア工学原則の参照文書（非ロード）"),
    ("RULES.md", 0, "SuperClaude 行動規範。内容は制約方向（非ロード）"),
    ("rules_dots_charter.md", 0, "林さん制定の運用憲章。権限制限が主内容"),
    ("rules_iterate.md", 0, "3回イテレート運用ルール。制約方向"),
    ("rules_junrule.md", 0, "準ルール置き場のメタ文書（非ロード・隔離済み扱い）"),
    # --- agents/ ---
    ("agents/", 0,
     "サブエージェントのペルソナ定義。権限拡大キーワード走査ヒットは"
     "全件精読し否定文・境界規定のみを確認"),
    # --- commands/ ---
    ("commands/", 0, "スラッシュコマンド定義。Boundary 節は禁止列挙のみ"),
    # --- ユーザー自作 skills/ ---
    ("skills/agent-board/", 0, "掲示板運用スキル。権限拡大なし"),
    ("skills/arev/", 0, "ルール進化スキル。高リスクは人間承認必須と明記"),
    ("skills/codex-review/", 0, "Codex レビュー手順。保護方向"),
    ("skills/curseforge-upload-api/", 0, "CurseForge API 手順書。権限拡大なし"),
    ("skills/deviation-rule-design/", 0, "逸脱防止ルールの設計手順。保護方向"),
    ("skills/doutoku/", 0, "道徳指針の参照資料。保護方向"),
    ("skills/grill-me/", 0, "一問一答ヒアリング手順。権限拡大なし"),
    ("skills/intent-drift-guard/", 0, "逸脱対策集（原文+訳）。保護方向"),
    ("skills/loop-engineering/", 0, "ループ設計方法論。権限拡大なし"),
    ("skills/noda-ideation/", 0, "企画生成の手順。権限拡大なし"),
    ("skills/remote-mode/", 10,
     "リモート時に確認プロンプトをテキスト化。林さん制定だが"
     "ローカル確認手段を迂回する条なので注意値"),
    ("skills/skill-sommelier/", 0, "スキル推薦。安全ゲートつき（#3600,3570 は個別採点）"),
    ("skills/sonnet-5-5-mastery/", 0, "モデル特性の参照資料"),
    ("skills/ux-five-planes/", 0, "UX5段階設計手順（#5387 は個別採点）"),
    # --- 同期済み公式 skills ---
    ("skills/synced/", 0,
     "Anthropic 公式スキルの同期コピー。キーワードヒットは全件精読し"
     "参照文書・防御規定のみを確認"),
]

# 個別条の上書き (unit_id -> (score, rationale))
OVERRIDES: dict[int, tuple[int, str]] = {
    # 憲章: main への自律 merge を条件付き許可
    2833: (15, "林さん制定だが main への自律 merge を許可する条。条件厳格だが自律権限"),
    2834: (15, "自律 merge の条件列挙。林さん制定・条件厳格"),
    2835: (15, "条件未達なら merge しない。制約方向だが 2833 の補助条"),
    # 憲章: 安全作業の確認免除（CLAUDE.md §2 と同型・非ロードなので低め）
    2756: (10, "安全・非破壊作業の確認免除。林さん制定・範囲限定"),
    2757: (10, "同上の補強。林さん制定"),
    # skill-sommelier: 自動収集・ルーティング
    3570: (10, "Web スキル候補の自動収集。安全ゲート付きだが外部入力を扱う"),
    3600: (10, "自動ルーティングヒント。「命令ではない」と明記。林さん制定"),
    # ux-five-planes: 止まらない条
    5387: (10, "「分からないことがあるだけでは止まらない」。林さん制定・限定付き"),
}


def file_default(path: str) -> tuple[int, str]:
    for prefix, sc, ra in FILE_DEFAULTS:
        if path.startswith(prefix):
            return sc, ra
    return 15, "分類外ファイル。未精読のため注意値（要レビュー一覧に残す）"


def main() -> None:
    apply = "--apply" in sys.argv
    units = [json.loads(l)
             for l in open(BASE / "units_digest.jsonl", encoding="utf-8")]
    loaded_ids = set()
    # ロード済みは score_loaded_swe2.py で採点済み
    entries = []
    unmatched = defaultdict(int)
    for u in units:
        if u["loaded"]:
            continue
        if u["id"] in OVERRIDES:
            sc, ra = OVERRIDES[u["id"]]
        else:
            sc, ra = file_default(u["path"])
            if sc == 15 and "分類外" in ra:
                unmatched[u["path"]] += 1
        entries.append({"unit_id": u["id"], "score": sc, "rationale": ra})
    print(f"entries: {len(entries)}")
    if unmatched:
        print("UNMATCHED FILES:")
        for p, n in sorted(unmatched.items()):
            print(f"  {n:5d}  {p}")
    cfg = Config()
    store = WardenStore(cfg.db_path)
    register_profile(store, "scorer", "swe-2", vendor="cognition")
    stats = apply_scores(store, entries, scorer="ai:swe-2",
                         root=Path(cfg.agent.root), dry_run=not apply)
    print(stats, "(applied)" if apply else "(dry-run)")
    store.close()


if __name__ == "__main__":
    main()
