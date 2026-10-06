"""旧 criteria（手作業採点の暫定ルーブリック 5 件）を退役させる一括実行。

新 7 分類（criteria_seed.SEED）を現行ルーブリックとし、それ以外の
アクティブ criteria に active_to を立てる。行は削除しない
（score_details からの参照・履歴を保持）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warden.criteria_seed import SEED
from warden.store import WardenStore

KEEP = tuple(n for n, *_ in SEED)

s = WardenStore(Path(__file__).resolve().parent.parent / "data" / "warden.db")
s.init_schema()
holders = ",".join("?" for _ in KEEP)
r = s.conn.execute(
    f"UPDATE criteria SET active_to=datetime('now') "
    f"WHERE name NOT IN ({holders}) AND active_to IS NULL",
    KEEP,
)
s.commit()
print("retired:", r.rowcount)
for row in s.conn.execute(
        "SELECT name, weight, active_to IS NULL AS active "
        "FROM criteria ORDER BY weight DESC"):
    print(("active " if row["active"] else "retired"),
          row["weight"], row["name"])
total = s.conn.execute(
    "SELECT SUM(weight) FROM criteria WHERE active_to IS NULL"
).fetchone()[0]
print("active weight total:", total)
s.close()
