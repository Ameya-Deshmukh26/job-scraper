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
  - `chips` / `ltype` are deprecated. Google's own "Date posted" filter is
    plain query text: its "Yesterday" option is the query plus "since
    yesterday", so that phrase is appended to every search.
  - `detected_extensions` is no longer returned (checked live, Sept 2026;
    the docs still show it). The age ("19 hours ago") and salary are plain
    strings in `extensions`. Reading the old field left every result
    undated, so the date filter silently passed everything.

What is kept, because a live run returned mostly noise (28 of 56 from one
training company, links to re-posting boards, 9 already expired):
  - only results with a direct employer link (their ATS or their own
    domain). Results that only link to LinkedIn or Indeed are dropped:
    those sites are scanned directly.
  - only results with a readable age inside the lookback window
  - only links that still load (not 404/410 or an "expired" page)
"""
import hashlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

import jobmeta
from config import COUNTRY, SEARCH_COUNTRY, SEARCH_TITLES, SOURCE_QUERIES

log = logging.getLogger(__name__)

_API = "https://serpapi.com/search.json"
_ACCOUNT = "https://serpapi.com/account.json"   # free: does not use a credit
_ENV = "SERPAPI_API_KEY"

# Every entry is a paid search. Phrased for new-grad to ~2 yr roles; the
# normal keyword / level / JD-experience filters still run afterwards.
# SOURCE_QUERIES for this site in search_profile.py, else SEARCH_TITLES. The search cap below limits how
# many of them a run actually pays for.
_QUERIES = list(SOURCE_QUERIES.get("google_jobs") or SEARCH_TITLES)
_LOCATION = SEARCH_COUNTRY
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
    # seen in a live run
    "jobserve.com", "career.io", "jobleads.com", "vaia.com", "worthyjobsbase.com",
    "jobgether.com", "careerjet.com", "ladders.com", "recruit.net", "naukri.com",
    "foundit.in", "shine.com", "instahyre.com", "iimjobs.com", "hirist.tech",
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


def _extensions(job: dict) -> list[str]:
    """The tag strings on a result. Includes the old detected_extensions
    fields too, in case SerpApi brings them back."""
    tags = [str(e) for e in (job.get("extensions") or [])]
    old = job.get("detected_extensions") or {}
    tags += [str(old[k]) for k in ("posted_at", "salary") if old.get(k)]
    return tags


def _posted_from(job: dict) -> datetime | None:
    for tag in _extensions(job):
        t = tag.lower()
        if "ago" in t or t in ("today", "just posted", "yesterday"):
            when = _posted_to_dt(tag)
            if when:
                return when
    return None


_PAY_RE = re.compile(r"\b(?:a|an|per)\s+(?:year|hour|month|week|day)\b", re.I)


def _salary_from(job: dict) -> str:
    return next((tag for tag in _extensions(job) if _PAY_RE.search(tag)), "")


def _description(job: dict) -> str:
    """Google sends the full description plus a Qualifications list."""
    parts = [job.get("description") or ""]
    for block in job.get("job_highlights") or []:
        if "qualif" in (block.get("title") or "").lower():
            parts.extend(block.get("items") or [])
    return "\n".join(p for p in parts if p)


def _date_phrase(cutoff: datetime) -> str:
    """Google's own "Date posted" filter, written the way Google writes it."""
    # Slack on each bound: a "24 hour" cutoff is already a little over 24
    # hours old by the time it is measured, and fell through to "3 days".
    hours = (datetime.now(timezone.utc) - cutoff).total_seconds() / 3600
    if hours <= 26:
        return "since yesterday"
    if hours <= 74:
        return "in the last 3 days"
    if hours <= 24 * 7 + 2:
        return "in the last week"
    return "in the last month"


_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
_EXPIRED = ("no longer available", "job has expired", "position has been filled",
            "this job is no longer", "no longer accepting applications", "job not found")


def _link_alive(url: str) -> bool:
    """False only on clear evidence the posting is gone. A timeout or a bot
    wall from here says nothing about the job, so those count as alive."""
    try:
        r = requests.get(url, headers=_UA, timeout=12, allow_redirects=True)
    except Exception:
        return True
    if r.status_code in (404, 410):
        return False
    body = r.text[:200_000].lower()
    return not any(p in body for p in _EXPIRED)


def _is_aggregator(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in _AGGREGATORS)


# Hosts of the applicant-tracking systems employers post to directly. A link
# here is the employer's own application, whatever the domain looks like.
_ATS_HOSTS = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com",
    "myworkdaysite.com", "icims.com", "smartrecruiters.com", "jobvite.com",
    "workable.com", "bamboohr.com", "taleo.net", "successfactors.com",
    "oraclecloud.com", "recruitee.com", "breezy.hr", "jazzhr.com",
    "applytojob.com", "rippling.com", "dover.com", "keka.com", "darwinbox.in",
    "zohorecruit.com", "freshteam.com", "personio.de", "teamtailor.com",
    "gem.com", "paylocity.com", "ultipro.com", "adp.com", "paycomonline.net",
    "dayforcehcm.com", "avature.net", "eightfold.ai", "pinpointhq.com",
)
_COMPANY_WORDS = re.compile(r"[a-z0-9]{4,}")
_GENERIC_WORDS = {"group", "global", "services", "solutions", "technologies",
                  "technology", "systems", "limited", "company", "india", "corp"}


