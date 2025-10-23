#!/usr/bin/env python3
"""
make_prompts.py
Generates 100 benchmark rows with a long shared context for KV/prefix-caching tests.

Output: prompts.txt
Format (pipe-delimited, one row per line):
prompt1|prompt2|topic

- prompt1 ≈ 1000 "tokens" (approx words)
- prompt2 = prompt1 + ~250 more tokens (same topic, follow-up / continuation)
- No '|' characters in any prompt; newlines are collapsed to spaces.
- Deterministic offline mode by default (no API required).
- Optional --openai mode to ask an LLM to draft the base content per topic.
"""

import argparse
import random
import re
import sys
from pathlib import Path
from typing import List, Tuple

# ---------------- Config ----------------
DEFAULT_ROWS = 100
PROMPTS_PATH = Path("prompts.txt")
DELIM = "|"
TARGET_TOKENS_P1 = 1000
TARGET_TOKENS_P2_EXTRA = 250
RNG_SEED = 42  # deterministic

# A pool of diverse topics (100+). Each row uses a unique topic.
TOPIC_SEEDS = [
    "quantitative risk management", "urban mobility planning", "renewable energy storage",
    "low-latency trading infrastructure", "satellite image segmentation", "ocean microplastics",
    "edge computing for retail", "smart grid demand response", "supply chain resilience",
    "gene expression analysis", "privacy-preserving analytics", "real-time fraud detection",
    "autonomous warehouse robotics", "neural search for support", "time-series forecasting",
    "drug discovery pipelines", "disaster early warning", "agritech yield optimization",
    "space weather prediction", "speech emotion recognition", "telemedicine triage systems",
    "cyber threat intelligence", "battery health monitoring", "wind farm layout optimization",
    "financial document parsing", "credit risk explainability", "protein structure insights",
    "personalized education pathways", "climate risk scenarioing", "air quality forecasting",
    "computer vision for safety", "market microstructure analysis", "vector databases in prod",
    "continuous deployment safety", "energy arbitrage modeling", "sports analytics strategy",
    "multilingual retrieval QA", "semantic code search", "observability at scale",
    "incident postmortem analytics", "pricing optimization engines", "quantum-inspired heuristics",
    "material science discovery", "clinical trial matching", "road traffic anomaly detection",
    "recommendation systems fairness", "smart building automation", "portfolio optimization",
    "geospatial route planning", "human-in-the-loop labeling", "document redaction at scale",
    "synthetic data generation", "privacy sandbox measurement", "manufacturing defect detection",
    "customer lifetime value", "green software engineering", "LLM eval harness design",
    "benchmark governance", "data quality observability", "retail demand forecasting",
    "ads budget pacing control", "session-based recommendations", "AB testing guardrails",
    "app performance tuning", "malware classification", "eBPF observability", "SRE capacity planning",
    "data mesh product thinking", "feature store operations", "model registry workflows",
    "multi-armed bandits in prod", "drone delivery routing", "network intrusion detection",
    "smart irrigation systems", "hydrology flood modeling", "audio fingerprinting",
    "contextual bandits ads", "warehouse slotting strategy", "clinical NLP de-identification",
    "topic modeling news", "media content moderation", "pricing elasticity modeling",
    "route ETA prediction", "anomaly detection payments", "supply planning under shocks",
    "loan default prediction", "marketing mix modeling", "energy price forecasting",
    "semantic layer design", "digital twin for factories", "hyperparameter optimization",
    "federated learning pipelines", "graph fraud rings", "churn prediction telco",
    "demand shaping promotions", "carbon accounting data", "workforce scheduling",
    "sports injury risk", "weather nowcasting", "satcom bandwidth allocation",
    "sensor drift detection", "knowledge distillation", "retrieval augmented generation",
    "latency SLO management", "capacity right-sizing", "multi-modal fusion",
    "streaming joins correctness", "feature drift alarms"
]
assert len(TOPIC_SEEDS) >= DEFAULT_ROWS, "Need at least 100 topics in TOPIC_SEEDS."


def sanitize_line(s: str) -> str:
    """Remove/replace characters we don't want in a single-line, pipe-delimited file."""
    s = s.replace(DELIM, " ")            # remove pipe
    s = s.replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_word_bank(topic: str) -> List[str]:
    """Make a deterministic, topic-biased pseudo-corpus without using external APIs."""
    base = re.sub(r"[^a-z0-9 ]+", " ", topic.lower())
    base_words = [w for w in base.split() if w]
    synonyms = [
        "system", "architecture", "throughput", "latency", "scalability", "robustness",
        "workflow", "pipeline", "dataset", "feature", "metric", "baseline", "benchmark",
        "evaluation", "validation", "safety", "privacy", "compliance", "monitoring",
        "governance", "orchestration", "deployment", "capacity", "efficiency",
        "accuracy", "recall", "precision", "tradeoff", "cache", "vector", "index",
        "sharding", "replication", "failover", "queue", "batch", "realtime", "stream",
        "signal", "label", "context", "token", "prefix", "inference", "serving",
        "autoscale", "scheduling", "optimizer", "gradient", "regularization", "ranking",
        "retrieval", "approximate", "hashing", "checkpoint", "drift", "monitor",
        "explainability", "cohort", "segmentation", "embedding", "router", "gateway",
        "loadbalancer", "affinity", "consistency", "isolation", "durability",
    ]
    # Mix topic words and a fixed synonym set repeatedly
    bank = (base_words + synonyms) * 50
    random.shuffle(bank)
    return bank


