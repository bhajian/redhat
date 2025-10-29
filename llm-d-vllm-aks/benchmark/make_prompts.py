#!/usr/bin/env python3
"""
make_prompts.py
Generates N benchmark rows with a long shared context for KV/prefix-caching tests.

Output: prompts.txt
Format (pipe-delimited, one row per line):
prompt1|prompt2|topic

- prompt1 ≈ 2000 tokens (approx words)
- prompt2 = prompt1 + ~200 more tokens (same topic, explicit follow-up that references the first part)
- No '|' characters in any prompt; newlines are collapsed to spaces.
- Deterministic offline mode by default (no API required).
- Optional --openai mode to ask an LLM to draft the base content per topic (adds a *relevant* follow-up).
- Optional --validate to check an existing prompts file.

Language behavior:
- By default, rows cycle through English, Spanish, French (en→es→fr), producing separate-language prompts per row.
- No mixing of languages inside a single row.

Usage:
  python3 make_prompts.py --rows 1000
  python3 make_prompts.py --rows 1000 --languages en,es,fr
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
DEFAULT_ROWS = 1000
PROMPTS_PATH = Path("prompts.txt")
DELIM = "|"
TARGET_TOKENS_P1 = 2000
TARGET_TOKENS_P2_EXTRA = 200
RNG_SEED = 42  # deterministic

# A pool of diverse topics (>= 350; we will cycle if rows exceed this list)
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
    "streaming joins correctness", "feature drift alarms",
    # extra variety for 1000 rows (tech + domain)
    "zero-trust network design", "homomorphic encryption use cases", "privacy-preserving telemetry",
    "GPU scheduling for inference", "vector quantization tradeoffs", "model distillation at scale",
    "fuzz testing for APIs", "chaos engineering playbooks", "event-driven backpressure control",
    "autoscaling with predictive signals", "reservoir sampling for logs", "sketching algorithms in ops",
    "LLM safety policies", "prompt injection defenses", "rate limiting fairness",
    "finite-state controllers", "linguistic feature extraction", "cross-lingual embeddings",
    "offline RL for pricing", "context windows and caching", "prefix compression strategies",
    "semantic chunking heuristics", "document layout parsing", "table extraction pipelines",
    "OCR post-correction", "speech diarization", "keyword spotting on-device",
    "SLO error budgets", "multi-region failover", "data residency controls",
    "PII tokenization vaults", "governed feature stores", "retraining triggers",
    "canary analysis statistics", "shadow traffic validation", "synthetic monitoring",
    "distributed tracing joins", "bitemporal data modeling", "late-arriving data handling",
    "backfills and replays", "sequence anomaly detection", "volatility regime shifts",
    "cointegration signals", "order book simulation", "latency arbitrage protection",
    "slippage estimation", "portfolio factor decomposition", "risk parity tuning",
    "explainable gradient boosting", "counterfactual explanations", "adversarial robustness tests",
    "SFT vs DPO comparisons", "reward modeling pitfalls", "online A/B sequential tests",
    "interleaving methods for ranking", "graph neural anomalies", "entity resolution at scale",
    "geohash-based indexing", "raster to vector conversion", "change detection SAR",
    "cloud cost anomaly detection", "GreenOps KPIs", "carbon-aware scheduling",
    "edge-to-cloud synchronization", "schema evolution contracts"
]

# ---------------- Utilities ----------------

STOPWORDS = set("""
a an the and or but if then else for of on in into to from with without over under above below
is are was were be being been can could should would may might will shall do does did done doing
this that these those it its their his her your my our as by at not no nor so very just than
more most less least many much few such per via about around between across up down out any each
""".split())

STOPWORDS_ES = set("""
un una unos unas el la los las y o pero si entonces sino para de del con sin sobre bajo entre
es son fue fueron ser estar siendo sido puede podrían debería deberíamos podrá deberá harán hará
esto eso estos esas aquello aquellas su sus tu tus mi mis nuestro nuestros vuestra vuestras como
por en al desde hasta muy más menos tanto tan mucho mucha muchos muchas cada
""".split())

STOPWORDS_FR = set("""
un une des le la les et ou mais si alors sinon pour de du des avec sans sur sous entre
est sont était étaient être étant été peut pourraient devrait devrions pourra devra feront fera
ce cela ces celles celui leur leurs ton ta tes mon mes notre nos votre vos comme par en au aux
depuis jusqu très plus moins autant tant beaucoup chacune chacun
""".split())

def sanitize_line(s: str) -> str:
    """Remove/replace characters we don't want in a single-line, pipe-delimited file."""
    s = s.replace(DELIM, " ")            # remove pipe
    s = s.replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def token_len(s: str) -> int:
    return 0 if not s else len(s.split())

