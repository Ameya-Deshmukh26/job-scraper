"""
Remotive — free public API, no auth required.
Covers remote-first tech/data roles worldwide.
API: https://remotive.com/api/remote-jobs
"""
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "JobScraper/1.0"})
_BASE = "https://remotive.com/api/remote-jobs"

# Remotive category slugs that map to our target roles
_CATEGORIES = ["data", "machine-learning", "software-dev"]


def fetch_remotive_jobs(cutoff: datetime) -> list[dict]:
    jobs = []
    seen_ids: set = set()

    for category in _CATEGORIES:
        try:
            resp = _SESSION.get(_BASE, params={"category": category, "limit": 100}, timeout=15)
            resp.raise_for_status()
            for job in resp.json().get("jobs", []):
                if job["id"] in seen_ids:
                    continue
                seen_ids.add(job["id"])

                raw_ts = job.get("publication_date", "")
                if raw_ts:
                    posted = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    if posted.tzinfo is None:
                        posted = posted.replace(tzinfo=timezone.utc)
                    if posted < cutoff:
                        continue

                jobs.append({
                    "id":        f"rm_{job['id']}",
                    "source":    "Remotive",
                    "company":   job.get("company_name", ""),
                    "title":     job.get("title", ""),
                    "location":  job.get("candidate_required_location", "Remote"),
                    "url":       job.get("url", ""),
                    "posted_at": raw_ts,
                })
        except Exception as e:
            log.debug(f"Remotive category={category}: {e}")

    return jobs
