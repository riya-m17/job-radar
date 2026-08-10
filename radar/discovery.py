"""Work out which system each employer publishes on, and keep score.

This runs where the network is unrestricted, so it can do the verification I
cannot do by hand: probe every employer, remember what answered, and report
honestly on what did not.

Three things this handles that the first version got wrong.

  Transient failures are not death sentences. The old version cached a miss
  permanently, so one bad night removed an employer for good. Misses are now
  counted and retried, and only quarantined after repeated failures across
  separate runs.

  Failures are named and counted, not silently swallowed. The registry was
  written from my own knowledge and is certainly imperfect. The only evidence
  available about which entries are real is whether a live board answers, so
  that evidence is recorded and reported rather than discarded.

  Success is verified, not assumed. A resolved board is re-checked
  periodically, because employers migrate between systems and a stale cache
  quietly stops returning postings without ever erroring.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

from .util import ROOT, get, load_config, log, session, settings, slug_candidates

CACHE = ROOT / "data" / "boards.json"
REPORT = ROOT / "data" / "registry_health.json"

# Misses across this many separate runs before an employer is quarantined.
MISSES_BEFORE_QUARANTINE = 4
# Re-verify a resolved board this often, since employers change systems.
REVERIFY_AFTER_DAYS = 30
# Retry a quarantined employer occasionally rather than never.
RETRY_QUARANTINED_AFTER_DAYS = 90

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
ORDER = ["greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee"]


def _probe(provider: str, slug: str, sess) -> int | None:
    """Return the number of postings on that board, or None if it is not one."""
    url, check = PROBES[provider](slug)
    r = get(url, sess)
    if r is None or r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if not check(data):
        return None
    if isinstance(data, list):
        return len(data)
    for key in ("jobs", "offers", "content"):
        if isinstance(data.get(key), list):
            return len(data[key])
    return 0


def resolve_one(org: dict) -> dict | None:
    sess = session()
    for slug in slug_candidates(org["name"], org.get("hints"))[:6]:
        for provider in ORDER:
            try:
                count = _probe(provider, slug, sess)
            except Exception as exc:
                log.debug("probe error %s %s/%s: %s", org["name"], provider, slug, exc)
                continue
            if count is not None:
                log.info("resolved %-46s -> %s/%s (%d live)",
                         org["name"], provider, slug, count)
                return {"provider": provider, "slug": slug,
                        "posting_count": count,
                        "verified_on": date.today().isoformat()}
    return None


def load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except ValueError:
            log.warning("boards.json unreadable, rebuilding")
    return {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")


def _stale(entry: dict, days: int) -> bool:
    when = entry.get("verified_on") or entry.get("last_tried")
    if not when:
        return True
    try:
        return date.today() - date.fromisoformat(when) > timedelta(days=days)
    except ValueError:
        return True


def _needs_probe(name: str, cache: dict, force: bool) -> bool:
    if force or name not in cache:
        return True
    entry = cache[name] or {}
    state = entry.get("state", "resolved" if entry.get("provider") else "missing")
    if state == "resolved":
        return _stale(entry, REVERIFY_AFTER_DAYS)
    if state == "quarantined":
        return _stale(entry, RETRY_QUARANTINED_AFTER_DAYS)
    return True          # a plain miss is retried next run


def run(force: bool = False) -> dict:
    orgs = load_config("organizations")["organizations"]
    cache = {} if force else load_cache()
    today = date.today().isoformat()

    todo = [o for o in orgs if _needs_probe(o["name"], cache, force)]
    # Drop cache entries for employers no longer in the registry.
    known = {o["name"] for o in orgs}
    for gone in [k for k in cache if k not in known]:
        del cache[gone]

    if todo:
        log.info("probing %d of %d employers", len(todo), len(orgs))
        with ThreadPoolExecutor(max_workers=settings()["run"]["max_workers"]) as pool:
            futures = {pool.submit(resolve_one, o): o for o in todo}
            for fut in as_completed(futures):
                org = futures[fut]
                try:
                    found = fut.result()
                except Exception as exc:
                    log.warning("discovery crashed for %s: %s", org["name"], exc)
                    found = None

                prior = cache.get(org["name"]) or {}
                if found:
                    found["misses"] = 0
                    found["state"] = "resolved"
                    found["last_tried"] = today
                    cache[org["name"]] = found
                else:
                    misses = int(prior.get("misses", 0)) + 1
                    cache[org["name"]] = {
                        "state": ("quarantined" if misses >= MISSES_BEFORE_QUARANTINE
                                  else "missing"),
                        "misses": misses,
                        "last_tried": today,
                        # Keep whatever worked before, so a temporary outage
                        # does not lose a known good slug.
                        "provider": prior.get("provider"),
                        "slug": prior.get("slug"),
                    }
    else:
        log.info("board cache current, nothing to probe")

    save_cache(cache)
    report(orgs, cache)
    return {k: v for k, v in cache.items()
            if v and v.get("provider") and v.get("state") != "quarantined"}


def report(orgs: list[dict], cache: dict) -> None:
    """Write and log an honest account of registry coverage."""
    by_name = {o["name"]: o for o in orgs}
    resolved, missing, quarantined, empty = [], [], [], []

    for name, entry in cache.items():
        entry = entry or {}
        state = entry.get("state", "missing")
        if state == "quarantined":
            quarantined.append(name)
        elif entry.get("provider"):
            resolved.append(name)
            if entry.get("posting_count") == 0:
                empty.append(name)
        else:
            missing.append(name)

    def group(names):
        out = {}
        for n in names:
            cat = by_name.get(n, {}).get("cat", "?")
            out[cat] = out.get(cat, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "registry_size": len(orgs),
        "resolved": sorted(resolved),
        "resolved_but_no_open_roles": sorted(empty),
        "missing_retrying": sorted(missing),
        "quarantined_no_public_feed": sorted(quarantined),
        "coverage_by_category": group(resolved),
        "gaps_by_category": group(missing + quarantined),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    total = len(orgs)
    log.info("registry health: %d/%d resolved (%.0f%%), %d retrying, %d quarantined",
             len(resolved), total, 100 * len(resolved) / max(total, 1),
             len(missing), len(quarantined))
    if quarantined:
        log.info("quarantined after %d failed runs, no public feed found:",
                 MISSES_BEFORE_QUARANTINE)
        for n in sorted(quarantined):
            log.info("    %s", n)
    if missing:
        log.info("not resolved this run, will retry (%d): %s",
                 len(missing), ", ".join(sorted(missing)[:40]))
    log.info("full detail in data/registry_health.json")