def clamp_to_target(text: str, target_tokens: int) -> str:
    words = text.split()
    if len(words) <= target_tokens:
        return text
    return " ".join(words[:target_tokens])

# ---------------- Multilingual banks ----------------

EN_BANK = [
    "system","architecture","throughput","latency","scalability","robustness","workflow","pipeline","dataset",
    "feature","metric","baseline","benchmark","evaluation","validation","safety","privacy","compliance",
    "monitoring","governance","orchestration","deployment","capacity","efficiency","accuracy","recall",
    "precision","tradeoff","cache","vector","index","sharding","replication","failover","queue","batch",
    "realtime","stream","signal","label","context","token","prefix","inference","serving","autoscale",
    "scheduling","optimizer","regularization","ranking","retrieval","approximate","hashing","checkpoint",
    "drift","monitor","observability","profiling","telemetry","slo","sla","backpressure","canary","rollout",
    "rollback","circuitbreaker","idempotency","deduplication","rate-limiting","fairness","interpretability",
    "trace","span","histogram","quantile","percentile","p50","p95","p99","tail-latency","cold-start"
]

ES_BANK = [
    "sistema","arquitectura","rendimiento","latencia","escalabilidad","robustez","flujo","tubería","conjunto",
    "característica","métrica","línea-base","evaluación","validación","seguridad","privacidad","cumplimiento",
    "monitoreo","gobernanza","orquestación","despliegue","capacidad","eficiencia","precisión","recuperación",
    "equilibrio","caché","vector","índice","fragmentación","replicación","tolerancia","cola","lote","tiempo-real",
    "flujo-continuo","señal","etiqueta","contexto","token","prefijo","inferencia","servicio","autoescala",
    "planificación","optimizador","regularización","clasificación","recuperación","aproximado","hash","punto-control",
    "deriva","observabilidad","telemetría","acuerdo-nivel-servicio","presión-retorno","canario","despliegue-progresivo",
    "reversión","cortacircuitos","idempotencia","deduplicación","limitación-tasa","equidad","interpretabilidad",
    "traza","segmento","histograma","cuantil","percentil","cola-latencia","arranque-en-frío"
]

FR_BANK = [
    "système","architecture","débit","latence","scalabilité","robustesse","flux","pipeline","ensemble",
    "caractéristique","métrique","référence","évaluation","validation","sécurité","confidentialité","conformité",
    "surveillance","gouvernance","orchestration","déploiement","capacité","efficacité","précision","rappel",
    "équilibre","cache","vecteur","index","partitionnement","réplication","basculement","file","lot","temps-réel",
    "diffusion","signal","étiquette","contexte","jeton","préfixe","inférence","service","auto-échelle",
    "ordonnancement","optimiseur","régularisation","classement","recherche","approximatif","hachage","point-de-contrôle",
    "dérive","observabilité","télémétrie","engagement-de-service","contre-pression","canari","déploiement-progressif",
    "retour-arrière","coupe-circuit","idempotence","déduplication","limitation-de-débit","équité","interprétabilité",
    "trace","span","histogramme","quantile","percentile","latence-de-queue","démarrage-à-froid"
]

# Section headers per language
SECTIONS = {
    "en": [("Overview",5),("Constraints",4),("Architecture",6),("Metrics",4),("Failure modes",4),("Mitigations",4),("Examples",4)],
    "es": [("Resumen",5),("Restricciones",4),("Arquitectura",6),("Métricas",4),("Modos de falla",4),("Mitigaciones",4),("Ejemplos",4)],
    "fr": [("Aperçu",5),("Contraintes",4),("Architecture",6),("Métriques",4),("Modes de défaillance",4),("Atténuations",4),("Exemples",4)],
}

