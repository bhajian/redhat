# analyze_results.py
import json, sys, statistics as stats
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else "results.jsonl"
rows = []
with open(path, encoding="utf-8") as f:
    for line in f:
        try:
            rows.append(json.loads(line))
        except:
            pass

by = defaultdict(list)
for r in rows:
    tgt = r.get("target")
    if "delta_full_ms" in r:
        by[tgt].append(r["delta_full_ms"])

for tgt, deltas in by.items():
    print(f"{tgt.upper()}  n={len(deltas)}  "
          f"meanΔ={stats.mean(deltas):.1f} ms  "
          f"medianΔ={stats.median(deltas):.1f} ms  "
          f"p10={stats.quantiles(deltas, n=10)[0]:.1f}  "
          f"p90={stats.quantiles(deltas, n=10)[-1]:.1f}")
    