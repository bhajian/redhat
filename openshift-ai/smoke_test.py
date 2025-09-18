import json, httpx, pprint, textwrap

def smoke(url: str):
    payload = {
        "model": "llama3",
        "messages": [{"role": "user", "content": PROMPT}],
        "max_new_tokens": 32,
        "stream": False
    }
    r = httpx.post(f"{url}/v1/chat/completions",
                   headers=HEADERS, json=payload, timeout=60.0, verify=False)
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]["content"]
    print(f"\n🟢  {url}\n" + textwrap.fill(msg, 88))

smoke(VLLM_URL)
smoke(TGI_URL)
