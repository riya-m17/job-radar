"""Read what a posting actually requires, and decide whether you could get it.

Two separate jobs here.

The experience bar. A posting asking for five years is not going to hire a May
2027 graduate no matter how good the keyword match is, and leaving those on the
dashboard is worse than useless because they look like opportunities. This
pulls the number out of the text and treats the lowest stated figure as the
bar, so "2 to 4 years, 5 preferred" is a two year bar rather than a five.

Academic bench roles. A research technician position in a named professor's
laboratory at a university is a specific kind of job: you run somebody else's
experiments at the bench, usually as a stepping stone to a doctorate. That is
not what you are looking for, so those are removed. Note the two things this
does NOT touch. Non-university research institutes stay, because the Broad and
the New York Genome Center and Woods Hole are not universities and their
post-bac and analyst roles are among the best fits you have. And the employer
stays in the registry either way, so a university whose current openings are
all wrong is still watched for the day it posts something right.
"""

from __future__ import annotations

import re

from .util import settings

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# "3+ years", "3-5 years", "minimum of 4 years", "at least three years"
_YEARS = re.compile(
    r"(?:(?:minimum|at least|min\.?)\s+(?:of\s+)?)?"
    r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\b"
    r"\s*(?:\+|plus)?\s*(?:(?:to|-|–|or)\s*\d{1,2}\s*(?:\+|plus)?\s*)?"
    r"\s*year",
    re.I)

# Only count a number as an experience bar if experience is being discussed
# nearby. Plenty of postings mention two year programmes and ten year datasets.
_EXPERIENCE_CONTEXT = re.compile(
    r"(experience|background|track record|working in|practising|practicing"
    r"|professional|industry|post[- ]qualification|relevant)", re.I)

# Deliberately narrow. An earlier version excluded any window containing the
# word "programme", which quietly swallowed "three years experience in
# programme delivery" and let a senior role through.
_NOT_A_BAR = re.compile(
    r"(within the (?:last|past)|over the (?:last|past)|in the (?:last|past)"
    r"|year (?:programme|program|appointment|position|contract|traineeship)"
    r"|programme length|program length|programme duration|program duration"
    r"|term of \d|fixed[- ]term|first year|per year|each year"
    r"|years of study|final year|years of data|year study|year dataset)", re.I)

DOCTORAL = [
    "phd required", "ph.d. required", "phd is required", "requires a phd",
    "must have a phd", "doctorate required", "doctoral degree required",
    "phd or equivalent", "ph.d. or equivalent", "phd in hand",
    "phd student", "phd position", "phd candidate", "phd fellowship",
    "doctoral candidate", "doctoral student", "doctoral position",
    "graduate research assistantship", "graduate assistantship",
    "md required", "md/phd", "must hold a doctorate",
]

MASTERS_REQUIRED = [
    "master's degree required", "masters degree required",
    "ms required", "m.s. required", "msc required",
    "master's is required", "requires a master's",
]

UNIVERSITY_MARKERS = [
    "university", "universität", "université", "universidad", "universiteit",
    "college", "polytechnic", "school of medicine", "school of public health",
    "school of nursing", "state univ", " univ.",
]
# Names that contain a university marker but are not universities.
UNIVERSITY_EXCEPTIONS = [
    "academy of sciences", "college of physicians", "royal college",
    "imperial college healthcare", "college board",
]

# Bench work in somebody's lab, whoever the employer is.
BENCH_ROLE_TITLES = [
    "research technician", "laboratory technician", "lab technician",
    "research technologist", "laboratory assistant", "lab assistant",
    "laboratory research", "research aide", "lab aide", "lab helper",
    "animal technician", "vivarium", "histotechn", "lab manager",
    "laboratory manager", "research support technician",
]
PI_LAB_PHRASES = [
    "in the laboratory of", "in the lab of", "the laboratory of dr",
    "the lab of dr", "the laboratory of professor", "pi's lab",
    "principal investigator's lab", "under the supervision of professor",
    "join the lab of", "laboratory of professor",
]


def _int(token: str) -> int | None:
    token = token.lower()
    if token.isdigit():
        return int(token)
    return WORD_NUMBERS.get(token)


def years_required(text: str) -> int | None:
    """The lowest number of years the posting genuinely asks for."""
    bars = []
    for match in _YEARS.finditer(text):
        start, end = match.span()
        window = text[max(0, start - 120):min(len(text), end + 120)]
        if _NOT_A_BAR.search(window):
            continue
        if not _EXPERIENCE_CONTEXT.search(window):
            continue
        value = _int(match.group(1))
        # Zero is a real answer and a good one: "0-2 years" is a new grad role.
        if value is not None and 0 <= value <= 25:
            bars.append(value)
    return min(bars) if bars else None


def _hit(text: str, phrases: list[str]) -> str | None:
    for p in phrases:
        if p in text:
            return p
    return None


def is_university(company: str) -> bool:
    low = (company or "").lower()
    if any(x in low for x in UNIVERSITY_EXCEPTIONS):
        return False
    return any(m in low for m in UNIVERSITY_MARKERS)


def assess(job: dict) -> dict:
    text = " ".join([
        job.get("title", ""),
        job.get("department", ""),
        job.get("description", "")[:9000],
    ]).lower()
    title = (job.get("title") or "").lower()

    years = years_required(text)
    doctoral = _hit(text, DOCTORAL)
    masters = _hit(text, MASTERS_REQUIRED)

    uni = is_university(job.get("company", ""))
    bench_title = _hit(title, BENCH_ROLE_TITLES)
    pi_lab = _hit(text, PI_LAB_PHRASES)
    academic_bench = bool(pi_lab or (uni and bench_title))

    if doctoral:
        verdict, detail = "doctorate", f"asks for a doctorate: {doctoral}"
    elif years is None:
        verdict, detail = "unstated", "no experience requirement stated"
    elif years <= 1:
        verdict, detail = "new grad ok", f"{years} year of experience"
    elif years <= 2:
        verdict, detail = "stretch", f"{years} years of experience"
    else:
        verdict, detail = "too senior", f"{years} years of experience"

    return {
        "years_required": years,
        "degree_bar": "doctorate" if doctoral else ("masters" if masters else None),
        "experience_verdict": verdict,
        "experience_detail": detail,
        "is_university": uni,
        "academic_bench": academic_bench,
        "academic_reason": pi_lab or bench_title or "",
    }


def rejected(job: dict) -> str | None:
    """Why this posting cannot realistically be applied to, or None."""
    cfg = settings()["run"]

    if cfg.get("drop_academic_bench", True) and job.get("academic_bench"):
        return f"university bench role ({job.get('academic_reason')})"

    if job.get("degree_bar") == "doctorate":
        return "requires a doctorate"

    if cfg.get("drop_masters_required") and job.get("degree_bar") == "masters":
        return "requires a master's"

    years = job.get("years_required")
    ceiling = cfg.get("max_years_experience", 2)
    if years is not None and years > ceiling:
        return f"wants {years} years of experience"
    return None