# Follow-up templates per language (kept short; we clamp to 200 tokens)
FOLLOWUP_TPL = {
    "en": [
        "Given the passage above, answer strictly using prior context.",
        "1) Identify the dominant bottleneck for latency under peak load and explain why basic caching might be insufficient.",
        "2) Describe the tradeoff between throughput and tail-latency in this design.",
        "3) Name two failure modes related to replication and sharding and propose mitigations.",
        "4) Which metrics best verify success (consider SLOs and observability hooks)?",
        "5) Sketch a safe rollout and rollback plan for the proposed change.",
        "Finally, add a three-bullet action plan referencing concrete entities from the passage."
    ],
    "es": [
        "Usando únicamente el contexto anterior, responde con precisión.",
        "1) Señala el cuello de botella dominante de latencia bajo carga pico y por qué la caché básica puede no bastar.",
        "2) Describe el equilibrio entre rendimiento y latencia de cola en este diseño.",
        "3) Indica dos modos de falla relacionados con la replicación y el fragmentado y propone mitigaciones.",
        "4) ¿Qué métricas verifican el éxito (considera SLOs y ganchos de observabilidad)?",
        "5) Esboza un plan de despliegue progresivo y reversión seguro para el cambio propuesto.",
        "Finalmente, agrega un plan de acción de tres viñetas con referencias concretas del pasaje."
    ],
    "fr": [
        "En t'appuyant uniquement sur le texte précédent, réponds de manière concise.",
        "1) Identifie le goulot d'étranglement dominant de latence en charge de pointe et pourquoi un cache simple peut être insuffisant.",
        "2) Décris le compromis entre débit et latence de queue dans cette architecture.",
        "3) Donne deux modes de défaillance liés à la réplication et au partitionnement, avec des atténuations.",
        "4) Quelles métriques valident la réussite (considère les SLO et les points d'observabilité) ?",
        "5) Esquisse un plan de déploiement progressif et de retour arrière sécurisé pour le changement proposé.",
        "Enfin, ajoute un plan d'action en trois puces en citant des éléments concrets du passage."
    ],
}

def take_top_keywords(text: str, topic: str, k: int, lang: str) -> List[str]:
    # language-aware stopwords
    sw = STOPWORDS if lang == "en" else (STOPWORDS_ES if lang == "es" else STOPWORDS_FR)
    words = [w.lower() for w in re.findall(r"[a-zàâäçéèêëîïôöùûüñ0-9\-]+", text)]
    words += [w.lower() for w in re.findall(r"[a-zàâäçéèêëîïôöùûüñ0-9\-]+", topic)]
    words = [w for w in words if w not in sw and len(w) > 2]
    freq = Counter(words)
    return [w for w, _ in freq.most_common(k)]

# ---------------- Offline synthesis ----------------

def build_word_bank(topic: str, lang: str) -> List[str]:
    """Deterministic, topic-biased multilingual corpus."""
    base = re.sub(r"[^a-zàâäçéèêëîïôöùûüñ0-9 ]+", " ", topic.lower())
    base_words = [w for w in base.split() if w]
    if lang == "en":
        synonyms = EN_BANK
    elif lang == "es":
        synonyms = ES_BANK
    else:
        synonyms = FR_BANK
    # Multiply to inflate vocabulary and shuffle deterministically
    bank = (base_words + synonyms) * 80
    rnd = random.Random(hash(topic + "|" + lang + "|bank") ^ RNG_SEED)
    rnd.shuffle(bank)
    return bank

def synth_sentence(rnd: random.Random, bank: List[str], topic: str, lang: str, min_len=16, max_len=28) -> str:
    sent_len = rnd.randint(min_len, max_len)
    core = [bank[rnd.randrange(len(bank))] for _ in range(max(6, sent_len - 10))]
    core += [w for w in topic.lower().split()[:4]]
    rnd.shuffle(core)
    # Simple capitalization without changing non-ASCII letters
    s = " ".join(core)
    if s:
        s = s[0].upper() + s[1:]
    return s + "."

