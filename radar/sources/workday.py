"""Workday.

Most of the best employers in the categories Riya cares about run Workday:
WHOI, large NGOs, hospital systems, big pharma, many museums and universities.
None of them were reachable before, because the first six providers I built for
are the startup and mid-market systems. That is the single biggest reason marine
and conservation coverage was thin.

Workday has no documented public API, but every tenant exposes the same JSON
endpoint that its own careers page uses:

    POST https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    {"limit": 20, "offset": 0, "searchText": ""}

Discovery is harder than for the others because a tenant needs three unknowns:
the tenant name, the data centre number, and the site name. Verified tenants go
in the registry under a `workday` key. For everything else the prober tries the
common patterns, which is a few dozen requests per employer but only runs when
an employer is otherwise unresolved.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..util import log, post, session, strip_html

WD_NUMBERS = [1, 2, 3, 5, 12, 10, 103]
SITE_PATTERNS = [
    "External", "{t}_External", "{t}-External", "careers", "Careers",
    "{t}_Careers", "External_Career_Site", "ExternalCareerSite",
    "{t}Careers", "Search", "{t}_External_Career_Site",
]


def endpoint(tenant: str, wd: int, site: str) -> str:
    return (f"https://{tenant}.wd{wd}.myworkdayjobs.com"
            f"/wday/cxs/{tenant}/{site}/jobs")


def _try(tenant: str, wd: int, site: str, sess) -> int | None:
    """Return the posting count if this is a real Workday board."""
    r = post(endpoint(tenant, wd, site), sess,
             json={"limit": 20, "offset": 0, "searchText": ""},
             headers={"Content-Type": "application/json",
                      "Accept": "application/json"})
    if r is None or r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if not isinstance(data, dict) or "jobPostings" not in data:
        return None
    return int(data.get("total") or len(data.get("jobPostings") or []))


def discover(org: dict) -> dict | None:
    """Find an employer's Workday tenant, or None."""
    sess = session()
    hint = org.get("workday")
    if hint:
        # Verified in the registry: {tenant, wd, site}
        count = _try(hint["tenant"], int(hint["wd"]), hint["site"], sess)
        if count is not None:
            return {"provider": "workday", "slug": hint["tenant"],
                    "workday": hint, "posting_count": count,
                    "verified_on": date.today().isoformat()}

    from ..util import slug_candidates
    for tenant in slug_candidates(org["name"], org.get("hints"))[:3]:
        for wd in WD_NUMBERS:
            for pattern in SITE_PATTERNS:
                site = pattern.format(t=tenant)
                try:
                    count = _try(tenant, wd, site, sess)
                except Exception:
                    continue
                if count is not None:
                    log.info("resolved %-44s -> workday/%s wd%d/%s (%d live)",
                             org["name"], tenant, wd, site, count)
                    return {"provider": "workday", "slug": tenant,
                            "workday": {"tenant": tenant, "wd": wd, "site": site},
                            "posting_count": count,
                            "verified_on": date.today().isoformat()}
    return None


def _posted_from_relative(text: str) -> str | None:
    """Workday publishes "Posted 5 Days Ago" rather than a date."""
    if not text:
        return None
    low = text.lower()
    today = date.today()
    if "today" in low:
        return today.isoformat()
    if "yesterday" in low:
        return (today - timedelta(days=1)).isoformat()
    digits = "".join(c for c in low if c.isdigit())
    if not digits:
        return None
    n = int(digits)
    if "day" in low:
        return (today - timedelta(days=n)).isoformat()
    if "week" in low:
        return (today - timedelta(weeks=n)).isoformat()
    if "month" in low:
        return (today - timedelta(days=30 * n)).isoformat()
    if "year" in low:
        return (today - timedelta(days=365 * n)).isoformat()
    return None


def fetch(board: dict) -> list[dict]:
    wd = board.get("workday") or {}
    if not wd:
        return []
    tenant, num, site = wd["tenant"], int(wd["wd"]), wd["site"]
    sess = session()
    base = f"https://{tenant}.wd{num}.myworkdayjobs.com"
    out, offset = [], 0

    while offset < 400:
        r = post(endpoint(tenant, num, site), sess,
                 json={"limit": 20, "offset": offset, "searchText": ""},
                 headers={"Content-Type": "application/json",
                          "Accept": "application/json"})
        if r is None or r.status_code != 200:
            break
        try:
            data = r.json()
        except ValueError:
            break
        batch = data.get("jobPostings") or []
        if not batch:
            break

        for j in batch:
            path = j.get("externalPath") or ""
            out.append({
                "title": j.get("title", ""),
                "location": j.get("locationsText", "") or "",
                # externalPath is the per-posting route, which is what makes
                # these real links rather than a shared board URL.
                "url": f"{base}/{site}{path}" if path else f"{base}/{site}",
                "description": strip_html(j.get("jobDescription", "")),
                "posted": _posted_from_relative(j.get("postedOn", "")),
                "department": j.get("jobFamily", "") or "",
                "req_id": j.get("bulletFields", [None])[0] if j.get("bulletFields") else None,
            })
        offset += 20
        if len(batch) < 20:
            break
    return out
