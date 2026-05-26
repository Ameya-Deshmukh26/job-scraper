"""
LinkedIn Jobs — undocumented guest API, no auth required.
Works for US job listings without logging in.
Rate limit: 1 req/sec enforced below. If LinkedIn starts blocking,
increase the sleep or add a proxy.
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

_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# Queries matched to your target roles
_QUERIES = [
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "data engineer",
    "analytics engineer",
    "AI engineer",
    "gen ai engineer",
]


def fetch_linkedin_jobs(cutoff: datetime, us_only: bool = True) -> list[dict]:
    jobs: list[dict] = []
    seen_ids: set = set()

    for query in _QUERIES:
        try:
            for start in [0, 25]:
                params = {
                    "keywords":  query,
                    "location":  "United States",
                    "geoId":     "103644278",   # LinkedIn US geo ID
                    "f_TPR":     "r86400",      # past 24 hours
                    "start":     start,
                    "position":  1,
                    "pageNum":   0,
                }
                resp = _SESSION.get(_SEARCH_URL, params=params, timeout=15)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("li")
                if not cards:
                    break

                for card in cards:
                    # Skip Easy Apply — those go nowhere useful
                    if card.find(string=lambda s: s and "easy apply" in s.lower()):
                        continue
                    if card.find(class_=lambda c: c and "easy-apply" in c.lower()):
                        continue

                    # Job ID
                    div = card.find("div", {"data-entity-urn": True})
                    if not div:
                        continue
                    jid = div.get("data-entity-urn", "").split(":")[-1]
                    if not jid or jid in seen_ids:
                        continue
                    seen_ids.add(jid)

                    # Fields
                    title_el    = card.find("h3", class_="base-search-card__title")
                    company_el  = card.find("h4", class_="base-search-card__subtitle")
                    location_el = card.find("span", class_="job-search-card__location")
                    time_el     = card.find("time")

                    title    = title_el.get_text(strip=True)    if title_el    else ""
                    company  = company_el.get_text(strip=True)  if company_el  else ""
                    location = location_el.get_text(strip=True) if location_el else ""

                    if not title:
                        continue

                    # Posted time
                    posted_at = ""
                    if time_el and time_el.get("datetime"):
                        posted_at = time_el["datetime"]
                        try:
                            posted = datetime.fromisoformat(posted_at)
                            if posted.tzinfo is None:
                                posted = posted.replace(tzinfo=timezone.utc)
                            if posted < cutoff:
                                continue
                        except ValueError:
                            pass

                    jobs.append({
                        "id":        f"li_{jid}",
                        "source":    "LinkedIn",
                        "company":   company,
                        "title":     title,
                        "location":  location,
                        "url":       f"https://www.linkedin.com/jobs/view/{jid}",
                        "posted_at": posted_at,
                    })

                time.sleep(1.2)  # respect rate limit

        except Exception as e:
            log.debug(f"LinkedIn query='{query}' start={start}: {e}")

    return jobs
