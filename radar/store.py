"""Keep a memory across runs so the dashboard can say what is actually new."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .util import ROOT, job_key, log

DATA = ROOT / "data"
JOBS = DATA / "jobs.json"
HISTORY = DATA / "history.json"
OUTREACH = ROOT / "config" / "outreach_companies.txt"


def _read(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            log.warning("could not parse %s, starting fresh", path.name)
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")


def outreach_companies() -> set[str]:
    """Companies already in the outreach campaign, so the dashboard can say so.

    Drop one company name per line into config/outreach_companies.txt. You can
    paste the company column straight out of the outreach tracker.
    """
    if not OUTREACH.exists():
        return set()
    names = set()
    for line in OUTREACH.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"[^a-z0-9 ]", "", line.lower()).strip()
        if line and not line.startswith("#"):
            names.add(line)
    return names


def _norm_company(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()


def merge(fresh: list[dict]) -> tuple[list[dict], list[dict]]:
    """Fold today's harvest into the archive.

    Returns (all_open_jobs, newly_seen_today).
    """
    today = date.today().isoformat()
    archive = {j["key"]: j for j in _read(JOBS, [])}
    contacted = outreach_companies()

    seen_now = set()
    new_today = []

    for job in fresh:
        key = job_key(job.get("company", ""), job.get("title", ""), job.get("url", ""))
        job["key"] = key
        seen_now.add(key)

        company_norm = _norm_company(job.get("company"))
        job["already_contacted"] = any(
            company_norm == c or (len(c) > 4 and c in company_norm)
            for c in contacted
        )

        if key in archive:
            prior = archive[key]
            job["first_seen"] = prior.get("first_seen", today)
            job["applied"] = prior.get("applied", False)
            job["notes"] = prior.get("notes", "")
        else:
            job["first_seen"] = today
            job["applied"] = False
            job["notes"] = ""
            new_today.append(job)

        job["last_seen"] = today
        job["missed_runs"] = 0
        job["status"] = "open"
        archive[key] = job

    # Anything not seen this run edges toward closed.
    for key, job in archive.items():
        if key in seen_now:
            continue
        job["missed_runs"] = job.get("missed_runs", 0) + 1
        if job["missed_runs"] >= 3:
            job["status"] = "closed"

    merged = list(archive.values())
    _write(JOBS, merged)

    hist = _read(HISTORY, {})
    open_now = [j for j in merged if j.get("status") == "open"]
    hist[today] = {"open": len(open_now), "new": len(new_today)}
    _write(HISTORY, hist)

    log.info("archive: %d open, %d new today, %d total tracked",
             len(open_now), len(new_today), len(merged))
    return open_now, new_today


def history() -> dict:
    return _read(HISTORY, {})
