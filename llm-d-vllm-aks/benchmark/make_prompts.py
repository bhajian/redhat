#!/usr/bin/env python3
"""
make_prompts.py
Generates N benchmark rows with a long shared context for KV/prefix-caching tests.

Output: prompts.txt
Format (pipe-delimited, one row per line):
prompt1|prompt2|topic

- prompt1 ≈ 1000 tokens (approx words)
- prompt2 = prompt1 + ~200 more tokens (same topic, explicit follow-up that references the first part)
- No '|' characters in any prompt; newlines are collapsed to spaces.
- Deterministic offline mode by default (no API required).
- Optional --openai mode to ask an LLM to draft the base content per topic (adds a *relevant* follow-up).
- Optional --validate to check an existing prompts file.

Usage:
  python3 make_prompts.py --rows 100
  python3 make_prompts.py --rows 100 --openai --model gpt-4o-mini
  python3 make_prompts.py --validate --outfile prompts.txt
"""

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import List, Tuple

# ---------------- Config ----------------
DEFAULT_ROWS = 100
PROMPTS_PATH = Path("prompts.txt")
DELIM = "|"
TARGET_TOKENS_P1 = 1000
TARGET_TOKENS_P2_EXTRA = 200
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


# ---------------- Utilities ----------------

STOPWORDS = set("""
a an the and or but if then else for of on in into to from with without over under above below
is are was were be being been can could should would may might will shall do does did done doing
this that these those it its their his her your my our as by at not no nor so very just than
more most less least many much few such per via about around between across up down out any each
""".split())

def sanitize_line(s: str) -> str:
    """Remove/replace characters we don't want in a single-line, pipe-delimited file."""
    s = s.replace(DELIM, " ")            # remove pipe
    s = s.replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def token_len(s: str) -> int:
    return 0 if not s else len(s.split())

def take_top_keywords(text: str, topic: str, k: int = 12) -> List[str]:
    words = [w.lower() for w in re.findall(r"[a-z0-9\-]+", text)]
    words += [w.lower() for w in re.findall(r"[a-z0-9\-]+", topic)]
    words = [w for w in words if w not in STOPWORDS and len(w) > 2]
    freq = Counter(words)
    return [w for w, _ in freq.most_common(k)]

def clamp_to_target(text: str, target_tokens: int) -> str:
    words = text.split()
    if len(words) <= target_tokens:
        return text
    return " ".join(words[:target_tokens])

# ---------------- Offline text synthesis (improved structure) ----------------

def build_word_bank(topic: str) -> List[str]:
    """Make a deterministic, topic-biased pseudo-corpus without external APIs."""
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
        "autoscale", "scheduling", "optimizer", "regularization", "ranking",
        "retrieval", "approximate", "hashing", "checkpoint", "drift", "monitor",
        "explainability", "cohort", "segmentation", "embedding", "router", "gateway",
        "loadbalancer", "affinity", "consistency", "isolation", "durability",
        "observability", "profiling", "telemetry", "slo", "sla", "backpressure",
        "throughput", "failover", "canary", "bluegreen", "rollout", "rollback"
    ]
    bank = (base_words + synonyms) * 50
    random.shuffle(bank)
    return bank

def synth_sentence(rnd: random.Random, bank: List[str], topic: str, min_len=14, max_len=26) -> str:
    sent_len = rnd.randint(min_len, max_len)
    words = [bank[rnd.randrange(len(bank))] for _ in range(max(4, sent_len - 8))]
    # Add some topic words to keep on-theme
    words += [w for w in topic.lower().split()[:4]]
    rnd.shuffle(words)
    return (" ".join(words)).capitalize() + "."

def synth_section(rnd: random.Random, bank: List[str], topic: str, header: str, sentences: int) -> str:
    parts = [f"{header}:"]  # simple inline markers; kept in-line (no newlines)
    for _ in range(sentences):
        parts.append(synth_sentence(rnd, bank, topic))
    return " ".join(parts)

