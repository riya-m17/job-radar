"""Specialist boards: conservation, ecology, museums, international NGOs.

These are the places where wildlife and conservation openings actually get
posted, and almost none of them have a modern API. Two strategies:

  1. ReliefWeb, which has a genuinely open and stable JSON API, and carries
     the international NGO and environment postings.
  2. A generic RSS reader pointed at a list of candidate feeds. Boards change
     their feed URLs from time to time; a dead feed is logged and skipped
     rather than breaking the run. Check the log occasionally and prune.
"""

from __future__ import annotations

from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from ..util import get, log, session, strip_html

# name -> feed url. Add your own; anything returning valid RSS or Atom works.
# RSS FEEDS: DELIBERATELY EMPTY.
#
# The first version listed seventeen conservation and science job boards here.
# When they were finally checked, the picture was bad:
#
#   Conservation Job Board offers email alerts, not RSS. Conservation Careers
#   sits behind a sign-in wall. Most of the other feed URLs were my guesses at
#   plausible addresses and simply did not exist.
#
#   Worse, the handful that did respond served site-wide feeds mixing articles
#   with jobs, and gave one shared link for every item rather than a link per
#   posting. That is why a single conservation URL appeared ten times under ten
#   different titles, and why the employer column showed the board's name
#   instead of the actual employer.
#
# An aggregator feed without a per-posting link and a real employer name cannot
# produce a usable row, so the list is empty rather than wrong. Conservation and
# marine coverage now comes from reading those employers' own career pages,
# including Workday, which is what WHOI and most large NGOs actually use.
#
# If you find a board with a genuine per-job feed, add it as (name, url) and the
# reader below will pick it up. The duplicate-link guard will reject it
# automatically if it turns out to share one URL across many items.
RSS_FEEDS: list[tuple[str, str]] = []

# ReliefWeb: international humanitarian, development and environment postings.
RELIEFWEB = "https://api.reliefweb.int/v1/jobs"
RELIEFWEB_QUERIES = [
    "environment conservation", "biodiversity", "climate data",
    "monitoring evaluation data", "research analyst", "marine",
    "wildlife", "public health data",
]


# Several of these sites publish one site-wide feed with articles, podcasts
# and jobs mixed together, so the feed alone is not evidence of a posting.
# Judge the link instead. This throws away some real postings whose urls do
# not say job anywhere, which is the right trade: employer career pages are
# the backbone and these feeds are a bonus.
BLOG_PATHS = ("/founders-desk/", "/blog/", "/news/", "/article", "/advice",
              "/guide", "/podcast", "/webinar", "/course", "/story", "/tips",
              "/opinion", "/interview", "/press-", "/event", "/resources/",
              "/how-to", "/why-", "/what-", "/report/", "/insight")
JOB_PATHS = ("/job", "/career", "/vacanc", "/position", "/opportunit",
             "/employment", "/opening", "/recruit", "/apply", "/post/")


def _is_posting(link: str) -> bool:
    low = (link or "").lower()
    if any(b in low for b in BLOG_PATHS):
        return False
    return any(j in low for j in JOB_PATHS)


def _base(title, company, location, url, desc, posted, source):
    return {
        "title": title or "",
        "company": company or source,
        "location": location or "",
        "url": url or "",
        "description": strip_html(desc)[:6000],
        "posted": posted,
        "source": source,
        # These feeds carry every kind of role. Calling them all conservation
        # made the category filter lie, so they are labelled by where they came
        # from and the scoring decides whether they are worth showing.
        "org_cat": "aggregator",
        "country_hint": "",
        "cap_exempt": False,
        "department": "",
    }


def _text(node, *names):
    for n in names:
        el = node.find(n)
        if el is not None and (el.text or "").strip():
            return el.text.strip()
        # Atom uses attributes for links
        el = node.find(f"{{http://www.w3.org/2005/Atom}}{n}")
        if el is not None:
            return (el.text or el.get("href") or "").strip()
    return ""


def _rss_one(name: str, url: str) -> list[dict]:
    r = get(url, session())
    if not r or r.status_code != 200 or not r.content:
        log.debug("feed dead: %s", name)
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        log.debug("feed unparseable: %s", name)
        return []

    items = root.iter("item")
    entries = list(items) or list(root.iter("{http://www.w3.org/2005/Atom}entry"))
    out = []
    for it in entries:
        title = _text(it, "title")
        link = _text(it, "link")
        if not link:
            le = it.find("{http://www.w3.org/2005/Atom}link")
            link = le.get("href") if le is not None else ""
        desc = _text(it, "description", "summary", "content")
        pub = _text(it, "pubDate", "published", "updated")
        posted = None
        if pub:
            try:
                posted = parsedate_to_datetime(pub).date().isoformat()
            except (TypeError, ValueError):
                posted = pub[:10]
        if not _is_posting(link):
            continue
        out.append(_base(title, name, "", link, desc, posted, name))
    if out:
        log.info("%-38s %d", name, len(out))
    return out


def _reject_shared_links(items: list[dict], source: str) -> list[dict]:
    """Throw out feeds that give one link for many postings.

    A feed serving the same URL under ten different titles is not publishing
    per-job links, so every row it produces is a lie about where it goes. This
    is what put one conservation link on the dashboard ten times.
    """
    counts: dict[str, int] = {}
    for it in items:
        counts[it.get("url", "")] = counts.get(it.get("url", ""), 0) + 1
    shared = {u for u, n in counts.items() if n > 1}
    if not shared:
        return items
    kept = [it for it in items if it.get("url", "") not in shared]
    log.warning("%s: dropped %d items sharing %d duplicate links",
                source, len(items) - len(kept), len(shared))
    return kept


def rss() -> list[dict]:
    jobs = []
    for name, url in RSS_FEEDS:
        try:
            jobs.extend(_reject_shared_links(_rss_one(name, url), name))
        except Exception as exc:
            log.debug("feed error %s: %s", name, exc)
    return jobs


def reliefweb() -> list[dict]:
    out, sess = [], session()
    for q in RELIEFWEB_QUERIES:
        url = (f"{RELIEFWEB}?appname=job-radar&limit=100&profile=full"
               f"&query[value]={q.replace(' ', '%20')}&sort[]=date:desc")
        r = get(url, sess)
        if not r or r.status_code != 200:
            continue
        try:
            data = r.json().get("data", [])
        except ValueError:
            continue
        for row in data:
            f = row.get("fields", {})
            src = f.get("source") or [{}]
            country = f.get("country") or [{}]
            item = _base(
                f.get("title"),
                src[0].get("name") if src else "ReliefWeb",
                ", ".join(c.get("name", "") for c in country[:2]),
                f.get("url"),
                f.get("body"),
                (f.get("date", {}).get("created") or "")[:10],
                "reliefweb")
            # ReliefWeb publishes a real closing date. Honour it.
            closing = (f.get("date", {}) or {}).get("closing")
            if closing:
                item["closes"] = closing[:10]
            out.append(item)
    log.info("reliefweb: %d", len(out))
    return out


def harvest() -> list[dict]:
    jobs = []
    try:
        jobs.extend(rss())
    except Exception as exc:
        log.warning("rss harvest failed: %s", exc)
    try:
        jobs.extend(reliefweb())
    except Exception as exc:
        log.warning("reliefweb failed: %s", exc)
    log.info("specialist boards returned %d raw postings", len(jobs))
    return jobs
