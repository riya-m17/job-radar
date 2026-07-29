"""Score a posting against what Riya can actually do, not against keywords.

The difference matters. A posting scores under classify.py because it contains
the word genomics. It scores here because it asks for Biopython and BLAST and
she has phage genome analysis, or because it wants passive acoustic monitoring
and she has harbour porpoise field work and the narwhal project. The second
kind of match is the one worth acting on, and the dashboard shows the
overlapping terms on every row so the reason is visible rather than implied.
"""

from __future__ import annotations

from .util import load_config

PROFILE = load_config("profile")

GROUP_WEIGHTS = {
    "signature": 8,     # rare, and strongly hers
    "core": 5,
    "wet_lab": 5,
    "field": 5,
    "communication": 3,
}
LEARNING_WEIGHT = 2     # honest stretch, worth seeing
EDUCATION_WEIGHT = 2


def assess(job: dict) -> dict:
    text = " ".join([
        job.get("title", ""),
        job.get("department", ""),
        job.get("description", "")[:8000],
    ]).lower()

    score = 0
    hits: list[str] = []
    signature_hits: list[str] = []

    for group, weight in GROUP_WEIGHTS.items():
        for term in PROFILE["skills"].get(group, []):
            if term in text:
                score += weight
                hits.append(term)
                if group == "signature":
                    signature_hits.append(term)

    for term in PROFILE.get("learning", []):
        if term in text:
            score += LEARNING_WEIGHT
            hits.append(term)

    for term in PROFILE.get("education", []):
        if term in text:
            score += EDUCATION_WEIGHT
            break

    # Ranking is by strength of overlap, not raw count, so a posting naming one
    # rare thing she has beats a posting naming five generic ones.
    return {
        "skill_score": score,
        "skill_hits": sorted(set(hits), key=lambda t: -len(t))[:8],
        "signature_hits": sorted(set(signature_hits)),
        "has_signature": bool(signature_hits),
    }
