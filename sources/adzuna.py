"""
Adzuna — aggregates Indeed, ZipRecruiter, SimplyHired, and more.
Free API key at: https://developer.adzuna.com/  (1 000 req/day free)
Set ADZUNA_APP_ID and ADZUNA_APP_KEY in config.py to enable.
"""
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "JobScraper/1.0"})
_BASE = "https://api.adzuna.com/v1/api/jobs/us/search/{page}"

_SEARCHES = [
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "data engineer",
    "analytics engineer",
    "ai engineer",
]


def fetch_adzuna_jobs(cutoff: datetime, app_id: str, app_key: str) -> list[dict]:
    if not app_id or not app_key:
        return []

    jobs = []
    seen_ids: set = set()

    for query in _SEARCHES:
        try:
            resp = _SESSION.get(
                _BASE.format(page=1),
                params={
                    "app_id":       app_id,
                    "app_key":      app_key,
                    "what":         query,
                    "where":        "united states",
                    "results_per_page": 50,
                    "sort_by":      "date",
                    "full_time":    1,
                },
                timeout=15,
            )
            resp.raise_for_status()

            for job in resp.json().get("results", []):
                jid = job.get("id", "")
                if jid in seen_ids:
                    continue
                seen_ids.add(jid)

                raw_ts = job.get("created", "")
                if raw_ts:
                    posted = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    if posted.tzinfo is None:
                        posted = posted.replace(tzinfo=timezone.utc)
                    if posted < cutoff:
                        continue

                location = job.get("location", {}).get("display_name", "Unknown")
                company = job.get("company", {}).get("display_name", "")

                jobs.append({
                    "id":        f"az_{jid}",
                    "source":    "Adzuna",
                    "company":   company,
                    "title":     job.get("title", ""),
                    "location":  location,
                    "url":       job.get("redirect_url", ""),
                    "posted_at": raw_ts,
                })
        except Exception as e:
            log.debug(f"Adzuna query='{query}': {e}")

    return jobs
