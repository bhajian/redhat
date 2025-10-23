#!/usr/bin/env python3
# kv_latency_demo.py — minimal LB vs Gateway KV/prefix-cache demo with FFTP delta.

import argparse, csv, json, time, requests, sys

def pick_endpoint(mode, lb_url, gw_url):
    if mode == "lb":
        if not lb_url: raise SystemExit("--lb-url is required when mode=lb")
        return lb_url.rstrip("/")
    if mode == "gw":
        if not gw_url: raise SystemExit("--gw-url is required when mode=gw")
        return gw_url.rstrip("/")
    raise SystemExit("mode must be lb or gw")

def read_pair(path, index):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        for i, row in enumerate(r):
            if i == index:
                if len(row) < 2:
                    raise SystemExit(f"CSV line {index} needs at least 2 columns")
                p1, p2 = row[0].strip(), row[1].strip()
                topic = row[2].strip() if len(row) >= 3 else None
                return p1, p2, topic
    raise SystemExit(f"Index {index} out of range for {path}")

def load_shared_prefix(path):
    if not path: return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def build_prompt(prefix, body):
    return (prefix.rstrip() + "\n\n" + body.lstrip()) if prefix else body

def post_once(base, model, prompt, timeout, stream, close_conn):
    """
    Returns: (fftp_s, full_s, last_json)
    - In non-stream mode, fftp_s == full_s
    - In stream mode, we read SSE and take timestamp at first 'data:' payload
    """
    url = f"{base}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 128,
        "temperature": 0.2,
        "stream": bool(stream),
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}

    headers = {"Content-Type": "application/json"}
    if close_conn:
        headers["Connection"] = "close"   # keep LB honest; avoid keep-alive stickiness

    t0 = time.perf_counter()

    if not stream:
        # one-shot session => fresh TCP per call
        with requests.Session() as s:
            r = s.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
        t1 = time.perf_counter()
        j = {}
        try:
            if r.headers.get("content-type","").startswith("application/json"):
                j = r.json()
            else:
                j = {"status": r.status_code, "text": r.text}
        except Exception:
            j = {"status": r.status_code, "text": "<non-json>"}
        return (t1 - t0), (t1 - t0), j

    # streaming path
    with requests.Session() as s:
        r = s.post(url, headers=headers, data=json.dumps(payload), timeout=timeout, stream=True)
        fftp = None
        last = {}
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
                last = obj
            except Exception:
                continue
            if fftp is None:
                fftp = time.perf_counter() - t0
        t1 = time.perf_counter()
        if fftp is None:
            fftp = t1 - t0
        return fftp, (t1 - t0), last

def main():
    ap = argparse.ArgumentParser(description="KV/prefix cache latency demo (LB vs Gateway, no custom headers).")
    ap.add_argument("--file", default="prompts.txt", help="CSV: prompt1,prompt2[,topic]")
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--mode", choices=["lb","gw"], required=True)
    ap.add_argument("--lb-url", default=None)
    ap.add_argument("--gw-url", default=None)
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B")
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--warmup", type=int, default=0, help="warmup calls before timing")
    ap.add_argument("--stream", action="store_true", help="use SSE streaming to capture FFTP")
    ap.add_argument("--shared-prefix-file", default=None, help="identical prefix prepended to BOTH prompts")
    ap.add_argument("--jsonl", default="results.jsonl")
    args = ap.parse_args()

    base = pick_endpoint(args.mode, args.lb_url, args.gw_url)
    p1, p2, topic = read_pair(args.file, args.index)
    prefix = load_shared_prefix(args.shared_prefix_file)

    prompt_cold = build_prompt(prefix, p1)
    prompt_warm = build_prompt(prefix, p2)

    # optional warmups (not recorded)
    for _ in range(max(0, args.warmup)):
        try:
            post_once(base, args.model, "warm up", args.timeout, stream=False,
                      close_conn=(args.mode == "lb"))
        except Exception as e:
            print(f"[warmup] {e}", file=sys.stderr)

    # 1) cold
    cold_fftp_s, cold_full_s, cold_json = post_once(
        base, args.model, prompt_cold, args.timeout, args.stream,
        close_conn=(args.mode == "lb")
    )
    time.sleep(0.05)  # tiny pause regardless of mode

    # 2) warm
    warm_fftp_s, warm_full_s, warm_json = post_once(
        base, args.model, prompt_warm, args.timeout, args.stream,
        close_conn=(args.mode == "lb")
    )

    usage_cold = cold_json.get("usage") if isinstance(cold_json, dict) else None
    usage_warm = warm_json.get("usage") if isinstance(warm_json, dict) else None

    row = {
        "target": args.mode,
        "base_url": base,
        "index": args.index,
        "topic": topic,
        "model": args.model,
        "shared_prefix": bool(prefix),
        "cold_fftp_ms": round(cold_fftp_s * 1000, 2),
        "cold_full_ms": round(cold_full_s * 1000, 2),
        "warm_fftp_ms": round(warm_fftp_s * 1000, 2),
        "warm_full_ms": round(warm_full_s * 1000, 2),
        "delta_fftp_ms": round((warm_fftp_s - cold_fftp_s) * 1000, 2),
        "delta_full_ms": round((warm_full_s - cold_full_s) * 1000, 2),
        "usage_cold": usage_cold,
        "usage_warm": usage_warm,
    }

    print(json.dumps(row, ensure_ascii=False, indent=2))
    try:
        with open(args.jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[warn] failed to append to {args.jsonl}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
