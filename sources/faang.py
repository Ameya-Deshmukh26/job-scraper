"""
FAANG career portals with public JSON APIs — no auth, no Selenium.

Working (verified Aug 2026):
  Amazon  — https://www.amazon.jobs/en/search.json  (sort=recent, posted_date)
  Netflix — Eightfold ATS: https://explore.jobs.netflix.net/api/apply/v2/jobs

Blocked for plain HTTP clients (would need a real browser):
  Google (careers API retired), Meta (GraphQL tokens), Apple (CSRF+WAF),
  Microsoft (bot-blocked CDN).
"""
import logging
import re
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0",
    "Accept": "application/json",
})

_QUERIES = [
    "data scientist",
    "data analyst",
    "machine learning engineer",
    "data engineer",
    "ai engineer",
    "business analyst",
]

_SLEEP = 0.5


def _amazon_location(loc: str) -> str:
    # "US, WA, Seattle" → "Seattle, WA"
    parts = [p.strip() for p in (loc or "").split(",")]
    if len(parts) == 3 and parts[0] == "US":
        return f"{parts[2]}, {parts[1]}"
    return loc or "Unknown"


def fetch_amazon_jobs(cutoff: datetime) -> list[dict]:
    jobs: list[dict] = []
    seen: set = set()
    for q in _QUERIES:
        try:
            r = _SESSION.get(
                "https://www.amazon.jobs/en/search.json",
                params={"base_query": q, "result_limit": 50, "offset": 0,
                        "sort": "recent", "country": "USA"},
                timeout=15,
            )
            r.raise_for_status()
            for j in r.json().get("jobs", []):
                jid = str(j.get("id_icims") or j.get("id") or "")
                if not jid or jid in seen:
                    continue
                # posted_date like "August  3, 2026"
                posted_iso = ""
                raw = re.sub(r"\s+", " ", j.get("posted_date") or "").strip()
                try:
                    posted = datetime.strptime(raw, "%B %d, %Y").replace(tzinfo=timezone.utc)
                    if posted < cutoff.replace(hour=0, minute=0, second=0, microsecond=0):
                        continue
                    posted_iso = posted.isoformat()
                except ValueError:
                    pass
                seen.add(jid)
                jobs.append({
                    "id":        f"amzn_{jid}",
                    "source":    "faang",
                    "company":   "Amazon",
                    "title":     (j.get("title") or "").strip(),
                    "location":  _amazon_location(j.get("location")),
                    "url":       "https://www.amazon.jobs" + (j.get("job_path") or ""),
                    "posted_at": posted_iso,
                })
        except Exception as e:
            log.debug(f"Amazon q={q!r}: {e}")
        time.sleep(_SLEEP)
    log.info(f"Amazon: {len(jobs)} jobs")
    return jobs


def fetch_netflix_jobs(cutoff: datetime) -> list[dict]:
    jobs: list[dict] = []
    seen: set = set()
    for q in _QUERIES:
        try:
            r = _SESSION.get(
                "https://explore.jobs.netflix.net/api/apply/v2/jobs",
                params={"domain": "netflix.com", "query": q, "num": 50, "start": 0,
                        "sort_by": "new"},
                timeout=15,
            )
            r.raise_for_status()
            for p in r.json().get("positions", []):
                pid = str(p.get("id") or "")
                if not pid or pid in seen:
                    continue
                posted_iso = ""
                t_create = p.get("t_create")
                if t_create:
                    try:
                        posted = datetime.fromtimestamp(int(t_create), tz=timezone.utc)
                        if posted < cutoff:
                            continue
                        posted_iso = posted.isoformat()
                    except Exception:
                        pass
                loc = p.get("location") or ""
                locs = p.get("locations") or []
                if not loc and locs:
                    loc = locs[0]
                seen.add(pid)
                jobs.append({
                    "id":        f"nflx_{pid}",
                    "source":    "faang",
                    "company":   "Netflix",
                    "title":     (p.get("name") or "").strip(),
                    "location":  loc or "Unknown",
                    "url":       p.get("canonicalPositionUrl")
                                 or f"https://explore.jobs.netflix.net/careers/job/{pid}",
                    "posted_at": posted_iso,
                })
        except Exception as e:
            log.debug(f"Netflix q={q!r}: {e}")
        time.sleep(_SLEEP)
    log.info(f"Netflix: {len(jobs)} jobs")
    return jobs


def fetch_faang_jobs(cutoff: datetime) -> list[dict]:
    return fetch_amazon_jobs(cutoff) + fetch_netflix_jobs(cutoff)


if __name__ == "__main__":
    from datetime import timedelta
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    jobs = fetch_faang_jobs(datetime.now(timezone.utc) - timedelta(days=3))
    print(f"\nTotal: {len(jobs)}")
    for j in jobs[:12]:
        print(f"  [{j['company']:<7}] {j['title'][:55]:<55} | {j['location'][:28]} | {j['posted_at'][:10]}")
