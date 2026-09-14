"""
LinkedIn Jobs — undocumented guest API, no auth required.
Works for US job listings without logging in.

f_TPR is computed from the cutoff datetime (e.g. r7200 = last 2 hours).
Easy Apply filtering: LinkedIn's f_AL=true returns ONLY Easy Apply jobs.
We fetch that set per query and subtract from the full results so only
direct-apply jobs remain — no Selenium needed.
"""
import logging
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

# LinkedIn serves the guest job cards from two interchangeable paths. Both
# returned identical results when last measured, but they have swapped the
# canonical one before, so try them in order and remember what worked.
_SEARCH_URLS = [
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results",
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
]
_SEARCH_URL = _SEARCH_URLS[0]      # kept for callers that import it directly


def _fetch(params: dict) -> requests.Response | None:
    """GET the guest search API, falling back across known endpoint paths."""
    global _SEARCH_URL
    ordered = [_SEARCH_URL] + [u for u in _SEARCH_URLS if u != _SEARCH_URL]
    last_status = None
    for url in ordered:
        try:
            r = _SESSION.get(url, params=params, timeout=15)
        except Exception as e:
            log.debug(f"LinkedIn {url.rsplit('/', 1)[-1]}: {e}")
            continue
        if r.status_code == 200 and r.text.strip():
            if url != _SEARCH_URL:
                log.info(f"LinkedIn: switched endpoint to {url.rsplit('/', 1)[-1]}")
                _SEARCH_URL = url          # stick with the one that works
            return r
        last_status = r.status_code
    log.warning(f"LinkedIn: all endpoints failed (last HTTP {last_status})")
    return None

_QUERIES = [
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "data engineer",
    "analytics engineer",
    "AI engineer",
    "gen ai engineer",
    "business analyst AI",
]


def _get_ids(params: dict) -> set:
    """Return job IDs from one page of LinkedIn search results."""
    r = _fetch(params)
    if r is None:
        return set()
    soup = BeautifulSoup(r.text, "html.parser")
    return {d["data-entity-urn"].split(":")[-1]
            for d in soup.find_all("div", {"data-entity-urn": True})
            if d["data-entity-urn"].split(":")[-1]}


def fetch_linkedin_jobs(cutoff: datetime, us_only: bool = True) -> list[dict]:
    jobs: list[dict] = []
    seen_ids: set = set()

    # Compute f_TPR from cutoff — LinkedIn filters server-side by seconds.
    # e.g. 2h lookback → r7200, 1h → r3600. Cap at 24h (r86400).
    now = datetime.now(timezone.utc)
    seconds = int((now - cutoff).total_seconds())
    seconds = max(3600, min(seconds, 86400))  # clamp 1h–24h
    f_tpr = f"r{seconds}"
    log.debug(f"LinkedIn f_TPR={f_tpr} ({seconds // 3600:.1f}h window)")

    for query in _QUERIES:
        try:
            base_params = {
                "keywords": query,
                "location": "United States",
                "geoId":    "103644278",
                "f_TPR":    f_tpr,
                "position": 1,
                "pageNum":  0,
            }

            # Collect Easy Apply IDs for this query (both pages)
            easy_ids: set = set()
            for start in [0, 25]:
                easy_ids |= _get_ids({**base_params, "start": start, "f_AL": "true"})
                time.sleep(1.0)
            log.debug(f"LinkedIn '{query}': {len(easy_ids)} Easy Apply IDs to exclude")

            # Now fetch all jobs and skip Easy Apply ones
            for start in [0, 25]:
                resp = _fetch({**base_params, "start": start})
                if resp is None:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("li")
                if not cards:
                    break

                for card in cards:
                    div = card.find("div", {"data-entity-urn": True})
                    if not div:
                        continue
                    jid = div.get("data-entity-urn", "").split(":")[-1]
                    if not jid or jid in seen_ids:
                        continue

                    # Skip Easy Apply jobs
                    if jid in easy_ids:
                        continue

                    # Skip reposts — LinkedIn shows "Reposted X hours ago"
                    # in the card's time element for recycled postings
                    time_check = card.find("time")
                    if time_check and "repost" in time_check.get_text(" ").lower():
                        continue

                    seen_ids.add(jid)

                    title_el    = card.find("h3", class_="base-search-card__title")
                    company_el  = card.find("h4", class_="base-search-card__subtitle")
                    location_el = card.find("span", class_="job-search-card__location")
                    time_el     = card.find("time")

                    title    = title_el.get_text(strip=True)    if title_el    else ""
                    company  = company_el.get_text(strip=True)  if company_el  else ""
                    location = location_el.get_text(strip=True) if location_el else ""

                    if not title:
                        continue

                    posted_at = ""
                    if time_el and time_el.get("datetime"):
                        posted_at = time_el["datetime"]

                    jobs.append({
                        "id":        f"li_{jid}",
                        "source":    "LinkedIn",
                        "company":   company,
                        "title":     title,
                        "location":  location,
                        "url":       f"https://www.linkedin.com/jobs/view/{jid}",
                        "posted_at": posted_at,
                    })

                time.sleep(1.2)

        except Exception as e:
            log.debug(f"LinkedIn query='{query}': {e}")

    # NOTE: an earlier version dropped jobs whose ID sat far below the batch
    # maximum, on the theory that LinkedIn re-dates reposts but keeps the old
    # ID. Measurement killed that idea: inside a single f_TPR=r3600 window the
    # ID span is ~82M, and a posting LinkedIn labelled "Just now" was 82M below
    # the batch max. IDs are not tightly monotonic with time, so any absolute
    # gap threshold sits in the noise and silently deletes brand-new jobs.
    #
    # Repost handling now relies only on sound signals:
    #   1. the "Reposted ..." marker in the card's <time>, handled above
    #   2. tracker.seen_by_title_company(), which catches a recycled posting
    #      the moment the same title+company reappears under a new ID
    log.info(f"LinkedIn: {len(jobs)} direct-apply jobs")
    return jobs
