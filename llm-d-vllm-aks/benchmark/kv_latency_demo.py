#!/usr/bin/env python3
import argparse, json, sys, time, csv, typing as t
import requests

def pick_endpoint(mode: str, lb_url: str | None, gw_url: str | None) -> str:
    if mode == "lb":
        if not lb_url:
            raise SystemExit("--lb-url is required when mode=lb")
        return lb_url.rstrip("/")
    if mode == "gw":
        if not gw_url:
            raise SystemExit("--gw-url is required when mode=gw")
        return gw_url.rstrip("/")
    raise SystemExit("mode must be one of: lb, gw")

def read_pair(path: str, index: int) -> tuple[str, str, str | None]:
    # CSV with 2 or 3 cols: prompt1,prompt2[,topic]
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        for i, row in enumerate(r):
            if i == index:
                if len(row) < 2:
                    raise SystemExit(f"Line {index} malformed (needs at least two columns).")
                p1, p2 = row[0].strip(), row[1].strip()
                topic = row[2].strip() if len(row) >= 3 else None
                return p1, p2, topic
    raise SystemExit(f"Index {index} out of range for {path}")

def build_prompt(base_prefix: str | None, body: str) -> str:
    if base_prefix:
        return base_prefix.rstrip() + "\n\n" + body.lstrip()
    return body

def _do_request(url: str, payload: dict, headers: dict, timeout: float, stream: bool):
    if stream:
        return requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout, stream=True)
    return requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)

def call_chat(
    url_base: str,
    model: str,
    prompt: str,
    api_key: str | None,
    timeout: float,
    stream: bool,
    extra_headers: dict | None = None,
    lb_mode: bool = False,
) -> tuple[float, float, dict, dict]:
    """
    Returns: (fftp_seconds, full_seconds, response_json_if_any, resp_headers)
    In non-stream mode, fftp_seconds == full_seconds.
    """
    url = f"{url_base}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 128,
        "temperature": 0.2,
        "top_p": 0.9,
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "stream": bool(stream),
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}

    headers = {
        "Content-Type": "application/json",
    }
    # Avoid accidental stickiness in LB mode
    if lb_mode:
        headers["Connection"] = "close"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra_headers:
        headers.update(extra_headers)

    t0 = time.perf_counter()
    if not stream:
        r = _do_request(url, payload, headers, timeout, stream=False)
        t1 = time.perf_counter()
        j = {}
        try:
            if r.headers.get("content-type", "").startswith("application/json"):
                j = r.json()
            else:
                j = {"status": r.status_code, "text": r.text}
        except Exception:
            j = {"status": r.status_code, "text": "<non-json>"}
        return (t1 - t0), (t1 - t0), j, dict(r.headers)

    # streaming
    r = _do_request(url, payload, headers, timeout, stream=True)
    fftp = None
    last_json = {}
    for chunk in r.iter_lines(decode_unicode=True):
        if not chunk:
            continue
        if chunk.startswith("data:"):
            data = chunk[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
                last_json = obj
            except Exception:
                # ignore malformed lines
                continue
            if fftp is None:
                fftp = time.perf_counter() - t0
    t1 = time.perf_counter()
    if fftp is None:
        fftp = t1 - t0
    return fftp, (t1 - t0), last_json, dict(r.headers)

def main():
    ap = argparse.ArgumentParser(description="KV/prefix cache latency demo for vLLM (LB vs Gateway)")
    ap.add_argument("--file", default="prompts.txt", help="CSV file (prompt1,prompt2[,topic])")
    ap.add_argument("--index", type=int, required=True, help="0-based pair index to test")
    ap.add_argument("--mode", choices=["lb","gw"], required=True, help="Target: lb (Service) or gw (Gateway)")
    ap.add_argument("--lb-url", default=None, help="Base URL for LoadBalancer, e.g. http://1.2.3.4")
    ap.add_argument("--gw-url", default=None, help="Base URL for Gateway, e.g. http://1.2.3.4")
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B", help="Model name exposed by vLLM")
    ap.add_argument("--api-key", default=None, help="Bearer token if your endpoint requires it")
    ap.add_argument("--timeout", type=float, default=90.0, help="HTTP timeout seconds")
    ap.add_argument("--warmup", type=int, default=0, help="Number of warm-up requests before timing")
    ap.add_argument("--stream", action="store_true", help="Use streaming to capture FFTP")
    ap.add_argument("--shared-prefix-file", default=None, help="File whose contents prepend BOTH prompts (to enable prefix reuse)")
    ap.add_argument("--affinity-key", default=None, help="Value for X-Affinity-Key (used by GW hashing to keep pair on same pod)")
    ap.add_argument("--jsonl", default="results.jsonl", help="Append results to this JSONL file")
    args = ap.parse_args()

    base = pick_endpoint(args.mode, args.lb_url, args.gw_url)
    p1, p2, topic = read_pair(args.file, args.index)

    shared_prefix = None
    if args.shared_prefix_file:
        with open(args.shared_prefix_file, "r", encoding="utf-8") as f:
            shared_prefix = f.read()

    # Compose prompts (with shared prefix if provided)
    prompt_cold = build_prompt(shared_prefix, p1)
    prompt_warm = build_prompt(shared_prefix, p2)

    # Headers specific to Gateway stickiness
    extra_headers = {}
    if args.mode == "gw" and args.affinity_key:
        extra_headers["X-Affinity-Key"] = args.affinity_key

    # Optional warm-ups (not recorded)
    for _ in range(max(0, args.warmup)):
        try:
            call_chat(base, args.model, "warm up", args.api_key, args.timeout, stream=False,
                      extra_headers=extra_headers, lb_mode=(args.mode == "lb"))
        except Exception as e:
            print(f"[warmup] {e}", file=sys.stderr)

    # 1) Cold
    cold_fftp_s, cold_full_s, cold_json, cold_hdrs = call_chat(
        base, args.model, prompt_cold, args.api_key, args.timeout, stream=args.stream,
        extra_headers=extra_headers, lb_mode=(args.mode == "lb")
    )

    # 2) Warm (related)
    warm_fftp_s, warm_full_s, warm_json, warm_hdrs = call_chat(
        base, args.model, prompt_warm, args.api_key, args.timeout, stream=args.stream,
        extra_headers=extra_headers, lb_mode=(args.mode == "lb")
    )

    # Extract upstream IDs if your VirtualService adds X-Upstream-Host
    up_cold = cold_hdrs.get("X-Upstream-Host") or cold_hdrs.get("x-upstream-host")
    up_warm = warm_hdrs.get("X-Upstream-Host") or warm_hdrs.get("x-upstream-host")

    # Usage if available (non-stream in vLLM returns usage; in stream it's in the last chunk if include_usage)
    usage_cold = cold_json.get("usage") if isinstance(cold_json, dict) else None
    usage_warm = warm_json.get("usage") if isinstance(warm_json, dict) else None

    row = {
        "target": args.mode,
        "base_url": base,
        "index": args.index,
        "topic": topic,
        "model": args.model,
        "shared_prefix": bool(shared_prefix),
        "affinity_key": args.affinity_key if args.mode == "gw" else None,
        "cold_upstream": up_cold,
        "warm_upstream": up_warm,
        "cold_fftp_ms": round(cold_fftp_s * 1000, 2),
        "cold_full_ms": round(cold_full_s * 1000, 2),
        "warm_fftp_ms": round(warm_fftp_s * 1000, 2),
        "warm_full_ms": round(warm_full_s * 1000, 2),
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
