"""
Goldman Sachs careers scraper — uses the public GraphQL API at higher.gs.com.

Endpoint: POST https://api-higher.gs.com/gateway/api/v1/graphql
No authentication required.

Job detail URL: https://higher.gs.com/roles/{roleId}
"""

import logging
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_GRAPHQL_URL = "https://api-higher.gs.com/gateway/api/v1/graphql"
_JOB_BASE    = "https://higher.gs.com/roles"
_PAGE_SIZE   = 20

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "Origin":       "https://higher.gs.com",
    "Referer":      "https://higher.gs.com/",
})

_QUERY = """
query GetRoles($searchQueryInput: RoleSearchQueryInput!) {
  roleSearch(searchQueryInput: $searchQueryInput) {
    totalCount
    items {
      roleId
      corporateTitle
      jobTitle
      jobFunction
      locations {
        primary
        state
        country
        city
      }
      status
      division
    }
  }
}
"""

# Keywords aligned with config.py KEYWORDS
_SEARCH_TERMS = [
    "data analyst",
    "data scientist",
    "machine learning",
    "data engineer",
    "analytics",
    "quantitative",
    "ai engineer",
    "business analyst",
]

# Experience levels to include (skip Partner/Managing Director levels)
_EXPERIENCES = ["EARLY_CAREER", "PROFESSIONAL"]


def _build_payload(search_term: str, page: int) -> dict:
    return {
        "operationName": "GetRoles",
        "variables": {
            "searchQueryInput": {
                "page": {
                    "pageSize": _PAGE_SIZE,
                    "pageNumber": page,
                },
                "sort": {
                    "sortStrategy": "RELEVANCE",
                    "sortOrder": "DESC",
                },
                "filters": [
                    {
                        "filterCategoryType": "LOCATION",
                        "filters": [
                            {"filter": "United States", "subFilters": []},
                        ],
                    },
                ],
                "experiences": _EXPERIENCES,
                "searchTerm": search_term,
            },
        },
        "query": _QUERY,
    }


def _parse_location(locations: list) -> str:
    """Pick the primary location, fall back to first available."""
    if not locations:
        return "Unknown"
    primary = next((loc for loc in locations if loc.get("primary")), locations[0])
    city    = primary.get("city", "")
    state   = primary.get("state", "")
    country = primary.get("country", "")
    parts   = [p for p in [city, state] if p]
    if not parts:
        parts = [country] if country else ["Unknown"]
    return ", ".join(parts)


def fetch_goldman_sachs_jobs(cutoff: datetime) -> list[dict]:
    """
    Fetch recent Goldman Sachs roles matching our keywords.
    Returns normalised dicts: {id, source, company, title, location, url, posted_at}.

    Note: the GS API exposes no posted-date field, so cutoff is ignored and all
    open US roles are returned. The tracker handles dedup across runs — first run
    ingests all open positions; subsequent runs only surface genuinely new ones.
    """
    results:  list[dict] = []
    seen_ids: set[str]   = set()

    for term in _SEARCH_TERMS:
        for page in range(5):   # up to 5 pages (100 jobs) per keyword
            payload = _build_payload(term, page)
            try:
                resp = _SESSION.post(_GRAPHQL_URL, json=payload, timeout=15)
                if resp.status_code != 200:
                    log.debug(f"GS API {term!r} page={page}: HTTP {resp.status_code}")
                    break
                data = resp.json()
            except Exception as e:
                log.debug(f"GS API {term!r} page={page}: {e}")
                break

            items = (data.get("data") or {}).get("roleSearch", {}).get("items") or []
            if not items:
                break

            for item in items:
                role_id = item.get("roleId")
                if not role_id:
                    continue

                # Skip LCA visa filings — these are legal notices, not job listings
                # (they appear as "nothing found" on the careers site)
                if "NOTICE_OF_FILING_LCA" in role_id:
                    continue

                # Skip any role with non-OPEN status
                status = (item.get("status") or "").upper()
                if status and status != "OPEN":
                    continue

                uid = f"gs_{role_id}"
                if uid in seen_ids:
                    continue

                # Filter to US only via location country field
                locs = item.get("locations") or []
                is_us = any(
                    (loc.get("country") or "").lower() in ("united states", "us", "usa")
                    for loc in locs
                )
                if not is_us:
                    continue

                seen_ids.add(uid)
                title    = (item.get("jobTitle") or "").strip()
                location = _parse_location(locs)

                # higher.gs.com SPA routes use only the numeric prefix of the roleId
                # e.g. "151793_GS_MID_CAREER" → https://higher.gs.com/roles/151793
                numeric_id = role_id.split("_")[0]
                job_url    = f"{_JOB_BASE}/{numeric_id}"

                results.append({
                    "id":        uid,
                    "source":    "goldman_sachs",
                    "company":   "Goldman Sachs",
                    "title":     title,
                    "location":  location,
                    "url":       job_url,
                    "posted_at": "",  # GS API does not expose posted date
                })

            # Stop paginating if we got fewer than a full page
            if len(items) < _PAGE_SIZE:
                break
            time.sleep(0.2)

        time.sleep(0.3)

    log.info(f"Goldman Sachs: {len(results)} jobs")
    return results


# ── Quick smoke-test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from datetime import timedelta
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s  %(levelname)-8s %(message)s")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    jobs = fetch_goldman_sachs_jobs(cutoff)
    print(f"\nTotal: {len(jobs)}")
    for j in jobs[:10]:
        print(f"  {j['title']:50s} | {j['location']:25s}")
        print(f"  {j['url']}")
    sys.exit(0)
