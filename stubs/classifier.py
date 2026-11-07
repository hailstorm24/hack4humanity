"""Narrative Classifier stub (classifier-api.yaml) on :8001.

No model: a keyword table over lower-cased Russian text produces
deterministic labels so the rest of the pipeline can be exercised.
Swap `score_text` for the real model; the HTTP contract stays the same.

Test hooks (stub only):
  - text containing "#fail"  -> 503 model_unavailable
  - text containing "#slow"  -> sleeps 12 s (exceeds the runtime's 10 s timeout)
"""
import time

from common import HttpError, error, load_taxonomy, serve

TAXONOMY = load_taxonomy()
MODEL_VERSION = "stub-keywords-0.1"

# (keywords, narrative, subnarrative|None, score). First keyword hit wins per rule.
RULES = [
    (["провоцир", "провокац", "запад развязал", "агрессия запада", "запад начал"],
     "Blaming the war on others rather than the invader", "The West are the aggressors", 0.88),
    (["украина напала", "киев начал войну", "обстрел донбасса", "украинская агрессия"],
     "Blaming the war on others rather than the invader", "Ukraine is the aggressor", 0.84),
    (["нацист", "неонацист", "бандер", "фашист"],
     "Discrediting Ukraine", "Ukraine is associated with nazism", 0.86),
    (["марионет", "под диктовку", "вашингтон управляет", "внешнее управление"],
     "Discrediting Ukraine", "Ukraine is a puppet of the West", 0.8),
    (["коррумпир", "зеленский украл", "киевский режим"],
     "Discrediting Ukraine", "Discrediting Ukrainian government and officials and policies", 0.74),
    (["всу бегут", "всу разваливаются", "украинская армия разваливается", "всу деморализ"],
     "Speculating war outcomes", "Ukrainian army is collapsing", 0.77),
    (["русофоб", "отмена русской культуры", "ненавидят русских"],
     "Russia is the Victim", "The West is russophobic", 0.82),
    (["самооборон", "защита донбасса", "вынуждена защищаться"],
     "Russia is the Victim", "Russia actions in Ukraine are only self-defence", 0.78),
    (["путин гениал", "мудрый путин", "великий лидер"],
     "Praise of Russia", "Praise of Russian President Vladimir Putin", 0.8),
    (["санкции ударили по европе", "санкции бьют по", "европа замерзнет", "бумеранг санкц"],
     "Negative Consequences for the West", "Sanctions imposed by Western countries will backfire", 0.83),
    (["западные сми лгут", "пропаганда запада", "западная пропаганда", "сми врут"],
     "Distrust towards Media", "Western media is an instrument of propaganda", 0.79),
    (["третья мировая", "мировой войн"],
     "Amplifying war-related fears", "By continuing the war we risk WWIII", 0.81),
    (["ядерн", "красную кнопку"],
     "Amplifying war-related fears", "There is a real possibility that nuclear weapons will be employed", 0.85),
    (["устал от украины", "усталость от украины", "запад устал"],
     "Discrediting the West, Diplomacy", "West is tired of Ukraine", 0.72),
    (["запад", "европа", "сша"],
     "Discrediting the West, Diplomacy", None, 0.41),
    (["биолаборатор", "мировое правительство", "тайный план", "глобалист"],
     "Hidden plots by secret schemes of powerful groups", None, 0.76),
]


def _check_rules():
    valid = {(n["name"], s) for n in TAXONOMY["narratives"] for s in n["subnarratives"] + [None]}
    for _, n, s, _ in RULES:
        assert (n, s) in valid, f"rule label not in taxonomy: {n!r} / {s!r}"


def score_text(text):
    low = text.lower()
    labels = [{"narrative": n, "subnarrative": s, "score": sc}
              for kws, n, s, sc in RULES if any(k in low for k in kws)]
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


ROUTES = [
    ("POST", r"/v1/classify", classify),
    ("GET", r"/v1/taxonomy", lambda r, m, b: (200, TAXONOMY)),
    ("GET", r"/v1/health", lambda r, m, b: (200, {"status": "ok"})),
]

if __name__ == "__main__":
    _check_rules()
    serve(ROUTES, 8001, "classifier")
