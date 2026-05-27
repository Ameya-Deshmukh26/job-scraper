"""
Oracle Cloud HCM — Candidate Experience (CE) public job API scraper.

Uses the recruitingCEJobRequisitions REST endpoint that powers every
Oracle HCM careers portal.  No authentication required; only the
ora-irc-cx-userid and ora-irc-language headers are needed.

Endpoint:
  GET https://{tenant}.fa.{region}.oraclecloud.com/hcmRestApi/resources/latest/
      recruitingCEJobRequisitions
      ?finder=findReqs;siteNumber={SITE},keyword={kw}
      &limit={N}
      &expand=requisitionList

Response structure:
  { "items": [ {
      "TotalJobsCount": N,
      "requisitionList": [
        {
          "Id":                  "210741283",
          "Title":               "Data Analyst",
          "PostedDate":          "2026-05-19",
          "PrimaryLocation":     "New York, NY, United States",
          "PrimaryLocationCountry": "US",
          ...
        }, ...
      ]
  } ] }

Job detail URL:
  https://{tenant}.fa.{region}.oraclecloud.com/hcmUI/CandidateExperience/
      en/sites/{SITE}/requisitions/preview/{Id}
"""

import logging
import time
import uuid
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent":        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":            "application/json",
    "ora-irc-cx-userid": str(uuid.uuid4()),
    "ora-irc-language":  "en",
})

# How many jobs to pull per keyword search (Oracle paginates via the outer limit)
_PAGE_SIZE = 25

# Keywords aligned with config.py KEYWORDS
_SEARCH_TERMS = [
    "data analyst",
    "data scientist",
    "machine learning",
    "data engineer",
    "analytics",
    "ai engineer",
]

# Only include jobs from these country codes
_US_COUNTRY_CODES = {"US", "USA"}

_SLEEP = 0.4   # seconds between requests


def _build_url(tenant: str) -> str:
    return f"https://{tenant}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"


def _detail_url(tenant: str, site: str, job_id: str) -> str:
    # Tenant may or may not include region subdomain — derive base from tenant
    return (
        f"https://{tenant}/hcmUI/CandidateExperience/en/sites/{site}"
        f"/requisitions/preview/{job_id}"
    )


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        # Comes as "2026-05-19" (date only) — treat as midnight UTC
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def fetch_oracle_hcm_jobs(
    companies: list[tuple[str, str, str]],
    cutoff: datetime,
) -> list[dict]:
    """
    Fetch jobs from Oracle HCM Candidate Experience portals.

    companies: list of (tenant, site_code, display_name)
      e.g. [("jpmc.fa.oraclecloud.com", "CX_1001", "JPMorgan Chase"), ...]

    Returns normalised dicts: {id, source, company, title, location, url, posted_at}
    """
    results:  list[dict] = []
    seen_ids: set[str]   = set()

    for tenant, site, display_name in companies:
        url = _build_url(tenant)

        for term in _SEARCH_TERMS:
            offset = 0
            while True:
                params = {
                    "finder":  f"findReqs;siteNumber={site},keyword={term}",
                    "limit":   _PAGE_SIZE,
                    "offset":  offset,
                    "expand":  "requisitionList",
                }
                try:
                    r = _SESSION.get(url, params=params, timeout=20)
                    if r.status_code != 200:
                        log.debug(f"Oracle HCM {display_name!r} kw={term!r}: HTTP {r.status_code}")
                        break
                    data = r.json()
                except Exception as e:
                    log.debug(f"Oracle HCM {display_name!r} kw={term!r}: {e}")
                    break

                search = (data.get("items") or [{}])[0]
                reqs   = search.get("requisitionList") or []
                total  = search.get("TotalJobsCount", 0)

                if not reqs:
                    break

                for req in reqs:
                    job_id = str(req.get("Id") or "")
                    if not job_id:
                        continue

                    uid = f"oracle_{job_id}"
                    if uid in seen_ids:
                        continue

                    # Filter to US-only via PrimaryLocationCountry code
                    country_code = (req.get("PrimaryLocationCountry") or "").upper()
                    if country_code and country_code not in _US_COUNTRY_CODES:
                        continue

                    # Date filter
                    posted_dt  = _parse_date(req.get("PostedDate"))
                    posted_iso = posted_dt.isoformat() if posted_dt else ""
                    if posted_dt is not None and posted_dt < cutoff:
                        continue

                    seen_ids.add(uid)
                    title    = (req.get("Title") or "").strip()
                    location = (req.get("PrimaryLocation") or "Unknown").strip()

                    results.append({
                        "id":        uid,
                        "source":    "oracle_hcm",
                        "company":   display_name,
                        "title":     title,
                        "location":  location,
                        "url":       _detail_url(tenant, site, job_id),
                        "posted_at": posted_iso,
                    })

                log.debug(
                    f"Oracle {display_name!r} kw={term!r} offset={offset}: "
                    f"{len(reqs)} returned, total={total}"
                )

                offset += _PAGE_SIZE
                if offset >= min(total, _PAGE_SIZE * 5):  # cap at 5 pages (125 jobs) per keyword
                    break
                if len(reqs) < _PAGE_SIZE:
                    break

                time.sleep(_SLEEP)

            time.sleep(_SLEEP)

    log.info(f"Oracle HCM: {len(results)} jobs across {len(companies)} companies")
    return results


# ── Quick smoke-test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from datetime import timedelta

    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)-8s %(message)s")
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    companies = [
        ("jpmc.fa.oraclecloud.com",     "CX_1001",      "JPMorgan Chase"),
        ("hdpc.fa.us2.oraclecloud.com", "LateralHiring", "Goldman Sachs (Oracle)"),
        ("eeho.fa.us2.oraclecloud.com", "jobsearch",     "Oracle Corporation"),
    ]
    jobs = fetch_oracle_hcm_jobs(companies, cutoff)
    print(f"\nTotal: {len(jobs)}")
    by_co: dict[str, list] = {}
    for j in jobs:
        by_co.setdefault(j["company"], []).append(j)
    for co, jlist in sorted(by_co.items()):
        print(f"\n{co}: {len(jlist)} jobs")
        for j in jlist[:3]:
            print(f"  {j['title'][:55]:55s} | {j['location'][:30]:30s} | {j['posted_at'][:10] if j['posted_at'] else '?'}")
            print(f"  {j['url']}")
    sys.exit(0)
