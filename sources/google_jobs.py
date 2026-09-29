"""
Google for Jobs via SerpApi.

Google serves script clients a "turn on JavaScript" page with no jobs in it,
and JobSpy's Google scraper returns nothing, so there is no free route. SerpApi
runs the search and hands back structured results.

Google for Jobs aggregates LinkedIn, Indeed and company career pages, so most
of what it returns overlaps sources we already have. The value is the rest:
postings on employer sites that no ATS board we scan covers. The apply link is
chosen accordingly - the employer's own page first, an aggregator only when it
is the sole option. Reposts of jobs already saved are dropped by the tracker's
title + company dedup.

Every search page costs one SerpApi credit, so this is frugal like Indeed: a
short query list, a hard cap per run, and never part of a broad scan.

API notes, checked against the docs (serpapi.com/google-jobs-api):
  - `start` pagination was discontinued by Google; pages chain through
    serpapi_pagination.next_page_token.
  - `chips` / `ltype` filters are deprecated, so there is no server-side date
    filter. Age is read from detected_extensions.posted_at ("3 hours ago")
    and filtered here.
"""
import hashlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

_API = "https://serpapi.com/search.json"
_ACCOUNT = "https://serpapi.com/account.json"   # free: does not use a credit
_ENV = "SERPAPI_API_KEY"

# Every entry is a paid search. Phrased for new-grad to ~2 yr roles; the
# normal keyword / level / JD-experience filters still run afterwards.
_QUERIES = [
    "entry level data scientist",
    "junior machine learning engineer",
    "entry level data engineer",
    "AI engineer new grad",
    "data analyst entry level",
]
_LOCATION = "United States"
_PAGES_PER_QUERY = 2      # ~10 results a page
_MAX_SEARCHES = 8         # hard ceiling per run, protects the credit budget
_TIMEOUT = 60

# Boards that re-list jobs. Their links are a last resort: we already scan
# LinkedIn and Indeed directly, and the rest put another hop before the
# employer's own application.
_AGGREGATORS = (
    "linkedin.com", "indeed.com", "ziprecruiter.com", "glassdoor.com",
    "bebee.com", "talent.com", "jooble.org", "simplyhired.com", "monster.com",
    "careerbuilder.com", "lensa.com", "jobright.ai", "adzuna.com",
    "learn4good.com", "salary.com", "jobilize.com", "whatjobs.com",
    "builtin.com", "dice.com", "snagajob.com", "tallo.com",
)

_AGE_RE = re.compile(r"(\d+)\s*\+?\s*(minute|min|hour|hr|day|week|month)", re.I)


_DOTENV = Path(__file__).resolve().parent.parent / ".env"


def api_key() -> str:
    """
    The SerpApi key: process environment, then the project .env, then the
    Windows user environment in the registry.

    Read at call time rather than import time. config.py loads .env once at
    startup, so a key pasted into .env (or set with setx) while the server is
    running would otherwise need a restart before the button worked.
    """
    key = os.environ.get(_ENV, "").strip()
    if key:
        return key
    try:
        from dotenv import dotenv_values
        key = (dotenv_values(_DOTENV).get(_ENV) or "").strip()
        if key:
            return key
    except ImportError:
        pass
    if os.name != "nt":
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, _ENV)[0]).strip()
    except OSError:
        return ""


def credits_left() -> int | None:
    """Searches remaining this month, or None if unknown. Costs nothing."""
    key = api_key()
    if not key:
        return None
    try:
        r = requests.get(_ACCOUNT, params={"api_key": key}, timeout=15)
        return r.json().get("total_searches_left")
    except Exception:
        return None


def _posted_to_dt(posted: str) -> datetime | None:
    """'3 hours ago' / '2 days ago' / '30+ days ago' -> approximate UTC time."""
    s = (posted or "").lower()
    if not s:
        return None
    now = datetime.now(timezone.utc)
    if "just" in s or "today" in s:
        return now
    if "yesterday" in s:
        return now - timedelta(days=1)
    m = _AGE_RE.search(s)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit.startswith("min"):
        return now - timedelta(minutes=n)
    if unit.startswith(("hour", "hr")):
        return now - timedelta(hours=n)
    if unit.startswith("day"):
        return now - timedelta(days=n)
    if unit.startswith("week"):
        return now - timedelta(weeks=n)
    return now - timedelta(days=30 * n)


