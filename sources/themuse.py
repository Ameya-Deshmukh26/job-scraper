"""
The Muse — free public API, no auth required.
Strong coverage of mid-size startups and tech companies in the US.
API: https://www.themuse.com/api/public/jobs
"""
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "JobScraper/1.0"})
_BASE = "https://www.themuse.com/api/public/jobs"

_CATEGORIES = [
    "Data Science",
    "Data Analysis",
    "Machine Learning",
    "Software Engineer",
]


def fetch_themuse_jobs(cutoff: datetime) -> list[dict]:
    jobs = []
    seen_ids: set = set()

    for category in _CATEGORIES:
        try:
            # page 0 and 1 = most recent ~200 postings per category
            for page in range(2):
                resp = _SESSION.get(
                    _BASE,
                    params={"category": category, "page": page, "descending": "true"},
                    timeout=15,
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
                if not results:
                    break

                for job in results:
                    jid = job.get("id")
                    if jid in seen_ids:
                        continue
                    seen_ids.add(jid)

                    raw_ts = job.get("publication_date", "")
                    if raw_ts:
                        posted = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                        if posted.tzinfo is None:
                            posted = posted.replace(tzinfo=timezone.utc)
                        if posted < cutoff:
                            continue

                    locations = job.get("locations", [{}])
                    location = locations[0].get("name", "Unknown") if locations else "Unknown"

                    company = job.get("company", {}).get("name", "")

                    jobs.append({
                        "id":        f"tm_{jid}",
                        "source":    "TheMuse",
                        "company":   company,
                        "title":     job.get("name", ""),
                        "location":  location,
                        "url":       job.get("refs", {}).get("landing_page", ""),
                        "posted_at": raw_ts,
                    })
        except Exception as e:
            log.debug(f"TheMuse category={category}: {e}")

    return jobs
