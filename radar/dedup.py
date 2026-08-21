"""Job identity and deduplication.

The old identity was sha1(company, title, full_url). That is why the output was
full of repeats: the URL is not stable for a single requisition. Greenhouse
alone serves the same job from boards.greenhouse.io and job-boards.greenhouse.io,
tracking parameters get appended, and aggregators re-list the identical posting
under their own host. Every one of those produced a separate row.

Two layers now.

LAYER 1, exact. The primary key is (ats_system, company_slug, job_id), pulled
out of the URL by a per-provider pattern. Two records with the same requisition
id are the same job no matter which host served them or what query string was
attached. This is an upsert, so a job seen on twenty consecutive days is one row
with first_seen and last_seen, never twenty rows.

LAYER 2, fuzzy. What survives layer 1 is then collapsed on normalised
(company, title, location). This catches the same role posted through two
different systems, where there is no shared requisition id to key on. Title
normalisation handles the level-suffix problem: "Research Associate I/II",
"Research Associate II" and "Research Associate 2" are one posting.

What deliberately does NOT collapse: the same title at the same company in
genuinely different locations. Those are separate requisitions upstream and
applying to the right one matters.
"""

from __future__ import annotations

import hashlib
import re

from .util import log, text_of

# ---------------------------------------------------------------- job ids
# Each pattern pulls the stable requisition id out of a posting URL.
ID_PATTERNS = [
    ("greenhouse", re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([^/?&#]+)"
                              r".*?(?:jobs?/|gh_jid=)(\d+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/([^/?#]+)/jobs/(\d+)", re.I)),
    ("lever", re.compile(r"lever\.co/([^/?#]+)/([0-9a-f-]{8,})", re.I)),
    ("ashby", re.compile(r"ashbyhq\.com/([^/?#]+)/([0-9a-f-]{8,})", re.I)),
    ("workable", re.compile(r"([^./]+)\.workable\.com/(?:j|jobs)/([A-Z0-9]+)", re.I)),
    ("smartrecruiters", re.compile(r"smartrecruiters\.com/([^/?#]+)/(\d+)", re.I)),
    ("recruitee", re.compile(r"([^./]+)\.recruitee\.com/o/([^/?#]+)", re.I)),
    ("workday", re.compile(r"([^./]+)\.wd\d+\.myworkdayjobs\.com/.*?"
                           r"(?:/job/.*?)?(R-?\d{4,}|JR-?\d{4,})", re.I)),
    ("workday", re.compile(r"([^./]+)\.wd\d+\.myworkdayjobs\.com/([^?#]+)", re.I)),
]

# Query parameters that are tracking noise rather than identity.
TRACKING = re.compile(
    r"[?&](gh_src|gh_jid|utm_[a-z]+|src|source|ref|referrer|lever-source"
    r"|trackingTag|rx_[a-z]+|jobPipeline)=[^&#]*", re.I)


def clean_url(url: str) -> str:
    """Strip tracking noise and normalise the host so one job is one URL."""
    if not url:
        return ""
    u = url.strip()
    u = TRACKING.sub("", u)
    u = re.sub(r"[?&]+$", "", u)
    u = re.sub(r"#.*$", "", u)
    # Greenhouse serves identical requisitions from two hosts.
    u = u.replace("//job-boards.greenhouse.io", "//boards.greenhouse.io")
    u = u.replace("//boards-api.greenhouse.io/v1/boards", "//boards.greenhouse.io")
    u = re.sub(r"^https?://www\.", "https://", u)
    return u.rstrip("/")


def requisition(job: dict) -> tuple[str, str, str] | None:
    """Return (ats_system, company_slug, job_id), or None if not derivable."""
    url = clean_url(text_of(job, "url"))
    if not url:
        return None
    for system, pattern in ID_PATTERNS:
        m = pattern.search(url)
        if m and m.lastindex and m.lastindex >= 2:
            slug = (m.group(1) or "").lower()
            jid = (m.group(2) or "").lower()
            if slug and jid:
                return system, slug, jid
    return None


# ------------------------------------------------------------ normalising
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6}
LEGAL = re.compile(r"\b(inc|llc|ltd|plc|corp|corporation|company|co|the|group"
                   r"|holdings|aps|gmbh|ab|as|sa|nv|bv)\b", re.I)


