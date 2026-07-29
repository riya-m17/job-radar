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

from radar import classify, discovery, render, store, visa
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

    # 1. Where does each employer post?
    boards_cache = discovery.run(force=args.rediscover) if cfg["ats"] else {}

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
        kept.append(result)

    log.info("kept %d postings", len(kept))
    for reason, n in dropped.most_common(8):
        log.info("  dropped %5d  %s", n, reason)

    # 4. Remember, then publish.
    open_jobs, new_today = store.merge(kept)
    open_jobs.sort(key=lambda j: (-j.get("visa_rank", 3), -j.get("relevance", 0)))
    render.write(open_jobs, store.history())

    if args.digest:
        write_digest(new_today)

    log.info("done. open %s to look at it", settings()["output"]["dashboard"])


def write_digest(new_today: list[dict]) -> None:
    """A short markdown summary, used as the body of the daily GitHub issue."""
    path = ROOT / "digest.md"
    if not new_today:
        path.write_text("No new openings today.\n", encoding="utf-8")
        return

    new_today.sort(key=lambda j: (-j.get("visa_rank", 3), -j.get("relevance", 0)))
    lines = [f"{len(new_today)} new openings today.", ""]
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
            tail = f" _{', '.join(flags)}_" if flags else ""
            where = j.get("location") or j.get("region") or ""
            lines.append(f"- [{j['title']}]({j['url']}) at {j['company']}"
                         f"{', ' + where if where else ''}{tail}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote digest.md")


if __name__ == "__main__":
    main()
