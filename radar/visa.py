"""Judge how workable a posting is for someone who needs sponsorship.

The default assumption everywhere is that sponsorship is required. That is the
safe reading and it needs no personal detail in any config file: a posting is
only treated as workable when it says something that makes it workable.

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

# Hard stops. If a posting says one of these, you cannot apply, so these are
# dropped from the dashboard entirely rather than ranked down.
BLOCKING = [
    # Citizenship
    "u.s. citizenship is required", "us citizenship is required",
    "must be a u.s. citizen", "must be a us citizen", "citizenship required",
    "citizens only", "must be a citizen", "national of the united states",
    "federal employment eligibility", "u.s. citizenship required",
    # Permanent residence, which an F-1 is not
    "citizen or permanent resident", "citizens or permanent residents",
    "citizens and permanent residents", "lawful permanent resident",
    "must be a permanent resident", "permanent resident status required",
    "green card required", "green card holders only",
    "u.s. person", "us person as defined",
    # Clearance and export control, which require citizenship in practice
    "security clearance", "active clearance", "top secret", "ts/sci",
    "public trust clearance", "itar", "export control", "export-controlled",
    "ability to obtain a clearance", "dod clearance",
]

NEGATIVE = [
    "no visa sponsorship", "not offer sponsorship", "does not offer sponsorship",
    "unable to sponsor", "cannot sponsor", "will not sponsor",
    "not able to provide sponsorship", "without sponsorship now or in the future",
    "not require sponsorship", "no sponsorship available",
    "must have permanent work authorization", "permanent authorization to work",
    "authorized to work without sponsorship", "not provide immigration sponsorship",
    "not eligible for visa sponsorship", "sponsorship is not available",
    "without the need for sponsorship", "without requiring sponsorship",
    "sponsorship will not be provided", "no sponsorship will be offered",
    "legally authorized to work in the united states without sponsorship",
    "authorized to work in the us without sponsorship",
    "now or in the future require sponsorship",
    "do not provide visa sponsorship",
]

POSITIVE = [
    "visa sponsorship", "sponsor a visa", "will sponsor", "we sponsor",
    "sponsorship available", "h-1b", "h1b", "immigration support",
    "relocation and visa", "opt", "cpt", "f-1", "f1 visa", "stem opt",
    "cap exempt", "cap-exempt", "international candidates welcome",
    "open to international applicants", "work permit support",
    "we support work visas", "support work permit", "support work permits",
    "work permits and relocation", "assist with work permit",
    "relocation package", "relocation assistance", "relocation support",
    "help with relocation", "we welcome applicants from",
    "regardless of nationality", "visa and relocation",
]


# Non-US phrasing for "you must already have the right to work here", which is
# the European and UK equivalent of the US no-sponsorship line.
WORK_RIGHTS_REQUIRED = [
    "right to work in the uk", "right to work in the united kingdom",
    "must have the right to work", "existing right to work",
    "eu work permit", "eu citizenship", "eea citizen",
    "valid work permit", "already hold a work permit",
    "must hold a valid residence permit", "danish work permit",
    "no relocation support", "we do not offer relocation",
    "applicants must be eligible to work in",
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

    hit = _flag(text, WORK_RIGHTS_REQUIRED)
    if hit:
        return _verdict(
            "unlikely",
            f"posting expects existing work rights: {hit}")

    region = job.get("region", "")

    if region == "Not stated":
        # The posting did not say where the work is. Asserting a permit
        # requirement here would be inventing a fact, so say what is true.
        return _verdict(
            "unknown",
            "the posting does not state a location, so eligibility cannot be "
            "read from it. Check the listing before spending time on it")

    if region not in ("US", "US remote"):
        # An F-1 is irrelevant here, but a work permit is not. Nothing in this
        # posting says the employer helps with one, so it stays an open
        # question rather than a free pass.
        return _verdict(
            "permit",
            "outside the US, so this needs a local work permit and the posting "
            "does not mention supporting one")

    if job.get("cap_exempt"):
        return _verdict(
            "likely",
            "H-1B cap exempt employer, so it can file outside the lottery")

    return _verdict("unknown", "the posting says nothing either way, ask before applying")


def _verdict(status: str, why: str) -> dict:
    rank = {"explicit": 5, "likely": 4, "unknown": 3, "permit": 2,
            "unlikely": 1, "blocked": 0}[status]
    return {"visa_status": status, "visa_reason": why, "visa_rank": rank}
