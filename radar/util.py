"""Shared plumbing: config loading, a polite HTTP session, text helpers."""

from __future__ import annotations

import hashlib
import html as html_mod
import logging
import re
import time
from functools import lru_cache
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"

log = logging.getLogger("radar")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


@lru_cache(maxsize=None)
def load_config(name: str) -> dict:
    path = CONFIG / f"{name}.yaml"
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def settings() -> dict:
    return load_config("settings")


def session() -> requests.Session:
    """One session per thread, with retries and a real user agent."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": settings()["run"]["user_agent"],
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s


def get(url: str, sess: requests.Session | None = None, **kw):
    """GET with retries. Returns the response or None. Never raises."""
    cfg = settings()["run"]
    sess = sess or session()
    kw.setdefault("timeout", cfg["timeout_seconds"])
    last = None
    for attempt in range(cfg["retries"] + 1):
        try:
            r = sess.get(url, **kw)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            return r
        except requests.RequestException as exc:
            last = exc
            time.sleep(0.6 * (attempt + 1))
    log.debug("GET failed %s (%s)", url, last)
    return None


def post(url: str, sess: requests.Session | None = None, **kw):
    cfg = settings()["run"]
    sess = sess or session()
    kw.setdefault("timeout", cfg["timeout_seconds"])
    for attempt in range(cfg["retries"] + 1):
        try:
            return sess.post(url, **kw)
        except requests.RequestException:
            time.sleep(0.6 * (attempt + 1))
    return None


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = _TAG.sub(" ", raw)
    text = html_mod.unescape(text)
    return _WS.sub(" ", text).strip()


def slug_candidates(name: str, hints: list[str] | None = None) -> list[str]:
    """Guess the board slugs an organization might use."""
    out: list[str] = list(hints or [])
    base = name.lower()
    base = re.sub(r"[\u2018\u2019'`]", "", base)
    base = re.sub(r"\b(inc|llc|ltd|plc|corp|corporation|company|co|the|and|of|for)\b", " ", base)
    base = re.sub(r"[^a-z0-9]+", " ", base).strip()
    words = base.split()
    if words:
        out.append("".join(words))
        out.append("-".join(words))
        if len(words) > 1:
            out.append(words[0])
            out.append("".join(w[0] for w in words))
    seen, uniq = set(), []
    for s in out:
        s = s.strip("-")
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def job_key(company: str, title: str, url: str) -> str:
    """Stable id so the same posting is recognised across runs."""
    norm_url = re.sub(r"[?#].*$", "", (url or "").lower().rstrip("/"))
    blob = f"{company.lower().strip()}|{title.lower().strip()}|{norm_url}"
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def first(*vals):
    for v in vals:
        if v:
            return v
    return None