def synth_paragraph(target_tokens: int, topic: str, mode: str) -> str:
    """
    Deterministic "synthetic" text that hits ~target_tokens words.
    mode: "p1" for the base context, "p2extra" for the continuation.
    """
    bank = build_word_bank(topic)
    rnd = random.Random(hash(topic + "|" + mode) ^ RNG_SEED)

    chunks = []
    word_count = 0
    # Use semi-structured sentences to avoid dull repetition
    while word_count < target_tokens:
        sent_len = rnd.randint(12, 24)
        words = [bank[rnd.randrange(len(bank))] for _ in range(sent_len - 8)]
        # Add some topic words to keep on-theme
        words += [w for w in topic.lower().split()[:4]]
        rnd.shuffle(words)
        sentence = " ".join(words).capitalize() + "."
        chunks.append(sentence)
        word_count += len(sentence.split())

    text = " ".join(chunks)
    return sanitize_line(text)


def make_pair(topic: str) -> Tuple[str, str, str]:
    """
    Returns (prompt1, prompt2, topic)
    - prompt1 ≈ 1000 tokens
    - prompt2 = prompt1 + ≈250 tokens (follow-up / continuation)
    """
    p1 = synth_paragraph(TARGET_TOKENS_P1, topic, "p1")
    p2_extra = synth_paragraph(TARGET_TOKENS_P2_EXTRA, topic, "p2extra")
    p2 = sanitize_line(p1 + " " + p2_extra)
    return p1, p2, sanitize_line(topic)


def write_rows(rows: List[Tuple[str, str, str]], out_path: Path):
    out_path.write_text("", encoding="utf-8")  # truncate
    with out_path.open("a", encoding="utf-8") as f:
        for p1, p2, topic in rows:
            # pipe-delimited: prompt1|prompt2|topic
            line = f"{p1}{DELIM}{p2}{DELIM}{topic}\n"
            f.write(line)


def main():
    parser = argparse.ArgumentParser(description="Generate long prompt pairs for KV/prefix caching benchmarks.")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="number of rows to generate (default 100)")
    parser.add_argument("--outfile", type=str, default=str(PROMPTS_PATH), help="output file (default prompts.txt)")
    parser.add_argument("--openai", action="store_true",
                        help="Use OpenAI to author base text per topic (optional, requires OPENAI_API_KEY).")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="OpenAI model for --openai mode")
    args = parser.parse_args()

    random.seed(RNG_SEED)

    topics = TOPIC_SEEDS[:args.rows]
    rows: List[Tuple[str, str, str]] = []

    if not args.openai:
        # Offline deterministic generation
        for topic in topics:
            p1, p2, t = make_pair(topic)
            rows.append((p1, p2, t))
        write_rows(rows, Path(args.outfile))
        print(f"✅ Wrote {len(rows)} rows to {args.outfile} (pipe-delimited).")
        return

    # ---- Optional OpenAI mode ----
    try:
        from openai import OpenAI
    except Exception as e:
        print("OpenAI SDK not installed. Run: pip install openai", file=sys.stderr)
        sys.exit(1)

    client = OpenAI()  # reads OPENAI_API_KEY
    sys_prompt = (
        "You draft long contextual passages for latency benchmarking.\n"
        "- Produce a single-paragraph base context (~1000 tokens) for the supplied topic.\n"
        "- Then produce a continuation (~250 tokens) that reads like a follow-up in the same context.\n"
        "- Avoid the '|' character entirely. Avoid markdown. Return JSON with keys: base, extra.\n"
    )

    def fetch_from_llm(topic: str) -> Tuple[str, str]:
        user_prompt = f"Topic: {topic}\nReturn JSON only."
        resp = client.chat.completions.create(
            model=args.model,
            temperature=0.6,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2000,
        )
        content = resp.choices[0].message.content
        import json
        obj = json.loads(content)
        base = sanitize_line(obj.get("base", ""))
        extra = sanitize_line(obj.get("extra", ""))
        return base, extra

    for topic in topics:
        try:
            base, extra = fetch_from_llm(topic)
        except Exception:
            # Fallback to offline if API fails
            base = synth_paragraph(TARGET_TOKENS_P1, topic, "p1")
            extra = synth_paragraph(TARGET_TOKENS_P2_EXTRA, topic, "p2extra")
        p1 = sanitize_line(base)
        p2 = sanitize_line(base + " " + extra)
        rows.append((p1, p2, sanitize_line(topic)))

    write_rows(rows, Path(args.outfile))
    print(f"✅ Wrote {len(rows)} rows to {args.outfile} (pipe-delimited, OpenAI-assisted).")


if __name__ == "__main__":
    main()
