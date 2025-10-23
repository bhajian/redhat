#!/usr/bin/env python3
# kv_latency_demo.py — simple KV-cache latency benchmark for llm-d gateway vs loadbalancer.
# Reads 'prompts.txt' with pipe-separated fields: prompt1|prompt2|topic

import argparse, json, time, requests, sys

def read_pair(path, index):
    """Reads one prompt pair (pipe-separated)."""
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == index:
                parts = line.rstrip("\n").split("|")
                if len(parts) < 2:
                    raise SystemExit(f"Line {index} malformed (needs at least 2 fields separated by '|').")
                p1, p2 = parts[0].strip(), parts[1].strip()
                topic = parts[2].strip() if len(parts) >= 3 else None
                return p1, p2, topic
    raise SystemExit(f"Index {index} out of range for {path}")

def pick_endpoint(mode, lb_url, gw_url):
    if mode == "lb":
        if not lb_url:
            raise SystemExit("--lb-url is required when mode=lb")
        return lb_url.rstrip("/")
    if mode == "gw":
        if not gw_url:
            raise SystemExit("--gw-url is required when mode=gw")
        return gw_url.rstrip("/")
    raise SystemExit("mode must be lb or gw")

def post_once(base, model, prompt, timeout, stream, close_conn):
    """Makes one /v1/chat/completions call and returns (fftp_s, full_s, json_response)."""
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
        headers["Connection"] = "close"  # force fresh TCP for LB mode

    t0 = time.perf_counter()

    # Non-streaming mode
    if not stream:
        with requests.Session() as s:
            r = s.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
        t1 = time.perf_counter()
        try:
            j = r.json()
        except Exception:
            j = {"status": r.status_code, "text": r.text}
        return (t1 - t0), (t1 - t0), j

    # Streaming mode
    with requests.Session() as s:
        r = s.post(url, headers=headers, data=json.dumps(payload), timeout=timeout, stream=True)
        fftp = None
        last = {}
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
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
    ap = argparse.ArgumentParser(description="KV-cache latency demo for llm-d gateway vs loadbalancer.")
    ap.add_argument("--file", default="prompts.txt", help="Pipe-separated file: prompt1|prompt2|topic")
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--mode", choices=["lb", "gw"], required=True)
    ap.add_argument("--lb-url", default=None)
    ap.add_argument("--gw-url", default=None)
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B")
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--warmup", type=int, default=0)
    ap.add_argument("--stream", action="store_true", help="Use streaming to measure FFTP")
    ap.add_argument("--jsonl", default="results.jsonl")
    args = ap.parse_args()

    base = pick_endpoint(args.mode, args.lb_url, args.gw_url)
    p1, p2, topic = read_pair(args.file, args.index)

    # Optional warmup requests (not recorded)
    for _ in range(max(0, args.warmup)):
        try:
            post_once(base, args.model, "warm up", args.timeout, stream=False,
                      close_conn=(args.mode == "lb"))
        except Exception as e:
            print(f"[warmup] {e}", file=sys.stderr)

    # Cold call
    cold_fftp_s, cold_full_s, cold_json = post_once(
        base, args.model, p1, args.timeout, args.stream, close_conn=(args.mode == "lb")
    )
    time.sleep(0.05)

    # Warm call (related continuation)
    warm_fftp_s, warm_full_s, warm_json = post_once(
        base, args.model, p2, args.timeout, args.stream, close_conn=(args.mode == "lb")
    )

    usage_cold = cold_json.get("usage") if isinstance(cold_json, dict) else None
    usage_warm = warm_json.get("usage") if isinstance(warm_json, dict) else None

    row = {
        "target": args.mode,
        "base_url": base,
        "index": args.index,
        "topic": topic,
        "model": args.model,
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
