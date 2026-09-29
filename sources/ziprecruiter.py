"""
ZipRecruiter via Firecrawl.

ZipRecruiter answers plain requests with a Cloudflare 403, and JobSpy gets
the same. Firecrawl's proxy gets the page.

Measured Sept 2026 on one search page:
  - Firecrawl JSON extraction: 6 credits, and every "job link" it returned
    was the company's page (/co/<Company>/Jobs), not the job.
  - Raw HTML: 1-2 credits (a full 8-page run cost 14; some pages need
    Firecrawl's heavier proxy), and the page embeds a schema.org ItemList with
    each job's title and its own URL:
        /c/<Company>/Job/<Title>/-in-<City,ST>?jid=<id>
So this fetches raw HTML and parses that list here. Company and city come
from the URL path.

Recency comes from ZipRecruiter's own posted-within filter (`days=`), so
only recent postings are returned and paid for. Cards do not carry a
parseable date reliably, so posted_at is left empty and the dashboard uses
the time the job was first seen.

Paid (Firecrawl credits) and US-only, so it runs only when named, e.g.
from the Workday + Google tab.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote

import requests

from config import IN_US, SEARCH_CITIES, SEARCH_COUNTRY, SEARCH_TITLES, SOURCE_QUERIES

log = logging.getLogger(__name__)

_API = "https://api.firecrawl.dev/v2/scrape"
_SEARCH = "https://www.ziprecruiter.com/jobs-search?search={q}&location={loc}&days={days}"
_MAX_PAGES = 8            # 1-2 credits each (14 measured for 8); hard ceiling per run
_TIMEOUT = 180

# SOURCE_QUERIES for this site in search_profile.py, else SEARCH_TITLES
_QUERIES = list(SOURCE_QUERIES.get("ziprecruiter") or SEARCH_TITLES)

_ITEMLIST = re.compile(
    r'<script type="application/ld\+json">(\{"@context":"https://schema\.org",'
    r'"@type":"ItemList".*?)</script>', re.S)
_JOB_URL = re.compile(r"/c/([^/]+)/Job/[^/?]+(?:/-in-([^?]+))?\?jid=([0-9a-f]+)")


def _locations() -> list[str]:
    """
    Where to search. ZipRecruiter's nationwide results already include
    remote jobs, so a "Remote" entry in SEARCH_CITIES (there for Indeed) is
    skipped rather than paid for twice.
    """
    locs = [c for c in SEARCH_CITIES if c.strip().lower() != "remote"]
    return locs or [SEARCH_COUNTRY]


def _days(cutoff: datetime) -> int:
    """ZipRecruiter's posted-within choices: 1, 5, 10 or 30 days."""
    hours = (datetime.now(timezone.utc) - cutoff).total_seconds() / 3600
    for days in (1, 5, 10):
        if hours <= days * 24 + 2:
            return days
    return 30


def _unslug(s: str) -> str:
    return unquote(s or "").replace("-", " ").strip()


def _parse(html: str) -> list[dict]:
    """Jobs from the page's embedded schema.org ItemList."""
    m = _ITEMLIST.search(html or "")
    if not m:
        return []
    try:
        items = json.loads(m.group(1)).get("itemListElement") or []
    except ValueError:
        return []

    jobs = []
    for it in items:
        url = (it.get("url") or "").strip()
        title = (it.get("name") or "").strip()
        p = _JOB_URL.search(url)
        if not (title and p):
            continue
        company, loc, jid = p.groups()
        location = _unslug(loc).replace(",", ", ") if loc else "United States"
        jobs.append({
            "id":        f"ziprecruiter_{jid}",
            "source":    "ziprecruiter",
            "company":   _unslug(company),
            "title":     title,
            "location":  location,
            "url":       url,
            "posted_at": "",
        })
    return jobs


def _scrape(key: str, url: str) -> str:
    try:
        r = requests.post(
            _API,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["rawHtml"]},
            timeout=_TIMEOUT,
        )
        d = r.json()
    except Exception as e:
        log.warning(f"ZipRecruiter {url}: {e}")
        return ""
    if not d.get("success"):
        log.warning(f"ZipRecruiter {url}: {str(d.get('error'))[:150]}")
        return ""
    return (d.get("data") or {}).get("rawHtml") or ""


def fetch_ziprecruiter_jobs(cutoff: datetime) -> list[dict]:
    """Recent ZipRecruiter postings. Costs Firecrawl credits (1-2 per page)."""
    if not IN_US:
        log.info("ZipRecruiter: skipped, SEARCH_COUNTRY is not the United States")
        return []
    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not key:
        log.warning("ZipRecruiter: FIRECRAWL_API_KEY is not set; skipping")
        return []

    days = _days(cutoff)
    results: list[dict] = []
    seen: set[str] = set()
    pages = 0
    for query in _QUERIES:
        for loc in _locations():
            if pages >= _MAX_PAGES:
                break
            pages += 1
            url = _SEARCH.format(q=quote_plus(query), loc=quote_plus(loc), days=days)
            for job in _parse(_scrape(key, url)):
                if job["id"] not in seen:
                    seen.add(job["id"])
                    results.append(job)

    log.info(f"ZipRecruiter: {len(results)} jobs from {pages} pages (posted within {days} day(s))")
    return results
