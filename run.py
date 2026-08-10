#!/usr/bin/env python3
"""Job Radar. One command, one dashboard.

    python run.py                 normal daily run
    python run.py --rediscover    re-probe every employer career page
    python run.py --verbose       show what got dropped and why
    python run.py --digest        also write a plain text digest of new roles
"""

from __future__ import annotations

import argparse
import collections
from pathlib import Path

from radar import (classify, deadlines, discovery, freshness, profile_match,
                   programs, render, requirements, store, visa)
from radar.sources import ats, boards, feeds
from radar.util import ROOT, log, setup_logging, settings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rediscover", action="store_true",
                    help="re-probe every career page from scratch")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--digest", action="store_true",
                    help="write digest.md listing today's new openings")
    args = ap.parse_args()

    setup_logging(args.verbose)
    cfg = settings()["sources"]
    cfg_run = settings()["run"]

    # 1. Where does each employer post?
    boards_cache = discovery.run(force=args.rediscover) if cfg["ats"] else {}
    if cfg["ats"]:
        log.info("using %d verified employer boards", len(boards_cache))

    # 2. Collect everything.
    raw: list[dict] = []
    if cfg["ats"]:
        raw += ats.harvest(boards_cache)
    raw += feeds.harvest()
    if cfg["specialist_boards"]:
        raw += boards.harvest()
    log.info("collected %d raw postings before filtering", len(raw))

    # 3. Filter and score.
    kept, dropped = [], collections.Counter()
    for job in raw:
        if not job.get("title") or not job.get("url"):
            dropped["no title or link"] += 1
            continue
        result = classify.classify(job)
        if result is None:
            reason = job.get("_dropped", "unknown")
            dropped[reason.split(":")[0]] += 1
            continue
        result.update(visa.assess(result))

        # You cannot apply to these, so they are removed rather than sorted
        # to the bottom where they still take up space.
        if cfg_run["drop_blocked"] and result["visa_status"] == "blocked":
            dropped["needs citizenship or clearance"] += 1
            continue

        result.update(freshness.assess(result))
        if freshness.too_old(result):
            dropped["older than %dd" % cfg_run["max_age_days"]] += 1
            continue

        result.update(requirements.assess(result))
        why = requirements.rejected(result)
        if why:
            dropped[why.split("(")[0].strip()] += 1
            continue

        if (cfg_run.get("exclude_internships")
                and result["role_type"] in ("internship", "seasonal")):
            dropped["internship or seasonal, not a job"] += 1
            continue

        result.update(deadlines.assess(result))
        result.update(profile_match.assess(result))
        # Ranking combines topic relevance with how much of the posting she can
        # actually already do. The two are shown separately on the dashboard.
        result["total_score"] = result["relevance"] + result["skill_score"]
        kept.append(result)

    log.info("kept %d postings", len(kept))
    for reason, n in dropped.most_common(8):
        log.info("  dropped %5d  %s", n, reason)

    # 4. Remember, then publish.
    open_jobs, new_today = store.merge(kept)
    open_jobs.sort(key=lambda j: (-j.get("visa_rank", 3), -j.get("total_score", 0)))
    log.info("posted dates: %d exact, %d approximate, %d unknown",
             sum(1 for j in open_jobs if j.get("posted_confidence") == "exact"),
             sum(1 for j in open_jobs if j.get("posted_confidence") == "approximate"),
             sum(1 for j in open_jobs if j.get("posted_confidence") == "unknown"))
    log.info("deadlines: %d stated, %d rolling, %d closing within 14d",
             sum(1 for j in open_jobs if j.get("closes_kind") == "stated"),
             sum(1 for j in open_jobs if j.get("closes_kind") == "rolling"),
             sum(1 for j in open_jobs if j.get("closing_soon")))
    for place in ("west_coast", "copenhagen", "india"):
        n = sum(1 for j in open_jobs if j.get("priority_place") == place)
        log.info("  %-12s %d openings", place, n)
    calendar = programs.load()
    render.write(open_jobs, store.history(), calendar)
    log.info("calendar: %d programmes, %d need attention now",
             len(calendar), len(programs.act_now(calendar)))

    if args.digest:
        write_digest(new_today, calendar)

    log.info("done. open %s to look at it", settings()["output"]["dashboard"])


def write_digest(new_today: list[dict], calendar: list[dict] | None = None) -> None:
    """A short markdown summary, used as the body of the daily GitHub issue."""
    path = ROOT / "digest.md"
    head = []
    urgent = programs.act_now(calendar or [], limit=4)
    if urgent:
        head.append("### Deadlines first")
        for p in urgent:
            when = ("closes in %dd" % p["days"] if p["state"] in ("closing", "open")
                    else "opens in %dw" % max(1, round(p["days"] / 7)))
            head.append(f"- [{p['name']}]({p['url']}) at {p['org']}, {when}")
        head.append("")

    if not new_today:
        path.write_text("\n".join(head + ["No new openings today."]) + "\n",
                        encoding="utf-8")
        return

    new_today.sort(key=lambda j: (-j.get("visa_rank", 3), -j.get("total_score", 0)))
    lines = head + [f"{len(new_today)} new openings today.", ""]
    by_cat: dict[str, list[dict]] = collections.defaultdict(list)
    for j in new_today:
        by_cat[j.get("org_cat", "other")].append(j)

    labels = render.CATEGORIES
    for cat, rows in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"### {labels.get(cat, cat)}")
        for j in rows[:25]:
            flags = []
            if j.get("cap_exempt"):
                flags.append("cap exempt")
            if j.get("visa_status") in ("explicit", "likely"):
                flags.append(f"F-1 {j['visa_status']}")
            if j.get("already_contacted"):
                flags.append("already contacted")
            if j.get("has_signature"):
                flags.insert(0, "your niche")
            tail = f" _{', '.join(flags)}_" if flags else ""
            where = j.get("location") or j.get("region") or ""
            lines.append(f"- [{j['title']}]({j['url']}) at {j['company']}"
                         f"{', ' + where if where else ''}{tail}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote digest.md")


if __name__ == "__main__":
    main()
