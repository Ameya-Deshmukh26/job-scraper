"""
Ashby ATS source — used by Cursor, Linear, PostHog, Harvey, Cognition, and
many other top startups.

Old REST endpoint (posting-public/job-board) now returns 401.
New endpoint: POST https://jobs.ashbyhq.com/api/non-user-graphql
"""
import logging
import time
from datetime import datetime, timezone

from functools import partial

import requests

import jobmeta
from experience import html_to_text

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
      employmentType
      workplaceType
      compensationTierSummary
    }
  }
}
"""



# The list has no dates or descriptions; one posting's detail has both.
# Fetched only for jobs that are new and pass the title filters.
_DETAIL_QUERY = """
query($org: String!, $id: String!) {
  jobPosting(organizationHostedJobsPageName: $org, jobPostingId: $id) {
    descriptionHtml
    publishedDate
  }
}
"""


def _detail(company: str, jid: str) -> dict:
    try:
        r = _SESSION.post(_GQL_URL, json={"query": _DETAIL_QUERY, "variables": {"org": company, "id": jid}},
                          headers={"Referer": f"https://jobs.ashbyhq.com/{company}"}, timeout=12)
        post = ((r.json().get("data") or {}).get("jobPosting")) or {}
    except Exception as e:
        log.debug(f"Ashby detail {company}/{jid}: {e}")
        return {}
    out = {"description": html_to_text(post.get("descriptionHtml") or "")}
    if post.get("publishedDate"):
        out["posted_at"] = f"{post['publishedDate']}T00:00:00+00:00"
    return out


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

        # The list view has no date: the detail fills posted_at in for new
        # jobs, and the tracker's dedup keeps old ones from repeating.
        jobs.append({
            "id":        f"ashby_{jid}",
            "source":    "ashby",
            "company":   company,
            "title":     title,
            "location":  location,
            "url":       url,
            "posted_at": "",
            "job_type":  jobmeta.job_type(job.get("employmentType") or "", title),
            "workplace": jobmeta.workplace(job.get("workplaceType") or "", title, location),
            "pay":       (job.get("compensationTierSummary") or "").split(" • ")[0],
            "_detail":   partial(_detail, company, jid),
        })

    return jobs

