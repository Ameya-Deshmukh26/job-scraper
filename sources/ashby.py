"""
Ashby ATS source — used by Cursor, Linear, PostHog, Harvey, Cognition, and
many other top startups.

Old REST endpoint (posting-public/job-board) now returns 401.
New endpoint: POST https://jobs.ashbyhq.com/api/non-user-graphql
"""
import logging
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
})
_SESSION.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=16))

_GQL_URL = "https://jobs.ashbyhq.com/api/non-user-graphql"

_QUERY = """
query($org: String!) {
  jobBoardWithTeams(organizationHostedJobsPageName: $org) {
    jobPostings {
      id
      title
      locationName
      secondaryLocations { locationName }
      teamId
    }
  }
}
"""


def fetch_ashby_jobs(company: str, cutoff: datetime) -> list[dict]:
    try:
        resp = _SESSION.post(
            _GQL_URL,
            json={"query": _QUERY, "variables": {"org": company}},
            headers={"Referer": f"https://jobs.ashbyhq.com/{company}"},
            timeout=12,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.debug(f"Ashby {company}: {e}")
        return []

    board = (data.get("data") or {}).get("jobBoardWithTeams")
    if not board:
        return []   # company not on Ashby

    jobs = []
    for job in board.get("jobPostings", []):
        jid  = job.get("id", "")
        if not jid:
            continue

        title = (job.get("title") or "").strip()
        if not title:
            continue

        # Location
        location = (job.get("locationName") or "").strip()
        if not location:
            sec = job.get("secondaryLocations") or []
            location = sec[0].get("locationName", "Remote") if sec else "Remote"

        # URL — no externalLink in list view; construct canonical URL
        url = f"https://jobs.ashbyhq.com/{company}/{jid}"

        # No publishedAt in list view — tracker handles dedup (same as Goldman/Deloitte)
        jobs.append({
            "id":        f"ashby_{jid}",
            "source":    "ashby",
            "company":   company,
            "title":     title,
            "location":  location,
            "url":       url,
            "posted_at": "",
        })

    return jobs