def synth_base_context(target_tokens: int, topic: str) -> str:
    """
    More structured ~1000-token passage with soft sections to improve coherence.
    """
    bank = build_word_bank(topic)
    rnd = random.Random(hash(topic + "|base") ^ RNG_SEED)
    sections = [
        ("Overview", 5),
        ("Constraints", 4),
        ("Architecture", 6),
        ("Metrics", 4),
        ("Failure modes", 4),
        ("Mitigations", 4),
        ("Examples", 4),
    ]
    chunks = []
    word_count = 0
    i = 0
    while word_count < target_tokens:
        header, sents = sections[i % len(sections)]
        para = synth_section(rnd, bank, topic, header, sents)
        chunks.append(para)
        word_count += token_len(para)
        i += 1
    text = " ".join(chunks)
    return sanitize_line(text)

def synth_followup_extra(base_text: str, topic: str, target_tokens: int) -> str:
    """
    Generate a ~200-token follow-up that *explicitly* refers to the preceding passage.
    We craft a short interrogative/task block referencing salient keywords.
    """
    rnd = random.Random(hash(topic + "|extra") ^ RNG_SEED)
    kws = take_top_keywords(base_text, topic, k=12)
    # Build a compact set of questions + a small task prompt
    prompts = [
        "Given the passage above, answer the following concisely and only using prior context.",
        f"1) Which bottleneck most affects latency under peak load and why might {kws[0] if kws else 'caching'} be insufficient?",
        f"2) How do {kws[1] if len(kws)>1 else 'throughput'} and {kws[2] if len(kws)>2 else 'tail-latency'} trade off in this design?",
        f"3) Identify two failure modes related to {kws[3] if len(kws)>3 else 'replication'} and {kws[4] if len(kws)>4 else 'sharding'}, and propose mitigations.",
        f"4) Which metrics best verify success of the mitigations (consider {kws[5] if len(kws)>5 else 'SLOs'} and observability hooks)?",
        f"5) Outline a stepwise rollout and rollback plan for the proposed change to {kws[6] if len(kws)>6 else 'the gateway'}."
    ]
    # Add a tiny "do this now" instruction to force relevant continuation.
    prompts.append("Then produce a 3-bullet action plan referencing concrete entities from the passage.")
    text = " ".join(prompts)
    text = clamp_to_target(text, target_tokens)
    return sanitize_line(text)

# ---------------- Row construction ----------------

def make_pair(topic: str) -> Tuple[str, str, str]:
    """
    Returns (prompt1, prompt2, topic)
    - prompt1 ≈ 1000 tokens
    - prompt2 = prompt1 + ≈200 tokens (explicit follow-up)
    """
    p1 = synth_base_context(TARGET_TOKENS_P1, topic)
    extra = synth_followup_extra(p1, topic, TARGET_TOKENS_P2_EXTRA)
    p2 = sanitize_line(p1 + " " + extra)
    return p1, p2, sanitize_line(topic)

def write_rows(rows: List[Tuple[str, str, str]], out_path: Path):
    out_path.write_text("", encoding="utf-8")  # truncate
    with out_path.open("a", encoding="utf-8") as f:
        for p1, p2, topic in rows:
            # pipe-delimited: prompt1|prompt2|topic
            line = f"{p1}{DELIM}{p2}{DELIM}{topic}\n"
            f.write(line)

# ---------------- Validation ----------------

