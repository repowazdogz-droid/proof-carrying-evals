"""model.py - local model under evaluation, via Ollama.

The model produces structured governed decisions in response to requests.
No cloud. Auto-detects an available Ollama model, preferring fast
non-reasoning chat models (reasoning models emit <think> blocks that fight
JSON parsing).
"""

import json
import re
import urllib.request

OLLAMA = "http://127.0.0.1:11434"

# Preference order. We match by substring against installed tags. We avoid
# qwen3 / deepseek-r1 by default because they are reasoning models (slow,
# emit <think> tags) which complicates structured-JSON extraction.
PREFERRED = [
    "llama3.1",
    "qwen2.5",
    "llama3",
    "qwen2.5-coder",
    "mistral-small3.1",
    "mistral",
    "gemma3",
    "gemma",
]


def _http_json(path, payload=None, timeout=180):
    url = OLLAMA + path
    if payload is None:
        req = urllib.request.Request(url, method="GET")
    else:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_models():
    try:
        d = _http_json("/api/tags", timeout=10)
        return [m["name"] for m in d.get("models", [])]
    except Exception:
        return []


def detect_model():
    """Return the name of the best available model, or None if Ollama is down."""
    installed = list_models()
    if not installed:
        return None
    for pref in PREFERRED:
        for tag in installed:
            if pref in tag:
                return tag
    # Fall back to the first installed model that is not an embedding model.
    for tag in installed:
        if "embed" not in tag:
            return tag
    return installed[0]


def _extract_json(text):
    """Pull the first JSON object out of a model response. Returns dict or None."""
    if text is None:
        return None
    # strip reasoning blocks if any leaked through
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # strip code fences
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    # find the first balanced-ish JSON object
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    return json.loads(blob)
                except Exception:
                    return None
    return None


def generate(model, prompt, system=None, temperature=0.0, seed=None, force_json=True,
             timeout=180):
    """Raw text generation. Returns the response string (possibly empty)."""
    options = {"temperature": temperature}
    if seed is not None:
        options["seed"] = seed
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": options,
    }
    if system:
        payload["system"] = system
    if force_json:
        payload["format"] = "json"
    try:
        d = _http_json("/api/generate", payload, timeout=timeout)
        return d.get("response", "")
    except Exception as e:
        return f"__ERROR__ {e}"


def generate_json(model, prompt, system=None, temperature=0.0, seed=None, timeout=180):
    """Generation that returns a parsed dict (or None on failure)."""
    raw = generate(model, prompt, system=system, temperature=temperature, seed=seed,
                   force_json=True, timeout=timeout)
    if raw.startswith("__ERROR__"):
        return None, raw
    return _extract_json(raw), raw
