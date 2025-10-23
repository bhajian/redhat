#!/usr/bin/env python3
import argparse, json, sys, time
import requests

def pick_endpoint(mode: str, lb_url: str, gw_url: str) -> str:
    if mode == "lb":
        if not lb_url:
            raise SystemExit("--lb-url is required when mode=lb")
        return lb_url.rstrip("/")
    elif mode == "gw":
        if not gw_url:
            raise SystemExit("--gw-url is required when mode=gw")
        return gw_url.rstrip("/")
    else:
        raise SystemExit("mode must be one of: lb, gw")

def read_line(path: str, index: int) -> tuple[str, str]:
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == index:
                parts = line.strip().split(",", 1)
                if len(parts) != 2:
                    raise SystemExit(f"Line {index} is malformed (needs exactly one comma).")
                return parts[0].strip(), parts[1].strip()
    raise SystemExit(f"Index {index} out of range.")

def post_chat(url_base: str, model: str, prompt: str, api_key: str | None, timeout: float) -> tuple[float, dict]:
    url = f"{url_base}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 64,
        "stream": False,
        "temperature": 0.2,
        "top_p": 0.9,
        "presence_penalty": 0,
        "frequency_penalty": 0
    }
    headers = {
        "Content-Type": "application/json",
        # Kill connection pooling so LB selection isn’t sticky
        "Connection": "close",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    t0 = time.perf_counter()
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
    t1 = time.perf_counter()
    return (t1 - t0), r.json() if r.headers.get("content-type","").startswith("application/json") else {"status": r.status_code, "text": r.text}

def main():
    ap = argparse.ArgumentParser(description="KV-cache latency demo for vLLM (LB vs Gateway)")
    ap.add_argument("--file", default="prompts.txt", help="Path to prompts file (one line: prompt1,prompt2)")
    ap.add_argument("--index", type=int, required=True, help="0-based line index to test")
    ap.add_argument("--mode", choices=["lb","gw"], required=True, help="Target: lb (Service) or gw (Inference Gateway)")
    ap.add_argument("--lb-url", default=None, help="Base URL for LoadBalancer, e.g. http://4.156.35.174")
    ap.add_argument("--gw-url", default=None, help="Base URL for Gateway, e.g. http://128.203.121.47")
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B", help="Model name exposed by vLLM")
    ap.add_argument("--api-key", default=None, help="Optional Bearer token if your endpoint requires it")
    ap.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout seconds")
    ap.add_argument("--warmup", action="store_true", help="Send one warm-up request that is ignored")
    args = ap.parse_args()

    base = pick_endpoint(args.mode, args.lb_url, args.gw_url)
    p1, p2 = read_line(args.file, args.index)

    # Optional warm-up hit to avoid first-request compile overhead
    if args.warmup:
        try:
            _ = post_chat(base, args.model, "warm up", args.api_key, args.timeout)
        except Exception as e:
            print(f"[warmup] failed: {e}", file=sys.stderr)

    # 1) Cold prompt
    t_cold, _ = post_chat(base, args.model, p1, args.api_key, args.timeout)

    # 2) Related prompt (should reuse KV on the same pod if gateway routes by key)
    t_warm, _ = post_chat(base, args.model, p2, args_api_key := args.api_key, timeout := args.timeout)

    # Output
    print(json.dumps({
        "target": args.mode,
        "base_url": base,
        "index": args.index,
        "prompt1": p1,
        "prompt2": p2,
        "latency_cold_ms": round(t_cold*1000, 2),
        "latency_warm_ms": round(t_warm*1000, 2),
        "delta_ms": round((t_warm - t_cold)*1000, 2)
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