def synth_section(rnd: random.Random, bank: List[str], topic: str, lang: str, header: str, sentences: int) -> str:
    parts = [f"{header}:"]  # inline header (no newlines)
    for _ in range(sentences):
        parts.append(synth_sentence(rnd, bank, topic, lang))
    return " ".join(parts)

def synth_base_context(target_tokens: int, topic: str, lang: str) -> str:
    """
    Structured ~2000-token passage with soft sections to improve coherence.
    """
    bank = build_word_bank(topic, lang)
    rnd = random.Random(hash(topic + "|" + lang + "|base") ^ RNG_SEED)
    sections = SECTIONS[lang]
    chunks = []
    word_count = 0
    i = 0
    while word_count < target_tokens:
        header, sents = sections[i % len(sections)]
        para = synth_section(rnd, bank, topic, lang, header, sents)
        chunks.append(para)
        word_count += token_len(para)
        i += 1
    text = " ".join(chunks)
    return sanitize_line(text)

def synth_followup_extra(base_text: str, topic: str, target_tokens: int, lang: str) -> str:
    """
    Generate a ~200-token follow-up that explicitly refers to the preceding passage, in the same language.
    """
    rnd = random.Random(hash(topic + "|" + lang + "|extra") ^ RNG_SEED)
    _ = take_top_keywords(base_text, topic, k=12, lang=lang)  # we keep for potential future personalization
    prompts = FOLLOWUP_TPL[lang]
    # Slight shuffle for variety, but keep first instruction first
    inst = prompts[0]
    rest = prompts[1:].copy()
    rnd.shuffle(rest)
    text = " ".join([inst] + rest)
    text = clamp_to_target(text, target_tokens)
    return sanitize_line(text)

# ---------------- Row construction ----------------

def make_pair(topic: str, lang: str) -> Tuple[str, str, str]:
    """
    Returns (prompt1, prompt2, topic_label)
    - prompt1 ≈ 2000 tokens
    - prompt2 = prompt1 + ≈200 tokens (explicit follow-up)
    """
    p1 = synth_base_context(TARGET_TOKENS_P1, topic, lang)
    extra = synth_followup_extra(p1, topic, TARGET_TOKENS_P2_EXTRA, lang)
    p2 = sanitize_line(p1 + " " + extra)
    topic_label = sanitize_line(f"{topic} [{lang}]")
    return p1, p2, topic_label

def write_rows(rows: List[Tuple[str, str, str]], out_path: Path):
    out_path.write_text("", encoding="utf-8")  # truncate
    with out_path.open("a", encoding="utf-8") as f:
        for p1, p2, topic in rows:
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
        if not p2.startswith(p1 + " "):
            print(f"[L{i}] prompt2 is not prefix-extended from prompt1")
            issues += 1
        n1, n2 = token_len(p1), token_len(p2) - token_len(p1)
        if abs(n1 - TARGET_TOKENS_P1) > 220:
            print(f"[L{i}] prompt1 token count off: got {n1}")
            issues += 1
        if abs(n2 - TARGET_TOKENS_P2_EXTRA) > 90:
            print(f"[L{i}] extra token count off: got {n2}")
            issues += 1
        if (DELIM in p1) or (DELIM in p2) or (DELIM in topic):
            print(f"[L{i}] stray delimiter detected in fields")
            issues += 1
    print(f"Validation complete. Issues found: {issues}")
    return issues

# ---------------- Main ----------------

