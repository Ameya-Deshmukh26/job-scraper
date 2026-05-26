import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "JobScraper/1.0 (personal job alerts)"})
_BASE = "https://api.lever.co/v0/postings/{}"


def fetch_lever_jobs(company: str, cutoff: datetime) -> list[dict]:
    resp = _SESSION.get(_BASE.format(company), params={"mode": "json"}, timeout=10)
    resp.raise_for_status()

    jobs = []
    for job in resp.json():
        created_ms = job.get("createdAt", 0)
        created = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
        if created < cutoff:
            continue
        categories = job.get("categories", {})
        jobs.append({
            "id":       f"lv_{job['id']}",
            "source":   "Lever",
            "company":  company,
            "title":    job.get("text", ""),
            "location": categories.get("location", "Unknown"),
            "url":      job.get("hostedUrl", ""),
            "posted_at": created.isoformat(),
        })
    return jobs
