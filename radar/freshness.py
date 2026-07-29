"""How old is this posting, and how much do we trust that answer.

Applying to something that was filled two months ago wastes everybody's time,
so age is treated as a first class field rather than a detail. The awkward part
is that sources disagree about what a date means, and some publish none at all.
Three levels of confidence:

  exact        the employer's own system published a date. Greenhouse, Lever,
               Ashby, Workable, SmartRecruiters and Recruitee all do, and this
               is the date the posting went live.
  approximate  a feed published a date, but feeds re-date items when they
               re-syndicate, so treat it as roughly right.
  unknown      no date anywhere. Kept, because several conservation boards
               publish none and throwing them away would lose real openings,
               but flagged and never ranked as fresh.

Source trust is separate and coarser. An employer career page returns
structured fields and is worth believing. An RSS board returns a title and a
link, so a weak keyword match from one is almost always noise, and those have
to clear a higher relevance bar to survive at all.
"""

from __future__ import annotations

from datetime import date, datetime

from .util import settings

# Employer applicant tracking systems: structured, dated, believable.
HIGH_TRUST = {"greenhouse", "lever", "ashby", "workable",
              "smartrecruiters", "recruitee"}
# Aggregators: real data, but a layer removed from the employer.
MEDIUM_TRUST = {"remotive", "arbeitnow", "himalayas", "adzuna", "usajobs",
                "reliefweb", "simplify-newgrad", "simplify-intern"}
# Everything else is an RSS board, which is title and link only.


def trust(source: str) -> str:
    if source in HIGH_TRUST:
        return "high"
    if source in MEDIUM_TRUST:
        return "medium"
    return "low"


def confidence(job: dict) -> str:
    if not job.get("posted"):
        return "unknown"
    return "exact" if trust(job.get("source", "")) == "high" else "approximate"


def _parse(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def assess(job: dict) -> dict:
    cfg = settings()["run"]
    today = date.today()
    conf = confidence(job)
    posted = _parse(job.get("posted"))

    # A date in the future, or one implausibly far back, means the field is
    # being used for something other than the publication date. Distrust it.
    if posted and (posted > today or (today - posted).days > 3650):
        posted, conf = None, "unknown"

    if posted:
        age = (today - posted).days
    else:
        # Fall back on when we first saw it. That is a floor on the real age,
        # never an overestimate, so it can only make a posting look fresher
        # than it is, and the unknown flag says so on the row.
        first = _parse(job.get("first_seen")) or today
        age = (today - first).days

    if conf == "unknown":
        freshness = "undated"
    elif age <= 7:
        freshness = "this week"
    elif age <= cfg["stale_after_days"]:
        freshness = "recent"
    else:
        freshness = "ageing"

    return {
        "posted_date": posted.isoformat() if posted else None,
        "posted_confidence": conf,
        "age_days": age,
        "freshness": freshness,
        "source_trust": trust(job.get("source", "")),
    }


def too_old(job: dict) -> bool:
    """Only drop on a date we actually believe."""
    cfg = settings()["run"]
    if job.get("posted_confidence") == "unknown":
        return False
    return job.get("age_days", 0) > cfg["max_age_days"]
