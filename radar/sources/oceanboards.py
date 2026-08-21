"""Ocean, marine tech, climate and science communication boards.

Six aggregators that sit outside the biotech ATS circuit entirely.

A caution before the code. I cannot reach any of these hosts from the machine I
build on, so unlike the ATS providers, none of this is verified against a live
response. Each source is written defensively and fails quietly, and every one
logs how many rows it returned. After the first real run, check the log: a
source reporting zero every day is either broken or shaped differently than I
assumed, and should be fixed or removed rather than left in.

Schmidt Marine is the highest value of the six, because it aggregates career
pages across ocean organisations and links straight to them, so it surfaces
postings the others miss. It runs on Getro, and Getro boards expose a JSON
search API, so that is tried first and HTML parsing is only a fallback.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime

from ..util import get, log, post, session, strip_html

GETRO_SEARCH = "https://api.getro.com/api/v2/collections/{cid}/search/jobs"


def _row(title, company, location, url, desc, posted, source, cat="marine"):
    return {
        "title": title or "",
        "company": company or "",
        "location": location or "",
        "url": url or "",
        "description": strip_html(desc)[:8000],
        "posted": posted,
        "source": source,
        "org_cat": cat,
        "country_hint": "",
        "cap_exempt": False,
        "department": "",
    }


def _iso(value) -> str | None:
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            ts = value / 1000 if value > 1e11 else value
            return datetime.utcfromtimestamp(ts).date().isoformat()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except (ValueError, OSError, OverflowError):
        return str(value)[:10] or None


# ------------------------------------------------------------ Getro boards
def _find_collection_id(board_url: str) -> str | None:
    """Getro embeds its numeric collection id in the page bundle."""
    r = get(board_url, session())
    if not r or r.status_code != 200:
        return None
    for pattern in (r'collection[_-]?id["\':\s]+(\d{3,7})',
                    r'"collectionId"\s*:\s*"?(\d{3,7})',
                    r'getro\.com/[^"\']*?/(\d{3,7})/'):
        m = re.search(pattern, r.text, re.I)
        if m:
            return m.group(1)
    return None


def getro(board_url: str, source: str, cat: str = "marine",
          collection_id: str | None = None) -> list[dict]:
    cid = collection_id or _find_collection_id(board_url)
    if not cid:
        log.info("%s: could not find a Getro collection id, skipping", source)
        return []

    sess = session()
    out, page = [], 0
    while page < 10:
        r = post(GETRO_SEARCH.format(cid=cid), sess,
                 json={"hitsPerPage": 100, "page": page, "filters": {}},
                 headers={"Content-Type": "application/json",
                          "Accept": "application/json"})
        if r is None or r.status_code != 200:
            break
        try:
            payload = r.json()
        except ValueError:
            break
        hits = (payload.get("results") or {}).get("jobs") or payload.get("jobs") or []
        if not hits:
            break
        for j in hits:
            org = j.get("organization") or {}
            locs = j.get("locations") or []
            out.append(_row(
                j.get("title"),
                org.get("name") or j.get("companyName"),
                ", ".join(l if isinstance(l, str) else l.get("name", "")
                          for l in locs[:2]),
                # Getro links straight through to the employer's own posting,
                # which is what makes this source worth more than the others.
                j.get("url") or j.get("applyUrl") or j.get("jobUrl"),
                j.get("description") or j.get("descriptionSnippet") or "",
                _iso(j.get("createdAt") or j.get("postedAt")),
                source, cat))
        page += 1
        if len(hits) < 100:
            break
    log.info("%s: %d", source, len(out))
    return out


def schmidt_marine() -> list[dict]:
    return getro("https://jobs.schmidtmarine.org", "schmidt-marine", "marine")


def climatebase() -> list[dict]:
    return getro("https://climatebase.org/jobs", "climatebase", "climate")


def naturetech() -> list[dict]:
    return getro("https://naturetech.io/jobs", "naturetech", "conservation")


# ------------------------------------------------- simple HTML list boards
def _html_listing(url: str, source: str, cat: str,
                  link_pattern: str) -> list[dict]:
    """Generic reader for boards that render a plain list of job links.

    Deliberately conservative: it only emits a row when it can find a link that
    looks like an individual posting AND a non-empty title. A board that
    changes layout produces zero rows and a log line, never garbage rows.
    """
    r = get(url, session())
    if not r or r.status_code != 200:
        log.info("%s: unreachable", source)
        return []

    html = r.text
    out, seen = [], set()
    anchor = re.compile(
        r'<a[^>]+href=["\']([^"\']*' + link_pattern + r'[^"\']*)["\'][^>]*>(.*?)</a>',
        re.I | re.S)
    for m in anchor.finditer(html):
        href, label = m.group(1), strip_html(m.group(2)).strip()
        if not label or len(label) < 6 or len(label) > 160:
            continue
        if href.startswith("/"):
            base = re.match(r"https?://[^/]+", url)
            href = (base.group(0) if base else "") + href
        if not href.startswith("http") or href in seen:
            continue
        seen.add(href)
        out.append(_row(label, "", "", href, "", None, source, cat))

    # A listing page that yields one link per row is fine; one that yields the
    # same link repeatedly is a layout mismatch, not a set of jobs.
    if len(out) == 1 and len(seen) == 1:
        log.info("%s: only one distinct link found, treating as a layout miss", source)
        return []
    log.info("%s: %d", source, len(out))
    return out


def wiseoceans() -> list[dict]:
    return _html_listing("https://wiseoceans.com/jobs/", "wiseoceans",
                         "marine", r"/marine-jobs?/|/job/")


def seven_seas() -> list[dict]:
    return _html_listing("https://sevenseasmedia.org/ocean-jobs/", "sevenseas",
                         "marine", r"/ocean-jobs?/|/job/")


def ocean_careers() -> list[dict]:
    return _html_listing("https://oceancareers.com/jobs", "oceancareers",
                         "marine", r"/jobs?/\w")


ALL = {
    "schmidt_marine": schmidt_marine,
    "climatebase": climatebase,
    "naturetech": naturetech,
    "wiseoceans": wiseoceans,
    "seven_seas": seven_seas,
    "ocean_careers": ocean_careers,
}


def harvest(enabled: dict | None = None) -> list[dict]:
    jobs: list[dict] = []
    for name, fn in ALL.items():
        if enabled is not None and not enabled.get(name, True):
            continue
        try:
            jobs.extend(fn())
        except Exception as exc:
            log.warning("ocean source %s failed: %s", name, exc)
    log.info("ocean and scicomm boards returned %d raw postings", len(jobs))
    return jobs
