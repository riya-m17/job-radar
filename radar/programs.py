"""Turn the programme calendar into something with urgency attached."""

from __future__ import annotations

from datetime import date

from .util import load_config


def _next_occurrence(month: int, today: date) -> date:
    """The next time this month comes around, counting this month as now."""
    year = today.year if month >= today.month else today.year + 1
    return date(year, month, 1)


def _window(opens: int, closes: int, today: date) -> tuple[str, int, date]:
    """Work out where today sits relative to an annual window.

    Returns (state, days, reference_date) where state is one of
    open, closing, upcoming, or year_round.
    """
    if opens == 1 and closes == 12:
        return "year_round", 0, today

    month = today.month
    wraps = closes < opens

    if wraps:
        inside = month >= opens or month <= closes
    else:
        inside = opens <= month <= closes

    if inside:
        # Close date is the first of the month after the closing month.
        end_month = closes % 12 + 1
        end_year = today.year
        if wraps and month >= opens:
            end_year = today.year + 1
        elif end_month <= month:
            end_year = today.year + 1
        end = date(end_year, end_month, 1)
        days = (end - today).days
        return ("closing" if days <= 30 else "open"), days, end

    start = _next_occurrence(opens, today)
    return "upcoming", (start - today).days, start


def load() -> list[dict]:
    today = date.today()
    out = []
    for p in load_config("programs")["programs"]:
        item = dict(p)
        status = item.get("status", "unverified")

        # A verified exact deadline beats a guessed month window every time.
        exact = None
        if item.get("deadline"):
            try:
                exact = date.fromisoformat(str(item["deadline"]))
            except ValueError:
                exact = None

        if exact and exact >= today:
            days = (exact - today).days
            state = "closing" if days <= 30 else "open"
            ref = exact
        else:
            state, days, ref = _window(int(p["opens"]), int(p["closes"]), today)

        # Something you cannot apply to has no urgency, whatever the date says.
        if status == "ineligible":
            state, days = "blocked", 0

        item["state"] = state
        item["days"] = days
        item["ref_date"] = ref.isoformat()
        item["status"] = status
        item["has_exact_deadline"] = bool(exact)
        # Sort key: things closing soonest first, then things opening soonest,
        # then rolling programmes, which have no urgency by definition.
        # Verified things you can act on first, then unverified, then the dead
        # ends, which sit at the bottom purely as a record.
        tier = {"eligible": 0, "unverified": 1, "ineligible": 2}.get(status, 1)
        # She wants jobs. A summer internship is not one, so it sorts below
        # anything that is a real position, however good the fit.
        is_job = 0 if item.get("type", "") not in ("internship", "seasonal") else 1
        item["is_job"] = not bool(is_job)
        item["urgency"] = tier * 10000000 + is_job * 1000000 + {
            "closing": 0,
            "open": 1,
            "upcoming": 2,
            "year_round": 3,
            "blocked": 4,
        }[state] * 10000 + days
        out.append(item)
    out.sort(key=lambda x: x["urgency"])
    return out


def act_now(programs: list[dict], limit: int = 6) -> list[dict]:
    """The ones where doing nothing this month has a real cost.

    Never surfaces anything verified ineligible. Putting a programme you
    cannot apply to at the top of a priority list is the exact failure this
    calendar was rebuilt to fix.
    """
    live = [p for p in programs
            if p.get("status") != "ineligible" and p.get("is_job", True)]
    picks = [p for p in live if p["state"] in ("closing", "open")]
    soon = [p for p in live if p["state"] == "upcoming" and p["days"] <= 60]
    return (picks + soon)[:limit]