def norm_company(name: str) -> str:
    n = (name or "").lower()
    n = LEGAL.sub(" ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


def norm_title(title: str) -> str:
    """Collapse level variants so one role is not three rows.

    "Research Associate I/II", "Research Associate II" and "Research
    Associate 2" all reduce to the same string. The level itself is dropped
    rather than kept, because a posting advertised as I/II is one requisition,
    and keeping the level would split it from its own re-listing.
    """
    t = (title or "").lower().strip()
    t = re.sub(r"\s*\([^)]*\)\s*", " ", t)          # trailing "(Remote)" etc
    t = re.sub(r"[-–—,]", " ", t)
    # Slash ranges: "associate i/ii", "scientist 1/2"
    t = re.sub(r"\b([ivx]+|\d)\s*/\s*([ivx]+|\d)\b", " ", t)
    # Trailing level markers
    t = re.sub(r"\b(level|lvl|grade)\s*[0-9ivx]+\b", " ", t)
    t = re.sub(r"\b([ivx]{1,3}|[1-9])\b\s*$", " ", t)
    t = re.sub(r"\b(sr|jr|senior|junior)\b", " ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def norm_location(loc: str) -> str:
    """Coarse location key. Distinct cities stay distinct requisitions."""
    l = (loc or "").lower()
    l = re.sub(r"\b(united states|usa|u\.s\.a?\.?|remote|hybrid|on ?site)\b", " ", l)
    l = re.sub(r"[^a-z ]+", " ", l)
    parts = [p for p in l.split() if len(p) > 1]
    return " ".join(sorted(set(parts)))[:60]


# Ranked by how much the source can be trusted to be the employer's own words.
SOURCE_RANK = {
    "greenhouse": 0, "lever": 0, "ashby": 0, "workable": 0,
    "smartrecruiters": 0, "recruitee": 0, "workday": 0,
    "schmidt-marine": 1, "climatebase": 1, "naturetech": 1,
    "wiseoceans": 1, "sevenseas": 1, "oceancareers": 1,
    "usajobs": 1, "reliefweb": 2, "adzuna": 2, "remotive": 2,
    "arbeitnow": 2, "himalayas": 2,
    "simplify-newgrad": 3, "simplify-intern": 3,
}


def _rank(job: dict) -> tuple:
    """Lower sorts better. Prefer employer boards, then richer records."""
    return (SOURCE_RANK.get(text_of(job, "source"), 4),
            0 if job.get("posted") else 1,
            -len(text_of(job, "description")))


def identity(job: dict) -> str:
    """The stable primary key for a posting."""
    req = requisition(job)
    if req:
        blob = "req|" + "|".join(req)
    else:
        blob = "alt|{}|{}|{}".format(
            norm_company(text_of(job, "company")),
            norm_title(text_of(job, "title")),
            clean_url(text_of(job, "url")))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def deduplicate(jobs: list[dict]) -> tuple[list[dict], dict]:
    """Two-layer dedup. Returns (unique jobs, stats)."""
    before = len(jobs)

    # Layer 1: exact requisition identity.
    exact: dict[str, dict] = {}
    for job in jobs:
        key = identity(job)
        job["key"] = key
        current = exact.get(key)
        if current is None or _rank(job) < _rank(current):
            if current is not None:
                job["also_seen_at"] = sorted(set(
                    current.get("also_seen_at", [])
                    + [text_of(current, "source")]))
            exact[key] = job
        else:
            current.setdefault("also_seen_at", [])
            src = text_of(job, "source")
            if src and src not in current["also_seen_at"]:
                current["also_seen_at"].append(src)
    after_exact = len(exact)

    # Layer 2: fuzzy collision on company + title + location.
    fuzzy: dict[tuple, dict] = {}
    for job in exact.values():
        fkey = (norm_company(text_of(job, "company")),
                norm_title(text_of(job, "title")),
                norm_location(text_of(job, "location")))
        # A posting with no company or title cannot be safely collapsed.
        if not fkey[0] or not fkey[1]:
            fuzzy[("_", id(job), "")] = job
            continue
        current = fuzzy.get(fkey)
        if current is None or _rank(job) < _rank(current):
            if current is not None:
                job.setdefault("also_seen_at", [])
                src = text_of(current, "source")
                if src and src not in job["also_seen_at"]:
                    job["also_seen_at"].append(src)
            fuzzy[fkey] = job
        else:
            current.setdefault("also_seen_at", [])
            src = text_of(job, "source")
            if src and src not in current["also_seen_at"]:
                current["also_seen_at"].append(src)

    unique = list(fuzzy.values())
    stats = {
        "before": before,
        "after_exact": after_exact,
        "after_fuzzy": len(unique),
        "removed_exact": before - after_exact,
        "removed_fuzzy": after_exact - len(unique),
        "removed_total": before - len(unique),
        "pct_duplicate": round(100 * (before - len(unique)) / before, 1) if before else 0.0,
    }
    log.info("dedup: %d raw -> %d after requisition key -> %d after fuzzy "
             "(%d removed, %.1f%% was duplication)",
             before, after_exact, len(unique),
             stats["removed_total"], stats["pct_duplicate"])
    return unique, stats