def _link_rank(url: str, company: str) -> int:
    """
    Lower is better: 0 the employer's ATS or own site, 1 an unknown site,
    2 a known job board. A blocklist of boards alone always misses some
    (jobserve, career.io and jobleads all slipped through a live run), so
    positive signs of an employer link are checked first.
    """
    host = urlparse(url).netloc.lower()
    if any(host == h or host.endswith("." + h) for h in _ATS_HOSTS):
        return 0
    words = set(_COMPANY_WORDS.findall(company.lower())) - _GENERIC_WORDS
    if any(w in host for w in words):
        return 0
    return 2 if _is_aggregator(url) else 1


def _best_apply_link(job: dict) -> tuple[str, str]:
    """
    (url, via) for the most direct application link: the employer's own
    page, then any other site, then a job board. Google's share link, which
    only reopens the Google listing, is the last resort.
    """
    options = [o for o in (job.get("apply_options") or []) if o.get("link")]
    company = job.get("company_name") or ""
    if options:
        best = min(options, key=lambda o: _link_rank(o["link"], company))  # stable: first wins ties
        return best["link"], best.get("title", "")
    return job.get("share_link", ""), job.get("via", "")


def _job_uid(job: dict) -> str:
    # job_id is a long base64 blob; hash it to a stable, short id. Fall back
    # to company + title + location when it is missing.
    basis = job.get("job_id") or "|".join(
        (job.get(k) or "").lower() for k in ("company_name", "title", "location"))
    return "google_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _search(key: str, query: str, page_token: str | None) -> dict:
    params = {"engine": "google_jobs", "q": query, "location": _LOCATION,
              "gl": COUNTRY["iso2"], "hl": "en", "api_key": key}
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
    from concurrent.futures import ThreadPoolExecutor

    key = api_key()
    if not key:
        log.warning(f"Google Jobs: {_ENV} is not set; skipping")
        return []

    phrase = _date_phrase(cutoff)
    found: list[dict] = []
    seen: set[str] = set()
    searches = 0
    dropped = {"older than the lookback": 0, "no date": 0, "no direct employer link": 0}

    for query in _QUERIES:
        token = None
        for _ in range(_PAGES_PER_QUERY):
            if searches >= _MAX_SEARCHES:
                break
            searches += 1
            d = _search(key, f"{query} {phrase}", token)
            jobs = d.get("jobs_results") or []

            page_fresh = 0
            for j in jobs:
                title = (j.get("title") or "").strip()
                company = (j.get("company_name") or "").strip()
                if not title or not company:
                    continue

                posted = _posted_from(j)
                if posted is None:
                    dropped["no date"] += 1
                    continue
                if posted < cutoff:
                    dropped["older than the lookback"] += 1
                    continue
                page_fresh += 1

                url, via = _best_apply_link(j)
                if _link_rank(url, company) != 0:
                    dropped["no direct employer link"] += 1
                    continue

                uid = _job_uid(j)
                if uid in seen:
                    continue
                seen.add(uid)
                found.append({
                    "id":        uid,
                    "source":    "google_jobs",
                    "company":   company,
                    "title":     title,
                    "location":  (j.get("location") or _LOCATION).strip(),
                    "url":       url,
                    "posted_at": posted.isoformat(),
                    "pay":       _salary_from(j),
                    "via":       via,
                    "description": _description(j),
                    "job_type":  jobmeta.job_type(" ".join(_extensions(j)), title),
                    "workplace": jobmeta.workplace(" ".join(_extensions(j)), title, j.get("location") or ""),
                })

            token = (d.get("serpapi_pagination") or {}).get("next_page_token")
            # Stop paying for pages once one is entirely stale or there is no next
            if not token or not jobs or page_fresh == 0:
                break

    # Only links that still load. Parallel: these are ordinary page fetches
    with ThreadPoolExecutor(max_workers=8) as pool:
        alive = list(pool.map(lambda j: _link_alive(j["url"]), found))
    results = [j for j, ok in zip(found, alive) if ok]
    dropped["expired link"] = len(found) - len(results)

    log.info(f"Google Jobs: {len(results)} kept from {searches} searches ({phrase}); dropped "
             + ", ".join(f"{n} {why}" for why, n in dropped.items() if n))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(f"credits left: {credits_left()}")
    jobs = fetch_google_jobs(datetime.now(timezone.utc) - timedelta(days=1))
    print(f"\n{len(jobs)} jobs")
    for j in jobs[:15]:
        print(f"  {j['title'][:40]:<40} | {j['company'][:20]:<20} | {j['via'][:14]:<14} | {j['url'][:50]}")
