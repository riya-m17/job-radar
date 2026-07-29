"""Decide whether a posting is worth Riya's attention, and how much."""

from __future__ import annotations

from .util import load_config, settings

TAX = load_config("taxonomy")
SET = settings()

WEIGHTS = {"core": 10, "domain": 6, "role": 5, "supporting": 2}

# Employer categories where a plain job title is enough. "Research Assistant"
# at a genomics institute is worth reading. "Research Analyst, Chemical Market
# Analytics" at a media conglomerate is not, and only the employer tells them
# apart, because the titles are identical.
TRUSTED_EMPLOYERS = {
    "genomics", "biotech", "health_data", "bio_software", "institute",
    "conservation", "marine", "bioacoustics", "museum", "media", "climate",
    "public_health", "policy", "plant_science", "lab_services",
    "consulting", "env_consulting",
}


def _hay(job: dict) -> str:
    return " ".join([
        job.get("title", ""),
        job.get("department", ""),
        job.get("description", "")[:4000],
    ]).lower()


def _title(job: dict) -> str:
    return (job.get("title") or "").lower()


def excluded(job: dict) -> str | None:
    """Return the reason a posting is dropped, or None to keep it."""
    title = _title(job)
    hay = _hay(job)

    # Seniority and hard ML are judged on the title, where they are decisive.
    for phrase in TAX["exclude"]["seniority"]:
        if phrase in title:
            return f"seniority: {phrase}"
    for phrase in TAX["exclude"]["hard_ml"]:
        if phrase in title:
            return f"machine learning role: {phrase}"
    for phrase in TAX["exclude"]["off_domain"]:
        if phrase in title:
            return f"off domain: {phrase}"

    # Standing exclusions are judged on the whole posting.
    for phrase in TAX["exclude"]["standing"]:
        if phrase in hay:
            return f"excluded sector: {phrase}"

    # Too much experience wanted.
    for phrase in TAX["experience_ceiling"]:
        if phrase in hay:
            return f"experience bar: {phrase}"
    return None


def relevance(job: dict) -> tuple[int, list[str]]:
    """Score a posting and report which terms earned the points.

    A posting has to name the subject to qualify. Core and domain terms do
    that on their own. A bare role title only counts when the employer is one
    Riya actually cares about, and supporting terms never qualify anything.
    """
    title = _title(job)
    hay = _hay(job)
    score, hits = 0, []
    tiers_hit = set()

    for tier, weight in WEIGHTS.items():
        for phrase in TAX["include"][tier]:
            if phrase in title:
                score += weight * 2          # a title match counts double
                hits.append(phrase)
                tiers_hit.add(tier)
            elif phrase in hay:
                score += weight
                hits.append(phrase)
                tiers_hit.add(tier)

    anchored = bool(tiers_hit & {"core", "domain"})
    if not anchored and "role" in tiers_hit:
        # A bare role title needs corroboration: either the employer is one of
        # hers, or the posting itself mentions the subject somewhere.
        anchored = (job.get("org_cat") in TRUSTED_EMPLOYERS
                    or "supporting" in tiers_hit)
    if not anchored:
        return 0, []

    # Employer-level context. A conservation NGO posting a coordinator role is
    # more interesting than a generic coordinator role somewhere else.
    if job.get("org_cat") in ("conservation", "marine", "bioacoustics",
                              "museum", "institute", "genomics"):
        score += 6
    if job.get("cap_exempt"):
        score += 4

    return score, sorted(set(hits))[:12]


def role_type(job: dict) -> str:
    title = _title(job)
    hay = _hay(job)
    for kind in ("internship", "fellowship", "seasonal", "new_grad"):
        for phrase in TAX["role_types"][kind]:
            if phrase in title:
                return kind
    for kind in ("internship", "fellowship", "seasonal"):
        for phrase in TAX["role_types"][kind]:
            if phrase in hay[:1200]:
                return kind
    return "full_time"


US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia", "puerto rico",
}
US_ABBR = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc", "pr",
}


def _is_us(loc: str) -> bool:
    if any(m in loc for m in ("united states", "usa", "u.s.a", "u.s.")):
        return True
    parts = [p.strip() for chunk in loc.split(";") for p in chunk.split(",")]
    return any(p in US_ABBR or p in US_STATES for p in parts)


def region(job: dict) -> str:
    loc = (job.get("location") or "").lower()
    geo = SET["geography"]
    base = "Remote" if any(m in loc for m in geo["remote_markers"]) else ""
    if _is_us(loc) or (not loc and job.get("country_hint") == "US"):
        return "US remote" if base else "US"
    if base:
        return "Remote"
    if not loc:
        return job.get("country_hint") or "Unspecified"
    for token, label in (("united kingdom", "UK"), ("london", "UK"), ("england", "UK"),
                         ("denmark", "Denmark"), ("copenhagen", "Denmark"),
                         ("germany", "Germany"), ("netherlands", "Netherlands"),
                         ("switzerland", "Switzerland"), ("france", "France"),
                         ("canada", "Canada"), ("india", "India"),
                         ("singapore", "Singapore"), ("australia", "Australia"),
                         ("kenya", "Kenya"), ("brazil", "Brazil")):
        if token in loc:
            return label
    return job.get("country_hint") or "Other"


def classify(job: dict) -> dict | None:
    reason = excluded(job)
    if reason:
        job["_dropped"] = reason
        return None
    score, hits = relevance(job)
    if score < SET["run"]["min_relevance"]:
        job["_dropped"] = f"below threshold ({score})"
        return None
    job["relevance"] = score
    job["match_terms"] = hits
    job["role_type"] = role_type(job)
    job["region"] = region(job)
    return job
