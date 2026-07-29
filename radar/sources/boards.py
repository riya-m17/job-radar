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
RSS_FEEDS = [
    ("Conservation Job Board", "https://www.conservationjobboard.com/rss"),
    ("Texas A&M Wildlife and Fisheries", "https://wfscjobs.tamu.edu/feed/"),
    ("Conservation Careers", "https://www.conservation-careers.com/feed/"),
    ("Ornithology Exchange", "https://ornithologyexchange.org/jobs/rss/"),
    ("Society for Conservation Biology", "https://careers.conbio.org/jobs/rss"),
    ("EnvironmentalCareer", "https://www.environmentalcareer.com/feed/"),
    ("AZA Job Board", "https://jobs.aza.org/jobs/rss"),
    ("Ecological Society of America", "https://careers.esa.org/jobs/rss"),
    ("American Fisheries Society", "https://careers.fisheries.org/jobs/rss"),
    ("The Wildlife Society", "https://careers.wildlife.org/jobs/rss"),
    ("Marine Technology Society", "https://careers.mtsociety.org/jobs/rss"),
    ("Nature Careers", "https://www.nature.com/naturecareers/rss/jobs"),
    ("New Scientist Jobs", "https://jobs.newscientist.com/en-gb/rss/"),
    ("HigherEdJobs Biology", "https://www.higheredjobs.com/rss/categoryFeed.cfm?catID=13"),
    ("Idealist Environment", "https://www.idealist.org/en/jobs.rss"),
    ("Museum Jobs AAM", "https://careers.aam-us.org/jobs/rss"),
    ("Botanical Society of America", "https://careers.botany.org/jobs/rss"),
]

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
        "org_cat": "conservation",
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


def rss() -> list[dict]:
    jobs = []
    for name, url in RSS_FEEDS:
        try:
            jobs.extend(_rss_one(name, url))
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
            out.append(_base(
                f.get("title"),
                src[0].get("name") if src else "ReliefWeb",
                ", ".join(c.get("name", "") for c in country[:2]),
                f.get("url"),
                f.get("body"),
                (f.get("date", {}).get("created") or "")[:10],
                "reliefweb"))
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
