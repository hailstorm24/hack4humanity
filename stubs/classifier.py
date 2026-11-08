"""Narrative Classifier stub (classifier-api.yaml) on :8001.

No model: keyword rules from classifier_rules.json produce deterministic
labels so the rest of the pipeline can be exercised. Swap `score_text` for
the real model; the HTTP contract stays the same.

Matching: text is lower-cased, ё→е, whitespace collapsed; each keyword
(Russian or English) matches where a word starts, so stems like "провоцир"
catch every ending but "нато" doesn't fire inside "донатов". Every rule with
a hit gives one label at its base score, +0.03 per extra keyword hit from
that rule, capped at 0.97. See docs/classifier-stub-plan.md.

Test hooks (stub only):
  - text containing "#fail"  -> 503 model_unavailable
  - text containing "#slow"  -> sleeps 12 s (exceeds the runtime's 10 s timeout)

`python3 classifier.py --demo [ru|en]` prints one demo sentence per label.
"""
import json
import os
import re
import sys
import time

from common import HERE, HttpError, error, load_taxonomy, serve

TAXONOMY = load_taxonomy()
RULES_PATH = os.path.join(HERE, "classifier_rules.json")
HIT_BONUS = 0.03
MAX_SCORE = 0.97
LANGS = ("ru", "en")


def normalize(text):
    return re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()


def load_rules(path=RULES_PATH, taxonomy=TAXONOMY):
    """Load and validate the rule file; raise ValueError on any problem."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    valid = {(n["name"], s) for n in taxonomy["narratives"] for s in n["subnarratives"] + [None]}
    seen, rules = {}, []
    for i, r in enumerate(doc["rules"]):
        where = f"rule {i} ({r.get('subnarrative') or r.get('narrative')})"
        label = (r["narrative"], r["subnarrative"])
        if label not in valid:
            raise ValueError(f"{where}: label not in taxonomy")
        if not 0 <= r["score"] <= 1:
            raise ValueError(f"{where}: score out of range")
        if r["score"] >= 0.5 and not all(r.get("demo", {}).get(lang) for lang in LANGS):
            raise ValueError(f"{where}: needs a demo sentence for {LANGS}")
        keywords = [normalize(k) for lang in LANGS for k in r["keywords"].get(lang, [])]
        if not keywords:
            raise ValueError(f"{where}: no keywords")
        for k in keywords:
            if k in seen:
                raise ValueError(f"{where}: keyword {k!r} already used by rule {seen[k]}")
            seen[k] = i
        rules.append({**r, "patterns": [re.compile(r"(?<!\w)" + re.escape(k)) for k in keywords]})
    return doc["model_version"], rules


MODEL_VERSION, RULES = load_rules()


def score_text(text):
    low = normalize(text)
    labels = []
    for r in RULES:
        hits = sum(1 for p in r["patterns"] if p.search(low))
        if hits:
            score = min(MAX_SCORE, round(r["score"] + HIT_BONUS * (hits - 1), 2))
            labels.append({"narrative": r["narrative"], "subnarrative": r["subnarrative"], "score": score})
    return sorted(labels, key=lambda l: l["score"], reverse=True)


def classify(req, match, body):
    if not isinstance(body, dict) or set(body) != {"text"} or not isinstance(body["text"], str):
        raise HttpError(400, error("invalid_request", "Body must be exactly {\"text\": string}"))
    text = body["text"]
    if not 1 <= len(text) <= 4096:
        raise HttpError(400, error("invalid_request", "text must be 1-4096 characters"))
    if "#fail" in text:
        raise HttpError(503, error("model_unavailable", "Stub failure triggered by #fail"))
    if "#slow" in text:
        time.sleep(12)
    return 200, {"labels": score_text(text), "model_version": MODEL_VERSION}


def print_demos(langs=LANGS):
    for r in RULES:
        if "demo" not in r:
            continue
        print(f"{r['narrative']} / {r['subnarrative'] or '(narrative only)'}")
        for lang in langs:
            print(f"  {lang}: {r['demo'][lang]}")


ROUTES = [
    ("POST", r"/v1/classify", classify),
    ("GET", r"/v1/taxonomy", lambda r, m, b: (200, TAXONOMY)),
    ("GET", r"/v1/health", lambda r, m, b: (200, {"status": "ok"})),
]

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        print_demos(tuple(sys.argv[2:]) or LANGS)
    else:
        serve(ROUTES, 8001, "classifier")
