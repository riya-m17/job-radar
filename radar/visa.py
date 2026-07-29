"""Judge how workable a posting is for someone on an F-1 visa.

No job board reliably tags sponsorship, so this reads the posting language and
combines it with what is known about the employer. Five verdicts:

  explicit  the posting says it sponsors, or names OPT, CPT or F-1
  likely    no blocking language and the employer is a strong bet, usually an
            H-1B cap exempt university, nonprofit or research institute
  unknown   nothing either way, which is the majority of postings
  unlikely  language that usually means no, such as needing authorization
            without sponsorship now or in future
  blocked   citizenship, clearance or ITAR requirements

The cap exempt flag matters more than most people realise. Universities,
affiliated nonprofits and nonprofit research institutes are exempt from the
H-1B lottery, so they can file any time of year without competing for the cap.
For a graduating international student that is the single biggest structural
advantage available, and it is why those employers are scored up.
"""

from __future__ import annotations

BLOCKING = [
    "u.s. citizenship is required", "us citizenship is required",
    "must be a u.s. citizen", "must be a us citizen", "citizenship required",
    "citizens only", "security clearance", "active clearance", "top secret",
    "public trust clearance", "itar", "export control", "must be a citizen",
    "national of the united states", "federal employment eligibility",
]

NEGATIVE = [
    "no visa sponsorship", "not offer sponsorship", "does not offer sponsorship",
    "unable to sponsor", "cannot sponsor", "will not sponsor",
    "not able to provide sponsorship", "without sponsorship now or in the future",
    "not require sponsorship", "no sponsorship available",
    "must have permanent work authorization", "permanent authorization to work",
    "authorized to work without sponsorship", "not provide immigration sponsorship",
    "not eligible for visa sponsorship", "sponsorship is not available",
]

POSITIVE = [
    "visa sponsorship", "sponsor a visa", "will sponsor", "we sponsor",
    "sponsorship available", "h-1b", "h1b", "immigration support",
    "relocation and visa", "opt", "cpt", "f-1", "f1 visa", "stem opt",
    "cap exempt", "cap-exempt", "international candidates welcome",
    "open to international applicants", "work permit support",
    "we support work visas", "eligible to work in the",
]


def _flag(text: str, phrases: list[str]) -> str | None:
    for p in phrases:
        if p in text:
            return p
    return None


def assess(job: dict) -> dict:
    text = " ".join([
        job.get("title", ""),
        job.get("description", "")[:8000],
    ]).lower()

    # Some feeds state sponsorship as structured data. Trust that first.
    declared = (job.get("sponsorship_declared") or "").lower()
    if "does not offer" in declared:
        return _verdict("unlikely", "the posting states it does not sponsor")
    if "citizenship is required" in declared:
        return _verdict("blocked", "the posting requires US citizenship")
    if "offers sponsorship" in declared:
        return _verdict("explicit", "the posting states it offers sponsorship")

    hit = _flag(text, BLOCKING)
    if hit:
        return _verdict("blocked", f"posting mentions {hit}")

    hit = _flag(text, NEGATIVE)
    if hit:
        return _verdict("unlikely", f"posting mentions {hit}")

    hit = _flag(text, POSITIVE)
    if hit:
        return _verdict("explicit", f"posting mentions {hit}")

    region = job.get("region", "")
    if region not in ("US", "US remote"):
        return _verdict(
            "n/a",
            "outside the US, so F-1 does not apply and local work rights decide it")

    if job.get("cap_exempt"):
        return _verdict(
            "likely",
            "H-1B cap exempt employer, so it can file outside the lottery")

    return _verdict("unknown", "the posting says nothing either way, ask before applying")


def _verdict(status: str, why: str) -> dict:
    rank = {"explicit": 5, "likely": 4, "unknown": 3, "n/a": 2,
            "unlikely": 1, "blocked": 0}[status]
    return {"visa_status": status, "visa_reason": why, "visa_rank": rank}
