# make_prompts_openai.py
import os, json, time, re, csv, sys
from typing import Tuple
from openai import OpenAI

OUTFILE = "prompts.txt"   # one line: prompt1,prompt2
NUM_PAIRS = 1000
MODEL = "gpt-4o-mini"     # fast & cheap; change if you want

client = OpenAI()  # reads OPENAI_API_KEY from env

SYSTEM = (
    "You generate benchmark prompt PAIRS for latency testing.\n"
    "- Each output MUST be JSON with keys: prompt1, prompt2, topic.\n"
    "- The two prompts must be closely related to EACH OTHER (same topic), "
    "  but every CALL must use a brand-new topic never used before.\n"
    "- Each prompt MUST be ~20–30 words (acceptable range 18–32).\n"
    "- DO NOT use commas in either prompt. Avoid punctuation that acts like commas.\n"
    "- The 'topic' is a short 2–5 word label (no commas) summarizing the pair.\n"
    "- Do not include explanations or extra fields."
)

USER_TEMPLATE = (
    "Produce a new JSON object for pair #{i} with a UNIQUE topic not used before.\n"
    "Return ONLY JSON (no backticks, no prose)."
)

def wc(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s))

def invalid_prompt(p: str) -> str:
    if "," in p:
        return "contains comma"
    n = wc(p)
    if n < 18 or n > 32:
        return f"wordcount {n} (needs 18–32)"
    if "\n" in p:
        return "contains newline"
    return ""

def ask_model(i: int) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        temperature=0.9,
        max_tokens=300,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER_TEMPLATE.format(i=i+1)},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # sometimes models wrap JSON in code fences; try to strip them
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            return json.loads(m.group(0))
        raise

def main():
    used_topics = set()
    written = 0

    # If continuing a previous run, load topics to avoid duplicates
    if os.path.exists(OUTFILE):
        with open(OUTFILE, newline="", encoding="utf-8") as f:
            r = csv.reader(f)
            for row in r:
                if len(row) == 3 and row[2].strip():
                    used_topics.add(row[2].strip())

    with open(OUTFILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        i = 0
        while written < NUM_PAIRS:
            for attempt in range(6):
                try:
                    obj = ask_model(i)
                except Exception as e:
                    print(f"Error (API): {e}", file=sys.stderr)
                    time.sleep(1.5)
                    continue

                # Validate presence
                if not all(k in obj for k in ("prompt1", "prompt2", "topic")):
                    print("Error: missing keys in response", file=sys.stderr)
                    time.sleep(0.8); continue

                p1 = str(obj["prompt1"]).strip()
                p2 = str(obj["prompt2"]).strip()
                topic = re.sub(r"\s+", " ", str(obj["topic"]).strip())

                # Basic validations
                bad1 = invalid_prompt(p1)
                bad2 = invalid_prompt(p2)
                if bad1:
                    print(f"Error: prompt1 {bad1}", file=sys.stderr); time.sleep(0.5); continue
                if bad2:
                    print(f"Error: prompt2 {bad2}", file=sys.stderr); time.sleep(0.5); continue
                if topic.lower() in used_topics:
                    print("Error: duplicate topic, regenerating", file=sys.stderr); time.sleep(0.5); continue
                if wc(p1) < 18 or wc(p2) < 18:
                    print("Error: too short", file=sys.stderr); time.sleep(0.5); continue

                # Looks good; write as CSV WITH a third column for the topic
                # (your reader can still take first two columns; topic is just for dedupe)
                w.writerow([p1, p2, topic])
                used_topics.add(topic.lower())
                written += 1
                i += 1
                if written % 50 == 0:
                    print(f"Generated {written}/{NUM_PAIRS}")
                break
            else:
                print("Failed too many times for this pair; retrying…", file=sys.stderr)
                time.sleep(2)

    print(f"✅ Wrote/updated {OUTFILE} with {written} new pairs.")

if __name__ == "__main__":
    main()
    