"""
Workday CXS API scraper.

Workday exposes an undocumented but public JSON endpoint used by their
hosted career sites:

    POST https://{subdomain}.wd{N}.myworkdayjobs.com/wday/cxs/{subdomain}/{board}/jobs

No authentication required.

Response JSON:
  {
    "total": <int>,
    "jobPostings": [
      {
        "title":        <str>,        # job title
        "externalPath": <str>,        # e.g. "/job/TX---Irving/Title-Slug_R0920505"
        "locationsText": <str>,       # "TX - Irving" | "2 Locations" etc.
        "postedOn":     <str>,        # "Posted Today" | "Posted 2 Days Ago" | "Posted 30+ Days Ago"
        "bulletFields": [<external_id>],  # list with one ID like "R0920505"
        "timeType":     <str>,        # "Full time" | "Part time"
      },
      ...
    ]
  }

Job detail URL:
  https://{subdomain}.wd{N}.myworkdayjobs.com/en-US/{board}{externalPath}

Date field is a human string ("Posted Today", "Posted 2 Days Ago",
"Posted 30+ Days Ago"). We convert to a UTC datetime approximation.

Each company tuple is: (full_subdomain, board_slug, display_name)
where full_subdomain includes the wd number, e.g. "cvshealth.wd1".
"""

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Accept": "application/json",
})

# Search terms aligned with config.py KEYWORDS
_SEARCH_TERMS = [
    "data engineer",
    "data scientist",
    "analytics engineer",
    "ml engineer",
    "ai engineer",
    "business analyst",
]

# Pages to fetch per (company, keyword) combination
_PAGES_PER_QUERY = 3
_PAGE_SIZE = 20

# Seconds between requests
_SLEEP_BETWEEN = 0.3


def _posted_on_to_datetime(posted_on: str) -> datetime | None:
    """
    Convert a Workday "postedOn" human string to a UTC datetime.

    Known patterns:
      "Posted Today"          → now
      "Posted Yesterday"      → now - 1 day
      "Posted 2 Days Ago"     → now - 2 days
      "Posted 30+ Days Ago"   → now - 30 days
      "Posted X Days Ago"     → now - X days

    Returns None if the string is unrecognised.
    """
    now = datetime.now(timezone.utc)
    if not posted_on:
        return None
    s = posted_on.strip().lower()
    if "today" in s:
        return now
    if "yesterday" in s:
        return now - timedelta(days=1)
    # "30+" → treat as exactly 30
    m = re.search(r'(\d+)\+?\s+day', s)
    if m:
        return now - timedelta(days=int(m.group(1)))
    return None


def _build_url(subdomain_with_wd: str, board: str) -> str:
    """
    Build the CXS endpoint URL.

    subdomain_with_wd: e.g. "cvshealth.wd1"  or just "cvshealth" (tries wd1)
    board: e.g. "CVS_Health_Careers"
    """
    # Extract just the company part (before any .wdN)
    company_part = subdomain_with_wd.split(".")[0]
    return (
        f"https://{subdomain_with_wd}.myworkdayjobs.com"
        f"/wday/cxs/{company_part}/{board}/jobs"
    )


def _job_detail_url(subdomain_with_wd: str, board: str, external_path: str) -> str:
    """Build the human-readable job detail page URL."""
    company_part = subdomain_with_wd.split(".")[0]
    return (
        f"https://{subdomain_with_wd}.myworkdayjobs.com"
        f"/en-US/{board}{external_path}"
    )


def _extract_external_id(job: dict) -> str:
    """Extract the external job ID from bulletFields or externalPath."""
    bullet = (job.get("bulletFields") or [])
    if bullet:
        return str(bullet[0]).strip()
    # Fall back: last segment of externalPath after final underscore
    path = job.get("externalPath", "")
    if "_" in path:
        return path.rsplit("_", 1)[-1]
    return path.replace("/", "_").strip("_") or ""


def _fetch_page(url: str, keyword: str, offset: int) -> dict | None:
    """
    POST one page to the CXS endpoint. Returns parsed JSON or None on error.
    """
    payload = {
        "appliedFacets": {},
        "limit": _PAGE_SIZE,
        "offset": offset,
        "searchText": keyword,
    }
    try:
        r = _SESSION.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            return r.json()
        log.debug(f"Workday {url} offset={offset}: HTTP {r.status_code}")
        return None
    except Exception as e:
        log.debug(f"Workday {url} offset={offset}: {e}")
        return None