def _is_aggregator(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in _AGGREGATORS)


def _best_apply_link(job: dict) -> tuple[str, str]:
    """
    (url, via) for the most direct application link.

    Employer pages beat aggregators; an aggregator beats Google's own share
    link, which only reopens the Google listing.
    """
    options = [o for o in (job.get("apply_options") or []) if o.get("link")]
    for o in options:
        if not _is_aggregator(o["link"]):
            return o["link"], o.get("title", "")
    if options:
        return options[0]["link"], options[0].get("title", "")
    return job.get("share_link", ""), job.get("via", "")


def _job_uid(job: dict) -> str:
    # job_id is a long base64 blob; hash it to a stable, short id. Fall back
    # to company + title + location when it is missing.
    basis = job.get("job_id") or "|".join(
        (job.get(k) or "").lower() for k in ("company_name", "title", "location"))
    return "google_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _search(key: str, query: str, page_token: str | None) -> dict:
    params = {"engine": "google_jobs", "q": query, "location": _LOCATION,
              "gl": "us", "hl": "en", "api_key": key}
    if page_token:
        params["next_page_token"] = page_token
    try:
        r = requests.get(_API, params=params, timeout=_TIMEOUT)
        d = r.json()
    except Exception as e:
        log.warning(f"Google Jobs {query!r}: {e}")
        return {}
    if d.get("error"):
        # "Google hasn't returned any results" is a normal empty page, not a fault
        if "hasn't returned any results" not in d["error"]:
            log.warning(f"Google Jobs {query!r}: {d['error'][:150]}")
        return {}
    return d


def fetch_google_jobs(cutoff: datetime) -> list[dict]:
    """Recent Google for Jobs postings. Costs SerpApi credits - use sparingly."""
    key = api_key()
    if not key:
        log.warning(f"Google Jobs: {_ENV} is not set; skipping")
        return []

    results: list[dict] = []
    seen: set[str] = set()
    searches = 0
    too_old = 0

    for query in _QUERIES:
        token = None
        for _ in range(_PAGES_PER_QUERY):
            if searches >= _MAX_SEARCHES:
                break
            searches += 1
            d = _search(key, query, token)
            jobs = d.get("jobs_results") or []

            page_fresh = 0
            for j in jobs:
                title = (j.get("title") or "").strip()
                company = (j.get("company_name") or "").strip()
                if not title or not company:
                    continue

                ext = j.get("detected_extensions") or {}
                posted = _posted_to_dt(ext.get("posted_at", ""))
                if posted is not None and posted < cutoff:
                    too_old += 1
                    continue
                page_fresh += 1

                uid = _job_uid(j)
                if uid in seen:
                    continue
                seen.add(uid)

                url, via = _best_apply_link(j)
                results.append({
                    "id":        uid,
                    "source":    "google_jobs",
                    "company":   company,
                    "title":     title,
                    "location":  (j.get("location") or _LOCATION).strip(),
                    "url":       url,
                    "posted_at": posted.isoformat() if posted else "",
                    "pay":       ext.get("salary", ""),
                    "via":       via,
                })

            token = (d.get("serpapi_pagination") or {}).get("next_page_token")
            # Stop paying for pages once one is entirely stale or there is no next
            if not token or not jobs or page_fresh == 0:
                break

    log.info(f"Google Jobs: {len(results)} jobs from {searches} searches "
             f"({too_old} older than the cutoff)")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(f"credits left: {credits_left()}")
    jobs = fetch_google_jobs(datetime.now(timezone.utc) - timedelta(days=1))
    print(f"\n{len(jobs)} jobs")
    for j in jobs[:15]:
        print(f"  {j['title'][:40]:<40} | {j['company'][:20]:<20} | {j['via'][:14]:<14} | {j['url'][:50]}")
