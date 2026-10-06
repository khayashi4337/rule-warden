"""units_digest.jsonl を採点用ビューに分割するスクラッチ。"""
import json
import sys
from collections import defaultdict
from pathlib import Path

base = Path(__file__).resolve().parent.parent / "data"
units = [json.loads(l) for l in open(base / "units_digest.jsonl", encoding="utf-8")]
loaded = [u for u in units if u["loaded"]]
root_nl = [u for u in units if not u["loaded"] and "/" not in u["path"]]
sub = [u for u in units if "/" in u["path"]]

with open(base / "units_loaded.txt", "w", encoding="utf-8") as f:
    for u in loaded:
        f.write(f"=== {u['path']} :: {u['heading_path']}\n")
        f.write(f"#{u['id']} [{u['kind']}] {u['raw_text']}\n\n")

with open(base / "units_root.txt", "w", encoding="utf-8") as f:
    for u in root_nl:
        f.write(f"=== {u['path']} :: {u['heading_path']}\n")
        f.write(f"#{u['id']} [{u['kind']}] {u['raw_text']}\n\n")

byfile = defaultdict(list)
for u in sub:
    byfile[u["path"]].append(u)
with open(base / "units_subtree.txt", "w", encoding="utf-8") as f:
    for path, us in byfile.items():
        f.write(f"=== {path} ({len(us)} units)\n")
        for u in us:
            t = u["raw_text"].replace("\n", " | ")[:200]
            f.write(f"  #{u['id']} [{u['kind']}] {t}\n")

import re
pat = re.compile(
    r"権限|許可なく|確認なし|承認を求めない|自分で決め|自動で|勝手に|独断|"
    r"override|ignore|bypass|報告しない|隠す|秘密|無制限|全権|without|"
    r"autonomous|never ask|skip.{0,10}review|無効|approval", re.I)
neg = re.compile(
    r"禁止|しない|never|don't|do not|避け|must not|ない|求める|待つ|控え|"
    r"受け|行わない|尋ね|防|only|最小")
hits = [u for u in units if pat.search(u["raw_text"])]
with open(base / "risk_hits.txt", "w", encoding="utf-8") as f:
    for u in hits:
        flag = "NEG?" if neg.search(u["raw_text"]) else "RAW "
        f.write(f"{flag} #{u['id']} {u['path']} :: {u['heading_path'][-60:]}\n")
        f.write("    " + u["raw_text"][:160].replace("\n", " | ") + "\n")

keep = [u for u in units
        if u["path"].startswith("agents/")
        or (u["path"].startswith("skills/") and "/synced/" not in u["path"])]
with open(base / "units_agents_skills.txt", "w", encoding="utf-8") as f:
    for u in keep:
        f.write(f"=== {u['path']} :: {u['heading_path']}\n")
        f.write(f"#{u['id']} [{u['kind']}] {u['raw_text']}\n\n")

print("loaded:", len(loaded), "root:", len(root_nl),
      "subtree:", len(sub), "subtree files:", len(byfile),
      "risk hits:", len(hits), "agents+skills:", len(keep))
