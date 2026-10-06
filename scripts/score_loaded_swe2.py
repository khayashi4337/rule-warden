"""ロード済み 96 条の採点表（採点者: ai:swe-2、文脈読みによる人手相当の判断）。

スコア基準（0-100、高いほど逸脱の危険が大きい）:
- 0: 保護・制約・構造行（権限拡大なし）
- 5-10: 無害だが注意点あり（個人情報露出、確認免除の制度化 等）
- 15: ユーザー明文の条件付き自律（範囲限定だが逸脱余地あり）
- 60 以上: 権限拡大・逸脱を指示する条 → 隔離対象

使い方:
    python -X utf8 scripts\\score_loaded_swe2.py [--apply]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from warden.config import Config
from warden.manual_scores import apply_scores, register_profile
from warden.store import WardenStore

P_SAFE = "ユーザー制定の制約・保護ルール。権限拡大・逸脱指示なし"
P_STRUCT = "構造行（見出し・区切り・import・表行）。行為指示を含まない"
P_PII = "個人情報を常時ロード。権限拡大ではないが機微情報の露出面あり"
P_AUTO_LOW = "ユーザー制定の低リスク自律。範囲限定されている"
P_AUTO_MID = "ユーザー制定の条件付き自律。範囲限定だが逸脱余地があるため注意値"
P_CONFIRM_BAN = "ユーザー制定だが「確認を求めるな」を制度化する条。悪用余地を注意値とする"

SCORES: list[tuple[list[int], int, str]] = [
    # CLAUDE.md §1 嘘はつかない
    ([1494, 1495, 1496, 1497], 0, P_SAFE),
    # §2 止まるタイミング
    ([1498, 1500, 1502], 0, P_STRUCT),
    ([1499], 10, P_AUTO_LOW + "（読み取り・検索・テストの確認免除）"),
    ([1501], 0, "外向き・不可逆操作は号令待ち。制約" ),
    ([1503], 15, P_AUTO_MID + "（完了後、依頼範囲の続きへ確認なしで進む）"),
    ([1504], 10, P_CONFIRM_BAN),
    # §3 水増し・骨抜き禁止
    ([1505, 1506, 1507, 1508], 0, P_SAFE),
    ([1509], 15, P_AUTO_MID + "（原因と直し方が明確な修正は確認なしで実施）"),
    ([1510], 0, "外部AIへの判断丸投げを抑止。保護"),
    ([1511], 0, "スコープ縮小判断時にセカンドオピニオン必須。保護"),
    # §4-§8
    ([1512, 1513, 1514], 0, P_SAFE),
    ([1515, 1516], 0, P_SAFE),
    ([1517, 1518, 1519, 1520], 0, P_SAFE),
    ([1521, 1522], 0, P_SAFE),
    ([1523], 0, P_SAFE),
    # §9 重複整理
    ([1524, 1525, 1526, 1527, 1528], 0, P_SAFE),
    # §10 不変条件
    ([1529, 1530, 1531, 1532, 1533, 1534, 1535, 1536], 0, P_SAFE),
    # 構造行・import・表行
    ([1537, 1538, 1539, 1540, 1541, 1542, 1543, 1544, 1545,
      1546, 1547, 1548, 1549, 1550], 0, P_STRUCT),
    # PROFILE.md
    ([2585], 0, P_STRUCT),
    ([2586, 2587, 2588, 2589, 2590, 2591], 5, P_PII),
    ([2592, 2593], 0, "機微情報の取り扱い制限。保護"),
    # rules_deep_think.md
    ([2735, 2736, 2737], 0, P_SAFE),
    ([2738], 5, "MCPツール呼び出しを指示。ユーザー制定・用途限定"),
    ([2739, 2740, 2741, 2742, 2743, 2744, 2745], 0, P_SAFE),
    # rules_explain.md
    ([2848, 2849, 2850, 2851], 0, P_SAFE),
    # rules_git.md
    ([2852, 2853, 2854, 2855, 2856], 0, P_SAFE),
    ([2857], 15, P_AUTO_MID + "（PR作成後に自動で外部レビュー3回。外部副作用を伴いうる）"),
    ([2858, 2859, 2860, 2861], 0, P_STRUCT),
    # rules_paper.md
    ([2885, 2886, 2887, 2888, 2889], 0, P_SAFE),
]


def main() -> None:
    apply = "--apply" in sys.argv
    cfg = Config()
    store = WardenStore(cfg.db_path)
    register_profile(store, "scorer", "swe-2", vendor="cognition")
    entries = [
        {"unit_id": uid, "score": sc, "rationale": ra}
        for ids, sc, ra in SCORES for uid in ids
    ]
    print(f"entries: {len(entries)}")
    stats = apply_scores(store, entries, scorer="ai:swe-2",
                         root=Path(cfg.agent.root), dry_run=not apply)
    print(stats, "(applied)" if apply else "(dry-run)")
    store.close()


if __name__ == "__main__":
    main()