def main():
    parser = argparse.ArgumentParser(description="Generate long prompt pairs for KV/prefix caching benchmarks.")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help=f"number of rows to generate (default {DEFAULT_ROWS})")
    parser.add_argument("--outfile", type=str, default=str(PROMPTS_PATH), help="output file (default prompts.txt)")
    parser.add_argument("--openai", action="store_true",
                        help="Use OpenAI to author base text per topic (optional, requires OPENAI_API_KEY).")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="OpenAI model for --openai mode")
    parser.add_argument("--languages", type=str, default="en,es,fr",
                        help="Comma-separated languages to cycle through per row (subset of en,es,fr).")
    parser.add_argument("--validate", action="store_true", help="Validate an existing prompts file and exit")
    args = parser.parse_args()

    if args.validate:
        path = Path(args.outfile)
        if not path.exists():
            print(f"No file at {path}")
            sys.exit(2)
        issues = validate_file(path)
        sys.exit(0 if issues == 0 else 3)

    langs = [x.strip().lower() for x in args.languages.split(",") if x.strip().lower() in {"en","es","fr"}]
    if not langs:
        raise SystemExit("No valid languages specified. Use a subset of: en,es,fr")

    random.seed(RNG_SEED)

    rows: List[Tuple[str, str, str]] = []

    # ---- Offline deterministic generation (default) ----
    if not args.openai:
        for i in range(args.rows):
            topic = TOPIC_SEEDS[i % len(TOPIC_SEEDS)]
            lang = langs[i % len(langs)]
            p1, p2, t = make_pair(topic, lang)
            rows.append((p1, p2, t))
        write_rows(rows, Path(args.outfile))
        print(f"✅ Wrote {len(rows)} rows to {args.outfile} (pipe-delimited, offline).")
        return

    # ---- Optional OpenAI mode (adds coherent base + targeted follow-up) ----
    try:
        from openai import OpenAI
    except Exception:
        print("OpenAI SDK not installed. Run: pip install openai", file=sys.stderr)
        sys.exit(1)

    client = OpenAI()  # reads OPENAI_API_KEY

    def sys_prompt_for(lang: str) -> str:
        if lang == "en":
            return ("You draft long contextual passages for latency benchmarking.\n"
                    "- Produce a single-paragraph base context (~2000 tokens) for the supplied topic, in English.\n"
                    "- Then produce a follow-up (~200 tokens) that explicitly references the base and asks probing questions/tasks.\n"
                    "- Avoid the '|' character entirely. Avoid markdown. Return JSON with keys: base, extra.\n")
        if lang == "es":
            return ("Redacta pasajes contextuales largos para pruebas de latencia.\n"
                    "- Produce un contexto base (~2000 tokens) para el tema, en español.\n"
                    "- Luego una continuación (~200 tokens) que haga referencia explícita al texto base con preguntas/tareas.\n"
                    "- Evita el carácter '|'. Evita markdown. Devuelve JSON con claves: base, extra.\n")
        return ("Rédige des passages contextuels longs pour des tests de latence.\n"
                "- Produis un contexte de base (~2000 tokens) pour le sujet, en français.\n"
                "- Puis une suite (~200 tokens) qui fait explicitement référence au texte de base avec questions/tâches.\n"
                "- Évite le caractère '|'. Évite le markdown. Retourne un JSON avec les clés: base, extra.\n")

    def fetch_from_llm(topic: str, lang: str) -> Tuple[str, str]:
        sp = sys_prompt_for(lang)
        user_prompt = f"Topic: {topic}\nReturn JSON only."
        resp = client.chat.completions.create(
            model=args.model,
            temperature=0.6,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": sp},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2600,
        )
        content = resp.choices[0].message.content
        obj = json.loads(content)
        base = sanitize_line(obj.get("base", ""))
        extra = sanitize_line(obj.get("extra", ""))
        # Clamp lengths if the model overshoots/undershoots; pad with offline to hit exact-ish targets deterministically.
        if token_len(base) < TARGET_TOKENS_P1:
            pad = synth_base_context(TARGET_TOKENS_P1 - token_len(base), topic, lang)
            base = sanitize_line((base + " " + pad).strip())
        extra = clamp_to_target(extra, TARGET_TOKENS_P2_EXTRA)
        return base, extra

    for i in range(args.rows):
        topic = TOPIC_SEEDS[i % len(TOPIC_SEEDS)]
        lang = langs[i % len(langs)]
        try:
            base, extra = fetch_from_llm(topic, lang)
        except Exception:
            base = synth_base_context(TARGET_TOKENS_P1, topic, lang)
            extra = synth_followup_extra(base, topic, TARGET_TOKENS_P2_EXTRA, lang)
        p1 = sanitize_line(base)
        p2 = sanitize_line(base + " " + extra)
        rows.append((p1, p2, sanitize_line(f"{topic} [{lang}]")))

    write_rows(rows, Path(args.outfile))
    print(f"✅ Wrote {len(rows)} rows to {args.outfile} (pipe-delimited, OpenAI-assisted).")


if __name__ == "__main__":
    main()
    