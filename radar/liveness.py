"""Check that a posting still exists before showing it.

The complaint that killed the last version's credibility: clicking through to
roles that had already closed. Three separate causes, and they need different
treatment.

  The employer pulled it. It vanishes from their board feed, so absence is the
  signal. Handled in store.py, and the threshold is now two consecutive misses
  rather than three, because a day of lag is tolerable and a week is not.

  A syndicated feed kept a stale copy. RSS boards and aggregators routinely
  serve items whose underlying posting is long gone, and no amount of waiting
  fixes that because the feed keeps asserting it exists. The only way to know
  is to fetch the link.

  The link redirects to a generic careers index. Technically a 200 response,
  actually a dead posting. Greenhouse, Lever and Workday all do this once a
  requisition closes, so the status code alone is not enough.

So: fetch the URL, follow redirects, and judge both the status and where it
landed. Results are cached with a timestamp, since re-checking every posting
every morning is wasteful and rude to the servers.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

from .util import ROOT, log, session, settings

CACHE = ROOT / "data" / "link_status.json"

# Re-check a posting known to be alive this often. Employers close roles
# quietly, so a live result goes stale quickly.
RECHECK_ALIVE_DAYS = 3

# Text that means the posting is gone even though the server said 200.
GONE_MARKERS = [
    "no longer accepting applications",
    "this job is no longer available",
    "this position is no longer available",
    "this posting is no longer available",
    "the job you are looking for is no longer",
    "position has been filled",
    "job has been filled",
    "this requisition is closed",
    "applications are closed",
    "no longer open",
    "posting has expired",
    "job expired",
    "we are no longer accepting",
    "page not found",
    "404 not found",
    "job not found",
    "opportunity is no longer",
]

# A URL that ends up here is an index page, not a posting.
INDEX_PATTERNS = [
    re.compile(r"/(jobs|careers|opportunities|openings|vacancies)/?$", re.I),
    re.compile(r"/(job-search|search|all-jobs|current-openings)/?$", re.I),
    re.compile(r"^https?://[^/]+/?$"),               # bare domain
]


def _read() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def _write(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")


def _looks_like_index(url: str) -> bool:
    return any(p.search(url) for p in INDEX_PATTERNS)


def check(url: str) -> dict:
    """Fetch a posting URL and decide whether it is still a live posting."""
    sess = session()
    try:
        r = sess.get(url, timeout=settings()["run"]["timeout_seconds"],
                     allow_redirects=True)
    except Exception as exc:
        # A network failure is not evidence the posting is gone.
        return {"state": "unknown", "reason": f"fetch failed: {type(exc).__name__}"}

    if r.status_code in (404, 410):
        return {"state": "dead", "reason": f"HTTP {r.status_code}"}
    if r.status_code in (403, 429):
        # Bot protection. Says nothing about the posting.
        return {"state": "unknown", "reason": f"HTTP {r.status_code}, blocked"}
    if r.status_code >= 500:
        return {"state": "unknown", "reason": f"HTTP {r.status_code}, server error"}
    if r.status_code != 200:
        return {"state": "unknown", "reason": f"HTTP {r.status_code}"}

    final = str(r.url)
    if _looks_like_index(final) and final.rstrip("/") != url.rstrip("/"):
        return {"state": "dead",
                "reason": "redirected to a careers index, so the posting is closed"}

    body = (r.text or "")[:60000].lower()
    for marker in GONE_MARKERS:
        if marker in body:
            return {"state": "dead", "reason": f"page says: {marker}"}

    return {"state": "alive", "reason": "posting still reachable"}


def _needs_check(url: str, cache: dict, aggressive: bool) -> bool:
    entry = cache.get(url)
    if not entry:
        return True
    if entry.get("state") == "dead":
        return False                     # settled, no need to re-fetch
    when = entry.get("checked")
    if not when:
        return True
    try:
        age = date.today() - date.fromisoformat(when)
    except ValueError:
        return True
    limit = 0 if aggressive else RECHECK_ALIVE_DAYS
    return age > timedelta(days=limit)


def verify(jobs: list[dict], aggressive: bool = False) -> tuple[list[dict], int]:
    """Drop postings whose links are provably dead. Returns (kept, dropped)."""
    if not settings()["run"].get("verify_links", True):
        return jobs, 0

    cache = _read()
    today = date.today().isoformat()
    todo = [j for j in jobs if _needs_check(j.get("url", ""), cache, aggressive)]

    if todo:
        log.info("verifying %d posting links", len(todo))
        with ThreadPoolExecutor(max_workers=settings()["run"]["max_workers"]) as pool:
            futures = {pool.submit(check, j["url"]): j for j in todo}
            for fut in as_completed(futures):
                job = futures[fut]
                try:
                    result = fut.result()
                except Exception as exc:
                    result = {"state": "unknown", "reason": str(exc)[:80]}
                result["checked"] = today
                cache[job["url"]] = result

    # Forget entries for postings no longer in the feed at all.
    urls = {j.get("url") for j in jobs}
    for gone in [u for u in cache if u not in urls]:
        del cache[gone]
    _write(cache)

    kept, dropped = [], 0
    for job in jobs:
        entry = cache.get(job.get("url", ""), {})
        state = entry.get("state", "unknown")
        if state == "dead":
            dropped += 1
            continue
        job["link_state"] = state
        job["link_checked"] = entry.get("checked")
        kept.append(job)

    alive = sum(1 for j in kept if j.get("link_state") == "alive")
    log.info("links: %d verified live, %d unverifiable, %d dead and removed",
             alive, len(kept) - alive, dropped)
    return kept, dropped
