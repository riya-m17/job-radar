"""When does this close.

Almost no applicant tracking system exposes a closing date as a field, so for
most postings it has to be read out of the prose. Employers write it about
fifteen different ways, and the cost of a wrong answer is high in both
directions: invent a deadline and you panic over nothing, miss one and you find
out in November that it shut in September.

So the rule is to only report a deadline that is stated. Three outcomes:

  stated       a real date was found in the text or a structured field
  rolling      the posting says it reviews applications as they arrive, which
               means early is better and there is no cliff
  none         nothing said. Most postings. Reported as unknown, never guessed.

Nothing here infers a deadline from the posting date. A close date is only ever
something the employer wrote down.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .util import text_of

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# The phrases that mean a date nearby is a deadline rather than a start date,
# an interview date or the date the posting went up.
DEADLINE_CUES = [
    "deadline", "closing date", "closes on", "closes", "close date",
    "apply by", "applications due", "application due", "due by", "due date",
    "last date", "no later than", "must be received by", "submit by",
    "applications close", "application closes", "open until",
    "accepted until", "received by", "expires", "expiry",
    "final date", "cut-off", "cutoff",
]

ROLLING_CUES = [
    "rolling basis", "on a rolling", "reviewed as they are received",
    "reviewed as received", "until filled", "until the position is filled",
    "until a suitable candidate", "ongoing basis", "continuous recruitment",
    "applications are reviewed continuously", "review applications as they",
    "early application is encouraged", "apply early",
    "we review applications on an ongoing",
]

# 15 January 2027 / January 15, 2027 / 15 Jan 27
_TEXT_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")\.?\s*,?\s*(\d{4}|\d{2})?\b"
    r"|\b(" + "|".join(MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4}|\d{2})?\b",
    re.I)
# 2027-01-15 and 15/01/2027 and 01/15/2027
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")


def _year(token: str | None, month: int, today: date) -> int:
    """Fill in a missing year the only sensible way: the next time it occurs."""
    if token:
        y = int(token)
        return y + 2000 if y < 100 else y
    return today.year if month >= today.month else today.year + 1


def _dates_in(window: str, today: date) -> list[date]:
    found = []

    for m in _ISO_DATE.finditer(window):
        try:
            found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass

    for m in _SLASH_DATE.finditer(window):
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = c + 2000 if c < 100 else c
        # Ambiguous. Try day/month first, which is how most of the world and
        # every European employer writes it, then fall back to month/day.
        for day, month in ((a, b), (b, a)):
            try:
                found.append(date(year, month, day))
                break
            except ValueError:
                continue

    for m in _TEXT_DATE.finditer(window):
        if m.group(2):                      # 15 January 2027
            day, month_name, yr = m.group(1), m.group(2), m.group(3)
        else:                               # January 15, 2027
            month_name, day, yr = m.group(4), m.group(5), m.group(6)
        month = MONTHS.get((month_name or "").lower().rstrip("."))
        if not month:
            continue
        try:
            found.append(date(_year(yr, month, today), month, int(day)))
        except ValueError:
            pass

    return found


def assess(job: dict) -> dict:
    today = date.today()
    text = " ".join([text_of(job, "description", 9000), text_of(job, "title")])
    low = text.lower()

    # A structured field beats anything parsed out of prose. ReliefWeb supplies
    # one, and it is authoritative.
    for key in ("closes", "closing_date", "deadline"):
        if job.get(key):
            try:
                d = datetime.fromisoformat(str(job[key])[:10]).date()
                if today <= d <= today + timedelta(days=730):
                    return _out("stated", d, today, "the posting publishes a closing date")
            except ValueError:
                pass

    best = None
    for cue in DEADLINE_CUES:
        start = 0
        while True:
            i = low.find(cue, start)
            if i == -1:
                break
            start = i + len(cue)
            # Look forward mostly: the date almost always follows the cue.
            window = text[max(0, i - 40):min(len(text), i + 160)]
            for d in _dates_in(window, today):
                # A deadline in the past is a stale posting, not a deadline, and
                # one more than two years out is a parse error.
                if today <= d <= today + timedelta(days=730):
                    if best is None or d < best:
                        best = d
    if best:
        return _out("stated", best, today, "a closing date is stated in the posting")

    for cue in ROLLING_CUES:
        if cue in low:
            return _out("rolling", None, today,
                        "reviewed on a rolling basis, so applying early matters "
                        "more than any deadline")

    return _out("none", None, today, "no closing date stated")


def _out(kind: str, closes: date | None, today: date, why: str) -> dict:
    days = (closes - today).days if closes else None
    return {
        "closes_date": closes.isoformat() if closes else None,
        "closes_kind": kind,
        "closes_in_days": days,
        "closes_reason": why,
        # Anything inside a fortnight is worth surfacing loudly.
        "closing_soon": bool(days is not None and days <= 14),
    }