def fetch_workday_jobs(
    companies: list[tuple],
    cutoff: datetime,
) -> list[dict]:
    """
    Fetch jobs from a list of Workday-hosted career boards.

    companies: list of (subdomain_with_wd, board_slug, display_name)
               e.g. [("cvshealth.wd1", "CVS_Health_Careers", "CVS Health"), ...]
    cutoff:    datetime — only return jobs posted at or after this time.

    Returns list of normalised dicts:
      {id, source, company, title, location, url, posted_at}
    """
    results: list[dict] = []
    seen_ids: set[str] = set()

    for subdomain_wd, board, display_name in companies:
        url = _build_url(subdomain_wd, board)
        company_found_any = False

        for keyword in _SEARCH_TERMS:
            for page in range(_PAGES_PER_QUERY):
                offset = page * _PAGE_SIZE
                data = _fetch_page(url, keyword, offset)
                if not data:
                    break   # skip remaining pages for this company+keyword

                postings = data.get("jobPostings") or []
                total = data.get("total", 0)

                if not postings:
                    break   # no more results

                company_found_any = True
                page_kept = 0

                for job in postings:
                    ext_id = _extract_external_id(job)
                    if not ext_id:
                        continue

                    uid = f"workday_{ext_id}"
                    if uid in seen_ids:
                        continue

                    posted_dt = _posted_on_to_datetime(job.get("postedOn", ""))
                    if posted_dt is None:
                        # Unknown date — include it (benefit of the doubt)
                        posted_iso = ""
                    else:
                        if posted_dt < cutoff:
                            # Workday results are roughly sorted newest-first,
                            # so once we hit an old job we can stop this page
                            # (but continue to next keyword in case of ordering quirks)
                            pass
                        posted_iso = posted_dt.isoformat()

                    # Skip if we have a date and it's before cutoff
                    if posted_dt is not None and posted_dt < cutoff:
                        continue

                    seen_ids.add(uid)

                    title = (job.get("title") or "").strip()
                    location = (job.get("locationsText") or "Unknown").strip()
                    external_path = job.get("externalPath", "")
                    job_url = _job_detail_url(subdomain_wd, board, external_path)

                    results.append({
                        "id":        uid,
                        "source":    "workday",
                        "company":   display_name,
                        "title":     title,
                        "location":  location,
                        "url":       job_url,
                        "posted_at": posted_iso,
                    })
                    page_kept += 1

                log.debug(
                    f"Workday {display_name!r} kw={keyword!r} page={page}: "
                    f"kept {page_kept}/{len(postings)} (total={total})"
                )

                # Stop paginating if we got fewer results than the page size
                if len(postings) < _PAGE_SIZE:
                    break

                time.sleep(_SLEEP_BETWEEN)

        if company_found_any:
            log.debug(f"Workday {display_name!r}: done")

        time.sleep(_SLEEP_BETWEEN)

    log.info(f"Workday: {len(results)} jobs across {len(companies)} companies")
    return results


# ── Quick smoke-test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from datetime import timedelta

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Import the full company list from config
    try:
        from config import WORKDAY_COMPANIES
        companies = WORKDAY_COMPANIES
    except ImportError:
        # Minimal fallback for standalone test
        companies = [
            ("cvshealth.wd1", "CVS_Health_Careers", "CVS Health"),
            ("paypal.wd1",    "jobs",               "PayPal"),
            ("walmart.wd5",   "WalmartExternal",     "Walmart"),
            ("hp.wd5",        "ExternalCareerSite",  "HP"),
        ]

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    print(f"Fetching Workday jobs (cutoff: last 7 days)…")
    print(f"Testing {len(companies)} companies\n")

    jobs = fetch_workday_jobs(companies, cutoff)

    print(f"\nTotal jobs found: {len(jobs)}")

    # Group by company
    from collections import defaultdict
    by_company: dict[str, list] = defaultdict(list)
    for j in jobs:
        by_company[j["company"]].append(j)

    print("\nResults by company:")
    for company, cjobs in sorted(by_company.items()):
        print(f"  {company}: {len(cjobs)} jobs")
        for j in cjobs[:2]:
            print(f"    - {j['title']} | {j['location']} | {j['posted_at'] or j.get('postedOn','?')}")
            print(f"      {j['url']}")

    sys.exit(0)
