"""
Staffing agency portals.

Most staffing sites are Angular/React shells with no scrapable HTML, but their
SPAs call plain JSON APIs that work fine from a script once you know the exact
parameter set. Insight Global is the first provider wired up here; the module
is shaped so more agencies can be added as `_PROVIDERS` entries.

Insight Global
--------------
  GET https://insightglobal.com/all/jobs
      ?keyword=data-scientist&page=1&size=50&sort=postedDate,desc
      &filter.includeOnlyRemoteWork=false&filter.locations=united-states
      &filter.distance=5&filter.status=active

`filter.distance` and `filter.status` are both required; without them the API
returns 200 with an empty job list. Keyword matching is very loose (searching
"data-scientist" returns "Warehouse Data Entry Clerk"), so the caller's title
filter does the real work.

Useful extra: this API exposes pay rate and contract type, which most sources
do not. Contract and contract-to-perm roles matter for STEM OPT.
"""
import logging
import re
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Referer": "https://insightglobal.com/jobs/",
})

IG_API = "https://insightglobal.com/all/jobs"
IG_SEARCH = "https://insightglobal.com/jobs/search/united-states/{kw}"

# Tailored to Ameya's background: data/ML/AI plus the analyst lane, and the
# GenAI terms that staffing firms now use for contract AI work.
_QUERIES = [
    "data-scientist",
    "data-analyst",
    "machine-learning-engineer",
    "data-engineer",
    "ai-engineer",
    "llm",
    "generative-ai",
    "business-intelligence",
    "analytics-engineer",
    "business-analyst",
]

_PAGE_SIZE = 50


def _pay(rate: dict | None) -> str:
    """Render payRate as a short human string, e.g. '$52/hr' or '$120k'."""
    if not rate:
        return ""
    lo = rate.get("min")
    if lo is None:
        return ""
    kind = (rate.get("type") or "").lower()
    if kind.startswith("hour"):
        return f"${lo:,.0f}/hr"
    if lo >= 1000:
        return f"${lo / 1000:,.0f}k"
    return f"${lo:,.0f}"


def _iso(raw: str) -> str:
    if not raw:
        return ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return ""


def _fetch_insight_global(keyword: str) -> list[dict]:
    params = {
        "keyword": keyword,
        "page": 1,
        "size": _PAGE_SIZE,
        "sort": "postedDate,desc",
        "filter.includeOnlyRemoteWork": "false",
        "filter.locations": "united-states",
        "filter.distance": 5,          # required, else the API returns nothing
        "filter.status": "active",     # required
    }
    try:
        r = _SESSION.get(IG_API, params=params, timeout=25)
        r.raise_for_status()
        return r.json().get("jobs") or []
    except Exception as e:
        log.debug(f"Insight Global {keyword!r}: {e}")
        return []


def fetch_staffing_jobs(cutoff: datetime) -> list[dict]:
    """Fetch recent staffing-agency postings. Free, no auth."""
    results: list[dict] = []
    seen: set[str] = set()

    for kw in _QUERIES:
        for j in _fetch_insight_global(kw):
            rid = str(j.get("requisitionId") or "")
            title = (j.get("jobTitle") or "").strip()
            if not rid or not title or rid in seen:
                continue

            posted = _iso(j.get("postedDate", ""))
            if posted:
                try:
                    if datetime.fromisoformat(posted) < cutoff:
                        continue
                except ValueError:
                    pass

            addr = j.get("workAddress") or {}
            city = (addr.get("locality") or "").strip()
            state = (addr.get("administrativeArea") or "").strip()
            if j.get("workRemote"):
                location = f"Remote{f' ({city}, {state})' if city else ''}"
            else:
                location = ", ".join(p for p in (city, state) if p) or "United States"

            seen.add(rid)
            jtype = (j.get("jobType") or "").strip()
            pay = _pay(j.get("payRate"))
            results.append({
                "id":        f"ig_{rid}",
                "source":    "staffing",
                "company":   "Insight Global",
                "title":     title,
                "location":  location,
                # No public per-job route exists, so deep-link a filtered search
                "url":       IG_SEARCH.format(
                                 kw=re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")),
                "posted_at": posted,
                "pay":       " ".join(p for p in (pay, jtype) if p),
            })

    log.info(f"Staffing (Insight Global): {len(results)} jobs across {len(_QUERIES)} queries")
    return results


if __name__ == "__main__":
    from datetime import timedelta
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    from main import _matches_keyword, _is_right_level

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    jobs = fetch_staffing_jobs(datetime.now(timezone.utc) - timedelta(days=3))
    rel = [j for j in jobs if _matches_keyword(j["title"]) and _is_right_level(j["title"])]
    print(f"\n{len(jobs)} fetched, {len(rel)} relevant after title filters\n")
    for j in rel[:20]:
        print(f"  {j['title'][:46]:<46} | {j['location'][:22]:<22} | {j['pay']}")
