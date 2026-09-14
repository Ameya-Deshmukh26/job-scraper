"""
Indeed via Firecrawl.

Indeed 403s every direct client (their own bot wall), and the publisher API
and RSS feeds were retired years ago. Firecrawl's proxy gets through, and its
structured-extraction mode pulls job cards out reliably without regex-parsing
40KB of markdown.

Firecrawl bills per scrape, so this source is deliberately frugal: a small
query set, a hard scrape cap per run, and it is NOT part of the automatic
portal scan. Trigger it explicitly.
"""
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger(__name__)

_API = "https://api.firecrawl.dev/v2/scrape"
_KEY = os.environ.get("FIRECRAWL_API_KEY", "")

# Kept small on purpose - every entry here is a paid scrape
_QUERIES = [
    "data scientist",
    "machine learning engineer",
    "data analyst",
]
_LOCATIONS = ["Boston, MA", "Remote"]
_MAX_SCRAPES = 6          # hard ceiling per run, protects the credit budget
_TIMEOUT = 180

_SCHEMA = {
    "type": "object",
    "properties": {
        "jobs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title":    {"type": "string"},
                    "company":  {"type": "string"},
                    "location": {"type": "string"},
                    "posted":   {"type": "string",
                                 "description": "e.g. 'Just posted', 'Posted 3 days ago'"},
                    "job_key":  {"type": "string",
                                 "description": "The bare value of the jk query "
                                                "parameter in the job link - a 16-character "
                                                "hex string. Do NOT include the 'jk=' prefix. "
                                                "Leave empty if the link has no jk parameter; "
                                                "never invent or guess a value."},
                },
                "required": ["title", "company"],
            },
        }
    },
}

_AGE_RE = re.compile(r"(\d+)\s*\+?\s*day", re.I)

# A real Indeed jk is a 16-char hex string. The extractor sometimes returns it
# with a literal "jk=" prefix (producing ?jk=jk=...) or invents a slug, so
# normalise then validate rather than trusting the value.
# Real Indeed keys are exactly 16 hex chars. A looser 10-20 range let a
# model-fabricated "abcde12345" through, which 404s on Indeed.
_JK_RE = re.compile(r"^[0-9a-f]{16}$", re.I)
_PLACEHOLDERS = {"not_available", "n/a", "na", "none", "null", "unknown", ""}


def _clean_jk(raw: str) -> str | None:
    """Return a valid Indeed job key, or None if it cannot be trusted."""
    jk = (raw or "").strip().strip('"\'')
    # strip any number of leading jk= / ?jk= / &jk= prefixes
    while True:
        m = re.match(r"^[?&]?jk\s*=\s*(.*)$", jk, re.I)
        if not m:
            break
        jk = m.group(1).strip()
    jk = jk.split("&")[0].strip()          # drop trailing query params
    if jk.lower() in _PLACEHOLDERS:
        return None
    return jk if _JK_RE.match(jk) else None


def _posted_to_iso(posted: str) -> str:
    """Indeed shows relative ages; convert to an approximate UTC timestamp."""
    now = datetime.now(timezone.utc)
    s = (posted or "").lower()
    if not s or "not_available" in s:
        return ""
    if "just posted" in s or "today" in s or "active" in s:
        return now.isoformat()
    m = _AGE_RE.search(s)
    if m:
        return (now - timedelta(days=int(m.group(1)))).isoformat()
    if "hour" in s:
        return now.isoformat()
    return ""


def _scrape(query: str, location: str, days: int) -> list[dict]:
    url = (f"https://www.indeed.com/jobs?q={requests.utils.quote(query)}"
           f"&l={requests.utils.quote(location)}&fromage={days}&sort=date")
    try:
        r = requests.post(
            _API,
            headers={"Authorization": f"Bearer {_KEY}", "Content-Type": "application/json"},
            json={"url": url,
                  "formats": [{"type": "json",
                               "prompt": "Extract every job posting card on this search page.",
                               "schema": _SCHEMA}]},
            timeout=_TIMEOUT,
        )
        d = r.json()
        if not d.get("success"):
            log.warning(f"Indeed {query!r}/{location!r}: {str(d.get('error'))[:120]}")
            return []
        return ((d.get("data") or {}).get("json") or {}).get("jobs") or []
    except Exception as e:
        log.warning(f"Indeed {query!r}/{location!r}: {e}")
        return []


def fetch_indeed_jobs(cutoff: datetime) -> list[dict]:
    """Fetch recent Indeed postings. Costs Firecrawl credits - use sparingly."""
    days = max(1, min(7, round((datetime.now(timezone.utc) - cutoff).total_seconds() / 86400) or 1))

    results: list[dict] = []
    seen: set[str] = set()
    scrapes = 0

    for location in _LOCATIONS:
        for query in _QUERIES:
            if scrapes >= _MAX_SCRAPES:
                log.info(f"Indeed: hit scrape cap ({_MAX_SCRAPES})")
                break
            scrapes += 1
            for j in _scrape(query, location, days):
                title = (j.get("title") or "").strip()
                company = (j.get("company") or "").strip()
                if not title or not company:
                    continue

                jk = _clean_jk(j.get("job_key", ""))
                if jk:
                    uid = f"indeed_{jk}"
                    url = f"https://www.indeed.com/viewjob?jk={jk}"
                else:
                    # No stable id - synthesise one so dedup still works
                    uid = "indeed_" + re.sub(r"[^a-z0-9]+", "-",
                                             f"{company}-{title}".lower())[:60]
                    url = ("https://www.indeed.com/jobs?q="
                           + requests.utils.quote(f"{title} {company}"))
                if uid in seen:
                    continue
                seen.add(uid)

                results.append({
                    "id":        uid,
                    "source":    "indeed",
                    "company":   company,
                    "title":     title,
                    "location":  (j.get("location") or location).strip(),
                    "url":       url,
                    "posted_at": _posted_to_iso(j.get("posted", "")),
                })

    log.info(f"Indeed: {len(results)} jobs from {scrapes} scrapes")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    jobs = fetch_indeed_jobs(datetime.now(timezone.utc) - timedelta(days=1))
    print(f"\n{len(jobs)} jobs")
    for j in jobs[:15]:
        print(f"  {j['title'][:44]:<44} | {j['company'][:22]:<22} | {j['location'][:22]:<22} | {j['posted_at'][:10]}")
