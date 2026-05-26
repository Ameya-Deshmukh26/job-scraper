import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "JobScraper/1.0 (personal job alerts)"})
_BASE = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"


def fetch_greenhouse_jobs(company: str, cutoff: datetime) -> list[dict]:
    resp = _SESSION.get(_BASE.format(company), timeout=10)
    resp.raise_for_status()

    jobs = []
    for job in resp.json().get("jobs", []):
        raw_ts = job.get("updated_at", "")
        if not raw_ts:
            continue
        updated = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        if updated < cutoff:
            continue
        jobs.append({
            "id":       f"gh_{job['id']}",
            "source":   "Greenhouse",
            "company":  company,
            "title":    job.get("title", ""),
            "location": job.get("location", {}).get("name", "Unknown"),
            "url":      job.get("absolute_url", ""),
            "posted_at": raw_ts,
        })
    return jobs
