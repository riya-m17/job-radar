"""Work out which applicant tracking system each organization publishes on.

Instead of hard coding board URLs that rot, this probes the public endpoints
of the six systems that between them cover most biotech, nonprofit and
research employers, then caches the answer in data/boards.json. Re-run it
weekly; the daily harvest just reads the cache.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .util import ROOT, get, load_config, log, session, settings, slug_candidates

CACHE = ROOT / "data" / "boards.json"

# Each probe returns True when the slug is a live board with a jobs list.
PROBES = {
    "greenhouse": lambda s: (
        f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
        lambda d: isinstance(d, dict) and isinstance(d.get("jobs"), list),
    ),
    "lever": lambda s: (
        f"https://api.lever.co/v0/postings/{s}?mode=json",
        lambda d: isinstance(d, list),
    ),
    "ashby": lambda s: (
        f"https://api.ashbyhq.com/posting-api/job-board/{s}",
        lambda d: isinstance(d, dict) and isinstance(d.get("jobs"), list),
    ),
    "smartrecruiters": lambda s: (
        f"https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=1",
        lambda d: isinstance(d, dict) and "content" in d,
    ),
    "workable": lambda s: (
        f"https://apply.workable.com/api/v1/widget/accounts/{s}?details=true",
        lambda d: isinstance(d, dict) and isinstance(d.get("jobs"), list),
    ),
    "recruitee": lambda s: (
        f"https://{s}.recruitee.com/api/offers/",
        lambda d: isinstance(d, dict) and isinstance(d.get("offers"), list),
    ),
}

# Order matters: the systems most common among these employers come first so
# most organizations resolve in one or two requests.
ORDER = ["greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee"]


def _probe(provider: str, slug: str, sess) -> bool:
    url, check = PROBES[provider](slug)
    r = get(url, sess)
    if r is None or r.status_code != 200:
        return False
    try:
        return bool(check(r.json()))
    except ValueError:
        return False


def resolve_one(org: dict) -> dict | None:
    sess = session()
    slugs = slug_candidates(org["name"], org.get("hints"))
    for slug in slugs[:6]:
        for provider in ORDER:
            try:
                if _probe(provider, slug, sess):
                    log.info("resolved %-46s -> %s/%s", org["name"], provider, slug)
                    return {"provider": provider, "slug": slug}
            except Exception as exc:  # a bad board should never stop the run
                log.debug("probe error %s %s %s: %s", org["name"], provider, slug, exc)
    log.debug("unresolved %s", org["name"])
    return None


def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")


def run(force: bool = False) -> dict:
    orgs = load_config("organizations")["organizations"]
    cache = {} if force else load_cache()
    todo = [o for o in orgs if o["name"] not in cache]
    if not todo:
        log.info("board cache complete (%d organizations)", len(cache))
        return cache

    log.info("resolving boards for %d organizations", len(todo))
    workers = settings()["run"]["max_workers"]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(resolve_one, o): o for o in todo}
        for fut in as_completed(futures):
            org = futures[fut]
            try:
                found = fut.result()
            except Exception as exc:
                log.warning("discovery crashed for %s: %s", org["name"], exc)
                found = None
            cache[org["name"]] = found  # None is a real answer: stop retrying daily

    save_cache(cache)
    hit = sum(1 for v in cache.values() if v)
    log.info("boards resolved: %d of %d organizations", hit, len(cache))
    return cache
