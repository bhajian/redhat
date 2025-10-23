import json, sys, statistics as stats
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else "results.jsonl"

rows = []
with open(path, encoding="utf-8") as f:
    for line in f:
        try:
            rows.append(json.loads(line))
        except Exception:
            pass

def get_delta(r):
    if "delta_full_ms" in r:
        return r["delta_full_ms"]
    # legacy field name
    if "delta_ms" in r:
        return r["delta_ms"]
    if "warm_full_ms" in r and "cold_full_ms" in r:
        return round(r["warm_full_ms"] - r["cold_full_ms"], 2)
    return None

by_target = defaultdict(list)
by_target_fftp = defaultdict(list)

for r in rows:
    t = r.get("target", "unknown")
    d = get_delta(r)
    if d is not None:
        by_target[t].append(d)
    if "warm_fftp_ms" in r and "cold_fftp_ms" in r:
        by_target_fftp[t].append(round(r["warm_fftp_ms"] - r["cold_fftp_ms"], 2))

def summarize(name, arr):
    if not arr:
        return f"{name}: n=0"
    arr_sorted = sorted(arr)
    p10 = arr_sorted[max(0, int(0.10 * (len(arr_sorted)-1)))]
    p90 = arr_sorted[min(len(arr_sorted)-1, int(0.90 * (len(arr_sorted)-1)))]
    return (f"{name}: n={len(arr)}  "
            f"meanΔ={stats.mean(arr):.1f} ms  "
            f"medianΔ={stats.median(arr):.1f} ms  "
            f"p10={p10:.1f}  p90={p90:.1f}")

print("=== Full latency deltas (warm - cold) ===")
for tgt, arr in by_target.items():
    print(summarize(tgt.upper(), arr))

print("\n=== FFTP deltas (warm - cold) ===")
for tgt, arr in by_target_fftp.items():
    print(summarize(tgt.upper(), arr))
