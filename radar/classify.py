"""Decide whether a posting is worth Riya's attention, and how much."""

from __future__ import annotations

import re

from .util import load_config, settings, text_of

TAX = load_config("taxonomy")
SET = settings()

WEIGHTS = {"core": 10, "domain": 6, "commercial": 6, "creative": 6,
           "role": 5, "supporting": 2}

# What kind of work is this, as opposed to what field is it in. She is not only
# a bench scientist and does not want a board that implies she is, so this is
# tagged and filterable, and the dashboard shows the mix.
FLAVOURS = {
    "bench": ["cell culture", "pipette", "bench", "wet lab", "assay",
              "western blot", "pcr", "cloning", "microscopy", "in situ",
              "dissection", "histolog", "vivarium", "reagent", "protocol"],
    "computational": ["python", "\bR\b", "bioinformatic", "pipeline", "dataset",
                      "sql", "statistical", "algorithm", "machine learning",
                      "data analysis", "computational", "code", "script"],
    "field": ["field work", "fieldwork", "field season", "survey", "boat",
              "vessel", "transect", "tracking", "trapping", "remote site",
              "outdoors", "hiking", "weather"],
    "commercial": ["customer", "client", "sales", "revenue", "pipeline of",
                   "territory", "quota", "prospect", "market", "commercial",
                   "stakeholder", "partner"],
    "creative": ["design", "illustration", "visual", "story", "narrative",
                 "editorial", "writing", "content", "audience", "exhibit",
                 "photograph", "video", "brand"],
    "comms": ["communicat", "outreach", "public engagement", "教育", "education",
              "workshop", "presentation", "teaching", "curriculum", "training"],
}

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
        text_of(job, "title"),
        text_of(job, "department"),
        text_of(job, "description", 4000),
    ]).lower()


def _title(job: dict) -> str:
    return text_of(job, "title").lower()


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
    # This group existed in taxonomy.yaml but was never read, so pure software
    # roles were only being dropped by accident when they failed to anchor.
    for phrase in TAX["exclude"].get("software", []):
        if phrase in title:
            return f"software engineering role: {phrase}"
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

    # Only subject matter qualifies a posting on its own. Everything else is a
    # role shape, and a role shape needs life science context: either the
    # employer is one of hers, or the posting names the subject somewhere.
    #
    # This was wrong in the first version. Commercial and creative anchored by
    # themselves, and an integration run promptly filled the board with generic
    # tech Product Manager postings. "Product Manager" is only interesting when
    # the product is a sequencer.
    anchored = bool(tiers_hit & {"core", "domain"})
    if not anchored and tiers_hit & {"role", "commercial", "creative"}:
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

    # Where you want to be. Ranking only; nothing is filtered on this.
    score += priority_bonus(job)[0]

    return score, sorted(set(hits))[:12]


def priority_bonus(job: dict) -> tuple[int, str]:
    """Bonus points and a label for the places she actually wants to work."""
    hay = " ".join([text_of(job, "location"), text_of(job, "region"),
                    text_of(job, "country_hint")]).lower()
    if not hay.strip():
        return 0, ""
    for name, spec in (SET.get("priority_locations") or {}).items():
        if any(m in hay for m in spec["markers"]):
            return spec["bonus"], name
    return 0, ""


# A title that names the kind of work settles it on its own. These are matched
# against the title only, and one hit is enough.
FLAVOUR_TITLES = {
    "commercial": ["application scientist", "applications specialist", "sales",
                   "account", "business development", "product", "commercial",
                   "customer", "client", "market", "partnerships"],
    "creative": ["illustrat", "design", "editor", "writer", "content",
                 "communicat", "multimedia", "producer", "photograph",
                 "exhibit", "storytell", "creative", "brand", "social media"],
    "computational": ["data analyst", "data scientist", "bioinformatic",
                      "computational", "software", "programmer", "analytics",
                      "machine learning", "statistic", "informatics", "data "],
    "bench": ["laboratory", "lab ", "bench", "technician", "assay",
              "molecular", "cell culture"],
    "field": ["field", "survey", "seasonal", "crew", "monitoring",
              "technician ii", "ranger"],
    "comms": ["educat", "outreach", "engagement", "instructor", "interpret",
              "curriculum", "training", "programme officer", "program officer"],
}


def flavours(job: dict) -> list[str]:
    """Which kinds of work this posting actually involves.

    Two signals. A title naming the kind of work is decisive on its own, since
    "Field Application Scientist" is a commercial role whatever the body says.
    Failing that, two or more cues in the body count. An earlier version used
    only the body rule, and both "Field Application Scientist" and "Marine Data
    Analyst" came out as "other", which defeated the whole point of the filter.
    """
    title = text_of(job, "title").lower()
    body = text_of(job, "description", 5000).lower()
    hay = title + " " + body

    out = []
    for name, cues in FLAVOURS.items():
        if any(t in title for t in FLAVOUR_TITLES.get(name, [])):
            out.append(name)
            continue
        if sum(1 for c in cues if re.search(c, hay)) >= 2:
            out.append(name)
    return out or ["other"]


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
    loc = text_of(job, "location").lower()
    geo = SET["geography"]
    base = "Remote" if any(m in loc for m in geo["remote_markers"]) else ""
    if _is_us(loc) or (not loc and job.get("country_hint") == "US"):
        return "US remote" if base else "US"
    if base:
        return "Remote"
    if not loc:
        # Say what is true. Calling this a region invites the visa scorer to
        # assert something it cannot know.
        return job.get("country_hint") or "Not stated"
    for token, label in (("bengaluru", "India"), ("bangalore", "India"),
                         ("hyderabad", "India"), ("mumbai", "India"),
                         ("pune", "India"), ("delhi", "India"),
                         ("gurugram", "India"), ("gurgaon", "India"),
                         ("noida", "India"), ("chennai", "India"),
                         ("kolkata", "India"), ("goa", "India"),
                         ("copenhagen", "Denmark"), ("københavn", "Denmark"),
                         ("greenland", "Denmark"), ("aarhus", "Denmark"),
                         ("united kingdom", "UK"), ("london", "UK"), ("england", "UK"),
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
    """Screen, score and label a posting. Returns None if it is dropped."""
    reason = excluded(job)
    if reason:
        job["_dropped"] = reason
        return None
    score, hits = relevance(job)
    from .freshness import trust
    floor = SET["run"]["min_relevance"]
    if trust(job.get("source", "")) == "low":
        floor = SET["run"]["min_relevance_lowtrust"]
    if score < floor:
        job["_dropped"] = f"below threshold ({score} < {floor})"
        return None
    job["relevance"] = score
    job["match_terms"] = hits
    job["role_type"] = role_type(job)
    job["region"] = region(job)
    bonus, where = priority_bonus(job)
    job["priority_place"] = where
    job["priority_bonus"] = bonus
    job["flavours"] = flavours(job)
    return job
