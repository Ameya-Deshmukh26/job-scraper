import logging
from datetime import datetime, timezone

import requests

import jobmeta
from experience import html_to_text

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "JobScraper/1.0 (personal job alerts)"})
# One request per company, all through this session, so the default pool of 10
# is smaller than the scan pool and connections get discarded and redialled.
_SESSION.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=16))
_BASE = "https://api.lever.co/v0/postings/{}"



def _description(job: dict) -> str:
    """Lever sends the whole posting: intro, requirement lists and closing."""
    parts = [job.get("descriptionPlain") or ""]
    for block in job.get("lists") or []:
        parts.append(block.get("text") or "")
        parts.append(html_to_text(block.get("content") or ""))
    parts.append(job.get("additionalPlain") or "")
    return "\n".join(p for p in parts if p)


def _pay(job: dict) -> str:
    sr = job.get("salaryRange") or {}
    if not sr.get("min"):
        return ""
    cur = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get(sr.get("currency", ""), "")
    per = {"per-year-salary": "/yr", "per-hour-wage": "/hr", "per-month-salary": "/mo"}.get(sr.get("interval", ""), "")
    lo, hi = sr.get("min"), sr.get("max")
    return f"{cur}{lo:,}" + (f"–{cur}{hi:,}" if hi and hi != lo else "") + per


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
        title = job.get("text", "")
        location = categories.get("location", "Unknown")
        jobs.append({
            "id":          f"lv_{job['id']}",
            "source":      "Lever",
            "company":     company,
            "title":       title,
            "location":    location,
            "url":         job.get("hostedUrl", ""),
            "posted_at":   created.isoformat(),
            "description": _description(job),
            "job_type":    jobmeta.job_type(categories.get("commitment", ""), title),
            "workplace":   jobmeta.workplace(job.get("workplaceType", ""), title, location),
            "pay":         _pay(job),
        })
    return jobs

