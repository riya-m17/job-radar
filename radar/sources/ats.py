"""Pull postings straight from employer career pages."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from ..util import get, load_config, log, session, settings, strip_html


def _iso(value) -> str | None:
    """Normalise the many date shapes these APIs return."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)):
            ts = value / 1000 if value > 1e11 else value
            return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).date().isoformat()
    except (ValueError, OSError, OverflowError):
        return str(value)[:10] or None


def _greenhouse(slug, sess):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    r = get(url, sess)
    if not r or r.status_code != 200:
        return []
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "description": strip_html(j.get("content", "")),
            # first_published is when the posting went live. updated_at moves
            # every time anyone edits it, so it overstates freshness badly.
            "posted": _iso(j.get("first_published") or j.get("updated_at")),
            "department": ", ".join(d.get("name", "") for d in j.get("departments", [])),
        })
    return out


def _lever(slug, sess):
    r = get(f"https://api.lever.co/v0/postings/{slug}?mode=json", sess)
    if not r or r.status_code != 200:
        return []
    out = []
    for j in r.json():
        cat = j.get("categories") or {}
        body = " ".join(filter(None, [
            j.get("descriptionPlain") or strip_html(j.get("description")),
            strip_html(j.get("additionalPlain") or j.get("additional")),
        ]))
        out.append({
            "title": j.get("text", ""),
            "location": cat.get("location", ""),
            "url": j.get("hostedUrl", ""),
            "description": body,
            "posted": _iso(j.get("createdAt")),
            "department": cat.get("team", "") or cat.get("department", ""),
        })
    return out


def _ashby(slug, sess):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    r = get(url, sess)
    if not r or r.status_code != 200:
        return []
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "title": j.get("title", ""),
            "location": j.get("location", "") or ", ".join(j.get("secondaryLocations", []) or []),
            "url": j.get("jobUrl", "") or j.get("applyUrl", ""),
            "description": strip_html(j.get("descriptionHtml")) or j.get("descriptionPlain", ""),
            "posted": _iso(j.get("publishedAt")),
            "department": j.get("department", "") or j.get("team", ""),
        })
    return out


def _workable(slug, sess):
    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"
    r = get(url, sess)
    if not r or r.status_code != 200:
        return []
    out = []
    for j in r.json().get("jobs", []):
        loc = ", ".join(filter(None, [j.get("city"), j.get("state"), j.get("country")]))
        out.append({
            "title": j.get("title", ""),
            "location": loc or ("Remote" if j.get("telecommuting") else ""),
            "url": j.get("url", "") or j.get("application_url", ""),
            "description": strip_html(j.get("description")) + " " + strip_html(j.get("requirements")),
            "posted": _iso(j.get("published_on") or j.get("created_at")),
            "department": j.get("department", ""),
        })
    return out


def _smartrecruiters(slug, sess):
    out, offset = [], 0
    while offset < 400:
        url = (f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
               f"?limit=100&offset={offset}")
        r = get(url, sess)
        if not r or r.status_code != 200:
            break
        payload = r.json()
        batch = payload.get("content", [])
        for j in batch:
            loc = j.get("location") or {}
            where = ", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")]))
            out.append({
                "title": j.get("name", ""),
                "location": where or ("Remote" if loc.get("remote") else ""),
                "url": f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}",
                "description": "",  # detail needs a second call; the title carries the signal
                "posted": _iso(j.get("releasedDate")),
                "department": (j.get("department") or {}).get("label", ""),
            })
        if len(batch) < 100:
            break
        offset += 100
    return out


def _recruitee(slug, sess):
    r = get(f"https://{slug}.recruitee.com/api/offers/", sess)
    if not r or r.status_code != 200:
        return []
    out = []
    for j in r.json().get("offers", []):
        out.append({
            "title": j.get("title", ""),
            "location": j.get("location", "") or j.get("city", ""),
            "url": j.get("careers_url", "") or j.get("careers_apply_url", ""),
            "description": strip_html(j.get("description")) + " " + strip_html(j.get("requirements")),
            "posted": _iso(j.get("published_at")),
            "department": j.get("department", ""),
        })
    return out


def _workday(slug, sess):
    raise RuntimeError("workday is dispatched on the board dict, not the slug")


FETCHERS = {
    "greenhouse": _greenhouse,
    "lever": _lever,
    "ashby": _ashby,
    "workable": _workable,
    "smartrecruiters": _smartrecruiters,
    "recruitee": _recruitee,
}


def _one(org: dict, board: dict) -> list[dict]:
    sess = session()
    try:
        if board["provider"] == "workday":
            from . import workday
            raw = workday.fetch(board)
        else:
            fetch = FETCHERS.get(board["provider"])
            if not fetch:
                return []
            raw = fetch(board["slug"], sess)
    except Exception as exc:
        log.warning("fetch failed %s: %s", org["name"], exc)
        return []
    for j in raw:
        j["company"] = org["name"]
        j["org_cat"] = org.get("cat", "aggregator")
        j["country_hint"] = org.get("country", "")
        j["cap_exempt"] = bool(org.get("cap_exempt"))
        j["source"] = board["provider"]
    return raw


def harvest(boards: dict) -> list[dict]:
    orgs = load_config("organizations")["organizations"]
    pairs = [(o, boards.get(o["name"])) for o in orgs]
    pairs = [(o, b) for o, b in pairs if b]
    log.info("harvesting %d employer boards", len(pairs))

    jobs: list[dict] = []
    with ThreadPoolExecutor(max_workers=settings()["run"]["max_workers"]) as pool:
        futures = [pool.submit(_one, o, b) for o, b in pairs]
        for fut in as_completed(futures):
            try:
                jobs.extend(fut.result())
            except Exception as exc:
                log.warning("harvest worker failed: %s", exc)
    log.info("employer boards returned %d raw postings", len(jobs))
    return jobs
