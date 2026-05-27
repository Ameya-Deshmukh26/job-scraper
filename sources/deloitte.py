"""
Deloitte Careers (Avature ATS) scraper.

Uses the server-rendered HTML search endpoint — no Selenium, no Playwright.

URL pattern for paginated search:
  GET https://apply.deloitte.com/en_US/careers/SearchJobs/{keyword}
      ?listFilterMode=1&jobSort=relevancy&jobRecordsPerPage=10&jobOffset={offset}

Response: HTML page containing <article class="article--result"> elements.
  - Title:    h3 > a.link  (text)
  - URL:      h3 > a.link  (href)
  - Location: last <span> inside .article__header__text__subtitle
  - Total:    data-total attribute on the article element
  - Date:     NOT available in listing HTML — tracker handles dedup

Job detail URL: https://apply.deloitte.com/en_US/careers/JobDetail/{Title-Slug}/{ID}
Job ID: numeric suffix of the detail URL.
"""

import logging
import time
import urllib.parse
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_BASE = "https://apply.deloitte.com/en_US/careers/SearchJobs"
_PAGE_SIZE   = 10
_MAX_PAGES   = 8   # cap at 80 jobs per keyword (Deloitte rarely posts > 30 new at once)
_SLEEP       = 0.5

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer":    "https://apply.deloitte.com/",
})

# Keywords to search (keep concise — Deloitte ATS handles broad matching)
_SEARCH_TERMS = [
    "data analyst",
    "data scientist",
    "machine learning",
    "data engineer",
    "analytics engineer",
    "ai engineer",
]


def _fetch_page(keyword: str, offset: int) -> list[dict]:
    """Fetch one page of results; return list of raw job dicts."""
    kw_encoded = urllib.parse.quote(keyword)
    url = (
        f"{_BASE}/{kw_encoded}"
        f"?listFilterMode=1&jobSort=relevancy&sort=relevancy"
        f"&jobRecordsPerPage={_PAGE_SIZE}&jobOffset={offset}"
    )
    try:
        r = _SESSION.get(url, timeout=20)
        if r.status_code != 200:
            log.debug(f"Deloitte kw={keyword!r} offset={offset}: HTTP {r.status_code}")
            return []
    except Exception as e:
        log.debug(f"Deloitte kw={keyword!r} offset={offset}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    articles = soup.find_all("article", class_="article--result")
    results = []

    for article in articles:
        link_el = article.find("a", class_="link")
        if not link_el:
            continue

        title = link_el.get_text(strip=True)
        job_url = link_el.get("href", "")
        if not job_url:
            continue

        # Extract numeric ID from URL:
        # .../JobDetail/Data-Engineer-Project-Delivery-Analyst/350353
        job_id = job_url.rstrip("/").rsplit("/", 1)[-1]
        if not job_id.isdigit():
            # Fallback: use last path segment
            job_id = job_url.rstrip("/").rsplit("/", 1)[-1]

        # Location: last non-empty span in the subtitle
        subtitle = article.find(class_="article__header__text__subtitle")
        location = "United States"
        if subtitle:
            spans = [s.get_text(strip=True) for s in subtitle.find_all("span") if s.get_text(strip=True)]
            if spans:
                location = spans[-1]

        results.append({
            "id":        f"deloitte_{job_id}",
            "source":    "deloitte",
            "company":   "Deloitte",
            "title":     title,
            "location":  location,
            "url":       job_url,
            "posted_at": "",   # Avature listing HTML has no date field
        })

    return results


def fetch_deloitte_jobs(cutoff: datetime) -> list[dict]:
    """
    Fetch Deloitte jobs matching data/AI keywords.

    cutoff is accepted for API consistency but cannot be applied (no date in HTML).
    The tracker handles dedup so only truly new IDs surface each run.
    """
    all_jobs:  list[dict] = []
    seen_ids:  set[str]   = set()

    for term in _SEARCH_TERMS:
        for page in range(_MAX_PAGES):
            offset = page * _PAGE_SIZE
            jobs = _fetch_page(term, offset)

            if not jobs:
                break

            for job in jobs:
                if job["id"] not in seen_ids:
                    seen_ids.add(job["id"])
                    all_jobs.append(job)

            log.debug(
                f"Deloitte kw={term!r} offset={offset}: "
                f"{len(jobs)} returned"
            )

            if len(jobs) < _PAGE_SIZE:
                break  # last page

            time.sleep(_SLEEP)

        time.sleep(_SLEEP)

    log.info(f"Deloitte: {len(all_jobs)} jobs across {len(_SEARCH_TERMS)} keywords")
    return all_jobs


# ── Quick smoke-test ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)-8s %(message)s")
    cutoff = datetime.now(timezone.utc)
    jobs = fetch_deloitte_jobs(cutoff)
    print(f"\nTotal: {len(jobs)}")
    for j in jobs[:10]:
        print(f"  {j['title'][:60]:60s} | {j['location'][:30]:30s}")
        print(f"  {j['url']}")
    sys.exit(0)
