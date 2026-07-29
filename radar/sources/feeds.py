"""Job feeds that are not tied to one employer.

Everything here degrades quietly. A feed that is down, rate limited or missing
its API key logs a line and returns nothing, so the run always finishes.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from ..util import get, log, post, session, settings, strip_html


def _base(title, company, location, url, desc, posted, source, cat="aggregator"):
    return {
        "title": title or "",
        "company": company or "",
        "location": location or "",
        "url": url or "",
        "description": strip_html(desc)[:6000],
        "posted": posted,
        "source": source,
        "org_cat": cat,
        "country_hint": "",
        "cap_exempt": False,
        "department": "",
    }


# --------------------------------------------------------------------------- 
def remotive() -> list[dict]:
    out = []
    for q in ("biology", "bioinformatics", "data analyst", "research",
              "science", "environmental", "sustainability"):
        r = get(f"https://remotive.com/api/remote-jobs?search={q}&limit=100", session())
        if not r or r.status_code != 200:
            continue
        for j in r.json().get("jobs", []):
            out.append(_base(
                j.get("title"), j.get("company_name"),
                j.get("candidate_required_location") or "Remote",
                j.get("url"), j.get("description"),
                (j.get("publication_date") or "")[:10], "remotive"))
    log.info("remotive: %d", len(out))
    return out


def arbeitnow() -> list[dict]:
    out, page = [], 1
    sess = session()
    while page <= 8:
        r = get(f"https://www.arbeitnow.com/api/job-board-api?page={page}", sess)
        if not r or r.status_code != 200:
            break
        data = r.json().get("data", [])
        if not data:
            break
        for j in data:
            posted = j.get("created_at")
            if isinstance(posted, (int, float)):
                posted = datetime.fromtimestamp(posted, timezone.utc).date().isoformat()
            out.append(_base(
                j.get("title"), j.get("company_name"), j.get("location"),
                j.get("url"), j.get("description"), posted, "arbeitnow"))
        page += 1
    log.info("arbeitnow: %d", len(out))
    return out


def himalayas() -> list[dict]:
    out = []
    r = get("https://himalayas.app/jobs/api?limit=500", session())
    if r and r.status_code == 200:
        try:
            for j in r.json().get("jobs", []):
                locs = j.get("locationRestrictions") or []
                out.append(_base(
                    j.get("title"), j.get("companyName"),
                    ", ".join(locs) if locs else "Remote",
                    j.get("applicationLink") or j.get("guid"),
                    j.get("description"),
                    (j.get("pubDate") or "")[:10] if isinstance(j.get("pubDate"), str) else None,
                    "himalayas"))
        except ValueError:
            pass
    log.info("himalayas: %d", len(out))
    return out


def simplify_lists() -> list[dict]:
    """Two community-maintained GitHub lists of new grad and intern roles.

    Heavily tech weighted, so most rows get filtered out later, but they catch
    the data analyst and research analyst openings at large employers that
    never show up on a biology board.
    """
    urls = [
        ("https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/"
         "dev/.github/scripts/listings.json", "simplify-newgrad"),
        ("https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/"
         "dev/.github/scripts/listings.json", "simplify-intern"),
    ]
    out = []
    for url, tag in urls:
        r = get(url, session())
        if not r or r.status_code != 200:
            continue
        try:
            rows = r.json()
        except ValueError:
            continue
        for j in rows:
            if not j.get("active") or not j.get("is_visible", True):
                continue
            posted = j.get("date_posted")
            if isinstance(posted, (int, float)):
                posted = datetime.fromtimestamp(posted, timezone.utc).date().isoformat()
            item = _base(
                j.get("title"), j.get("company_name"),
                "; ".join(j.get("locations") or []),
                j.get("url"), "", posted, tag)
            # This feed states sponsorship outright. Carry it through.
            item["sponsorship_declared"] = j.get("sponsorship")
            out.append(item)
    log.info("simplify lists: %d active", len(out))
    return out


# --------------------------------------------------------------------------- 
def adzuna() -> list[dict]:
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        log.info("adzuna: skipped, no API key set")
        return []
    cfg = settings()["adzuna"]
    out, sess = [], session()
    for country in cfg["countries"]:
        for q in cfg["queries"]:
            url = (f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
                   f"?app_id={app_id}&app_key={app_key}&results_per_page=50"
                   f"&what={q.replace(' ', '%20')}&content-type=application/json")
            r = get(url, sess)
            if not r or r.status_code != 200:
                continue
            for j in r.json().get("results", []):
                out.append(_base(
                    j.get("title"),
                    (j.get("company") or {}).get("display_name"),
                    (j.get("location") or {}).get("display_name"),
                    j.get("redirect_url"), j.get("description"),
                    (j.get("created") or "")[:10], "adzuna"))
    log.info("adzuna: %d", len(out))
    return out


def usajobs() -> list[dict]:
    key = os.getenv("USAJOBS_KEY")
    email = os.getenv("USAJOBS_EMAIL")
    if not (key and email):
        log.info("usajobs: skipped, no API key set")
        return []
    sess = session()
    sess.headers.update({"Host": "data.usajobs.gov",
                         "User-Agent": email,
                         "Authorization-Key": key})
    out = []
    for kw in settings()["usajobs"]["keywords"]:
        url = (f"https://data.usajobs.gov/api/search?Keyword={kw.replace(' ', '%20')}"
               f"&ResultsPerPage=100&WhoMayApply=All")
        r = get(url, sess)
        if not r or r.status_code != 200:
            continue
        items = r.json().get("SearchResult", {}).get("SearchResultItems", [])
        for it in items:
            d = it.get("MatchedObjectDescriptor", {})
            locs = "; ".join(l.get("LocationName", "") for l in d.get("PositionLocation", [])[:3])
            summary = (d.get("UserArea", {}).get("Details", {}) or {})
            out.append(_base(
                d.get("PositionTitle"), d.get("OrganizationName"), locs,
                d.get("PositionURI"),
                " ".join([d.get("QualificationSummary") or "",
                          summary.get("JobSummary") or "",
                          " ".join(summary.get("KeyRequirements") or [])]),
                (d.get("PublicationStartDate") or "")[:10], "usajobs"))
    log.info("usajobs: %d", len(out))
    return out


# --------------------------------------------------------------------------- 
ALL = {
    "remotive": remotive,
    "arbeitnow": arbeitnow,
    "himalayas": himalayas,
    "simplify_newgrad": simplify_lists,
    "adzuna": adzuna,
    "usajobs": usajobs,
}


def harvest() -> list[dict]:
    toggles = settings()["sources"]
    jobs: list[dict] = []
    for name, fn in ALL.items():
        if not toggles.get(name, False):
            continue
        try:
            jobs.extend(fn())
        except Exception as exc:
            log.warning("feed %s failed: %s", name, exc)
    return jobs