def validate_file(path: Path) -> int:
    """
    Basic checks for an existing prompts.txt:
      - No pipes inside fields (only 2 delimiters per line).
      - prompt2 starts with prompt1 (prefix property).
      - token counts near their targets.
    Returns number of issues found.
    """
    issues = 0
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        parts = line.split(DELIM)
        if len(parts) != 3:
            print(f"[L{i}] wrong number of fields: {len(parts)}")
            issues += 1
            continue
        p1, p2, topic = parts
        # 1) Ensure p2 has p1 as prefix
        if not p2.startswith(p1 + " "):
            print(f"[L{i}] prompt2 is not prefix-extended from prompt1")
            issues += 1
        # 2) Check approximate lengths
        n1, n2 = token_len(p1), token_len(p2) - token_len(p1)
        if abs(n1 - TARGET_TOKENS_P1) > 150:
            print(f"[L{i}] prompt1 token count off: got {n1}")
            issues += 1
        if abs(n2 - TARGET_TOKENS_P2_EXTRA) > 80:
            print(f"[L{i}] extra token count off: got {n2}")
            issues += 1
        # 3) Check stray pipes inside fields (shouldn't happen after sanitize)
        if (DELIM in p1) or (DELIM in p2) or (DELIM in topic):
            print(f"[L{i}] stray delimiter detected in fields")
            issues += 1
    print(f"Validation complete. Issues found: {issues}")
    return issues

# ---------------- Main ----------------

def main():
    parser = argparse.ArgumentParser(description="Generate long prompt pairs for KV/prefix caching benchmarks.")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="number of rows to generate (default 100)")
    parser.add_argument("--outfile", type=str, default=str(PROMPTS_PATH), help="output file (default prompts.txt)")
    parser.add_argument("--openai", action="store_true",
                        help="Use OpenAI to author base text per topic (optional, requires OPENAI_API_KEY).")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="OpenAI model for --openai mode")
    parser.add_argument("--validate", action="store_true", help="Validate an existing prompts file and exit")
    args = parser.parse_args()

    if args.validate:
        path = Path(args.outfile)
        if not path.exists():
            print(f"No file at {path}")
            sys.exit(2)
        issues = validate_file(path)
        sys.exit(0 if issues == 0 else 3)

    random.seed(RNG_SEED)

    topics = TOPIC_SEEDS[:args.rows]
    rows: List[Tuple[str, str, str]] = []

    # ---- Offline deterministic generation (default) ----
    if not args.openai:
        for topic in topics:
            p1, p2, t = make_pair(topic)
            rows.append((p1, p2, t))
        write_rows(rows, Path(args.outfile))
        print(f"✅ Wrote {len(rows)} rows to {args.outfile} (pipe-delimited, offline).")
        return

    # ---- Optional OpenAI mode (adds coherent base + targeted follow-up) ----
    try:
        from openai import OpenAI
    except Exception as e:
        print("OpenAI SDK not installed. Run: pip install openai", file=sys.stderr)
        sys.exit(1)

    client = OpenAI()  # reads OPENAI_API_KEY
    sys_prompt = (
        "You draft long contextual passages for latency benchmarking.\n"
        "- Produce a single-paragraph base context (~1000 tokens) for the supplied topic.\n"
        "- Then produce a follow-up (~200 tokens) that explicitly references the base and asks probing questions/tasks.\n"
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
            max_tokens=2200,
        )
        content = resp.choices[0].message.content
        obj = json.loads(content)
        base = sanitize_line(obj.get("base", ""))
        extra = sanitize_line(obj.get("extra", ""))
        # Clamp lengths if the model overshoots/undershoots
        if token_len(base) < TARGET_TOKENS_P1:
            # pad with offline to hit target deterministically
            pad = synth_base_context(TARGET_TOKENS_P1 - token_len(base), topic)
            base = sanitize_line((base + " " + pad).strip())
        extra = clamp_to_target(extra, TARGET_TOKENS_P2_EXTRA)
        return base, extra

    for topic in topics:
        try:
            base, extra = fetch_from_llm(topic)
        except Exception:
            # Fallback to offline if API fails
            base = synth_base_context(TARGET_TOKENS_P1, topic)
            extra = synth_followup_extra(base, topic, TARGET_TOKENS_P2_EXTRA)
        p1 = sanitize_line(base)
        p2 = sanitize_line(base + " " + extra)
        rows.append((p1, p2, sanitize_line(topic)))

    write_rows(rows, Path(args.outfile))
    print(f"✅ Wrote {len(rows)} rows to {args.outfile} (pipe-delimited, OpenAI-assisted).")


if __name__ == "__main__":
    main()
