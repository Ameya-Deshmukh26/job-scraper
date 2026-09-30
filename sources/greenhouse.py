import logging
from datetime import datetime, timezone

from functools import partial

import requests

import jobmeta
from experience import html_to_text

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "JobScraper/1.0 (personal job alerts)"})
# Sized for the parallel scan engine (12 workers hit this host at once)
_SESSION.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=16))
_BASE = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"



_DETAIL = "https://boards-api.greenhouse.io/v1/boards/{}/jobs/{}"


def _detail(company: str, job_id) -> dict:
    """The full description, from the job's own JSON (the page it links to is
    often a company site that needs a browser). Fetched only for new jobs."""
    try:
        r = _SESSION.get(_DETAIL.format(company, job_id), timeout=15)
        r.raise_for_status()
        return {"description": html_to_text(r.json().get("content", ""))}
    except Exception as e:
        log.debug(f"Greenhouse detail {company}/{job_id}: {e}")
        return {}


def fetch_greenhouse_jobs(company: str, cutoff: datetime) -> list[dict]:
    resp = _SESSION.get(_BASE.format(company), timeout=10)
    resp.raise_for_status()

    jobs = []
    for job in resp.json().get("jobs", []):
        # first_published is when it went up. updated_at moves on every edit,
        # which made months-old jobs look brand new.
        raw_ts = job.get("first_published") or job.get("updated_at") or ""
        if not raw_ts:
            continue
        posted = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        if posted < cutoff:
            continue
        title = job.get("title", "")
        location = job.get("location", {}).get("name", "Unknown")
        jobs.append({
            "id":        f"gh_{job['id']}",
            "source":    "Greenhouse",
            "company":   company,
            "title":     title,
            "location":  location,
            "url":       job.get("absolute_url", ""),
            "posted_at": raw_ts,
            "job_type":  jobmeta.job_type("", title),
            "workplace": jobmeta.workplace("", title, location),
            "_detail":   partial(_detail, company, job["id"]),
        })
    return jobs

