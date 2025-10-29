#!/usr/bin/env python3
# kv_latency_demo.py — KV/prefix-caching latency demo (GW-only).
# Reads 'prompts.txt' with pipe-separated fields: prompt1|prompt2|topic
#
# Outputs one JSON row with TTFT + full latencies for cold (p1) and warm (p2),
# plus deltas and percent improvements.

import argparse, json, time, requests, sys

def read_pair(path, index):
    """Reads one prompt pair (pipe-separated)."""
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == index:
                parts = line.rstrip("\n").split("|", 2)
                if len(parts) < 2:
                    raise SystemExit(f"Line {index} malformed (needs prompt1|prompt2|[topic]).")
                p1, p2 = parts[0].strip(), parts[1].strip()
                topic = parts[2].strip() if len(parts) >= 3 else None
                return p1, p2, topic
    raise SystemExit(f"Index {index} out of range for {path}")

def pct_improve_ms(cold_ms, warm_ms):
    """Return percent improvement: (cold - warm) / cold * 100. None if cold<=0."""
    if cold_ms is None or warm_ms is None or cold_ms <= 0:
        return None
    return round(((cold_ms - warm_ms) / cold_ms) * 100.0, 2)

def has_nonempty_token(obj: dict) -> bool:
    """
    True if this stream chunk carries actual generated token(s), not just role/housekeeping.
    Supports OpenAI/vLLM style deltas.
    """
    try:
        ch = obj["choices"][0]["delta"]
    except Exception:
        return False
    # text token
    if isinstance(ch.get("content"), str) and len(ch["content"]) > 0:
        return True
    # tool calls
    tc = ch.get("tool_calls")
    if isinstance(tc, list) and len(tc) > 0:
        for t in tc:
            fn = t.get("function") if isinstance(t, dict) else None
            if fn and (fn.get("name") or fn.get("arguments")):
                return True
        return True
    # legacy function_call
    fc = ch.get("function_call")
    if isinstance(fc, dict) and (fc.get("name") or fc.get("arguments")):
        return True
    # some providers put reasoning
    if isinstance(ch.get("reasoning"), str) and len(ch["reasoning"]) > 0:
        return True
    return False

def post_once(base, model, prompt, timeout, stream, ttft_mode):
    """
    Makes one /v1/chat/completions call and returns (ttft_s, full_s, last_json_chunk_or_resp).
    TTFT modes:
      - "first-data": time to first SSE 'data:' line
      - "first-content": time to first non-empty token (recommended)
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

    headers = {"Content-Type": "application/json"}  # keep-alive default

    t0 = time.perf_counter()

    # Non-streaming: TTFT == full time
    if not stream:
        with requests.Session() as s:
            r = s.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
        t1 = time.perf_counter()
        try:
            j = r.json()
        except Exception:
            j = {"status": r.status_code, "text": r.text}
        elapsed = t1 - t0
        return elapsed, elapsed, j

    # Streaming: measure TTFT from first non-empty token (or first data if configured)
    with requests.Session() as s:
        r = s.post(url, headers=headers, data=json.dumps(payload), timeout=timeout, stream=True)
        ttft = None
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
            if ttft is None:
                if ttft_mode == "first-data":
                    ttft = time.perf_counter() - t0
                elif ttft_mode == "first-content":
                    if has_nonempty_token(obj):
                        ttft = time.perf_counter() - t0
        t1 = time.perf_counter()
        if ttft is None:
            ttft = t1 - t0
        return ttft, (t1 - t0), last

def main():
    ap = argparse.ArgumentParser(description="KV-cache latency demo (GW only): cold (p1) vs warm (p2).")
    ap.add_argument("--file", default="prompts.txt", help="Pipe-separated file: prompt1|prompt2|topic")
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--gw-url", required=True)
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B")
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--warmup", type=int, default=0, help="Optional pre-calls (not recorded).")
    ap.add_argument("--stream", action="store_true", help="Use streaming to measure TTFT")
    ap.add_argument("--ttft-mode", choices=["first-data", "first-content"], default="first-content",
                    help="TTFT detection: first SSE vs first non-empty token (default).")
    ap.add_argument("--sleep-between", type=float, default=0.05, help="Seconds to sleep between cold and warm calls.")
    ap.add_argument("--jsonl", default="results.jsonl")
    args = ap.parse_args()

    base = args.gw_url.rstrip("/")
    p1, p2, topic = read_pair(args.file, args.index)

    # Optional warmup requests (not recorded)
    for _ in range(max(0, args.warmup)):
        try:
            post_once(base, args.model, "warm up", args.timeout, stream=False, ttft_mode=args.ttft_mode)
        except Exception as e:
            print(f"[warmup] {e}", file=sys.stderr)

    # Cold call (p1)
    cold_ttft_s, cold_full_s, cold_json = post_once(
        base, args.model, p1, args.timeout, args.stream, args.ttft_mode
    )
    time.sleep(max(0.0, args.sleep_between))

    # Warm call (p2)
    warm_ttft_s, warm_full_s, warm_json = post_once(
        base, args.model, p2, args.timeout, args.stream, args.ttft_mode
    )

    # Convert to ms and compute improvements
    cold_ttft_ms = round(cold_ttft_s * 1000, 2)
    cold_full_ms = round(cold_full_s * 1000, 2)
    warm_ttft_ms = round(warm_ttft_s * 1000, 2)
    warm_full_ms = round(warm_full_s * 1000, 2)

    row = {
        "target": "gw",
        "base_url": base,
        "index": args.index,
        "topic": topic,
        "model": args.model,
        "cold_ttft_ms": cold_ttft_ms,
        "cold_full_ms": cold_full_ms,
        "warm_ttft_ms": warm_ttft_ms,
        "warm_full_ms": warm_full_ms,
        "delta_ttft_ms": round(warm_ttft_ms - cold_ttft_ms, 2),
        "delta_full_ms": round(warm_full_ms - cold_full_ms, 2),
        "improve_ttft_pct": pct_improve_ms(cold_ttft_ms, warm_ttft_ms),
        "improve_full_pct": pct_improve_ms(cold_full_ms, warm_full_ms),
        "usage_cold": (cold_json or {}).get("usage") if isinstance(cold_json, dict) else None,
        "usage_warm": (warm_json or {}).get("usage") if isinstance(warm_json, dict) else None,
    }

    print(json.dumps(row, ensure_ascii=False, indent=2))
    try:
        with open(args.jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[warn] failed to append to {args.jsonl}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
    