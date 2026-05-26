"""
Ashby ATS source — used by Anthropic, Perplexity, Cursor, Vercel, Posthog,
Harvey, Cognition, Linear, and many other top startups.

Public API: POST https://api.ashbyhq.com/posting-public/job-board
"""
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "JobScraper/1.0 (personal job alerts)"})
_URL = "https://api.ashbyhq.com/posting-public/job-board"


def fetch_ashby_jobs(company: str, cutoff: datetime) -> list[dict]:
    try:
        resp = _SESSION.post(
            _URL,
            json={"organizationHostedJobsPageName": company},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        log.debug(f"Ashby {company}: {e}")
        return []

    jobs = []
    for job in resp.json().get("jobPostings", []):
        raw_ts = job.get("publishedAt", "")
        if not raw_ts:
            continue
        try:
            posted = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        except Exception:
            continue
        if posted < cutoff:
            continue

        # Location: prefer locationName, fall back to secondaryLocations
        location = job.get("locationName", "") or ""
        if not location:
            locs = job.get("secondaryLocations", [])
            location = locs[0].get("locationName", "Unknown") if locs else "Unknown"

        # Link: externalLink > ashby hosted page
        url = (job.get("externalLink") or
               f"https://jobs.ashbyhq.com/{company}/{job.get('id', '')}")

        jobs.append({
            "id":       f"ashby_{job['id']}",
            "source":   "Ashby",
            "company":  company,
            "title":    job.get("title", ""),
            "location": location,
            "url":      url,
            "posted_at": raw_ts,
        })
    return jobs
