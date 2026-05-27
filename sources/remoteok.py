"""
RemoteOK job scraper — free public JSON API, no auth.

Endpoint: GET https://remoteok.com/api?tags={tag}
Returns a JSON array; first element is metadata, rest are job objects.

This board skews heavily toward startups, indie companies, and bootstrapped
businesses — a great complement to the Fortune-500-heavy Workday/Oracle sources.

Job fields: id, epoch, date, company, position, tags, location, url, apply_url
"""

import logging
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

_API = "https://remoteok.com/api"
_SLEEP = 2.0  # RemoteOK asks for ≥1s between requests; we use 2s to be safe

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "application/json",
    "Referer":    "https://remoteok.com/",
})

# Tag queries — each maps to a RemoteOK tag slug
_TAGS = [
    "machine-learning",
    "data-science",
    "python",
    "ai",
    "analytics",
    "data-engineering",
    "nlp",
]

# Title must contain at least one of these to be considered relevant
_MUST_CONTAIN = [
    "data", "analyst", "scientist", "analytics", "analytic",
    "machine learning", "ml ", " ml,", "deep learning",
    "nlp", "llm", "language model", "generative", "gen ai",
    "ai engineer", "ai/ml", "ml/ai", "applied scientist",
    "intelligence", "modeling", "modelling",
    "business intelligence", "bi ", " bi,",
    "quantitative", "quant",
    "research scientist", "research engineer",
    "data engineer", "etl", "pipeline",
    "statistics", "statistical",
]


def _is_relevant(title: str) -> bool:
    t = title.lower()
    return any(w in t for w in _MUST_CONTAIN)


def fetch_remoteok_jobs(cutoff: datetime) -> list[dict]:
    """
    Fetch startup / small-company jobs from RemoteOK.

    RemoteOK is primarily remote-first startups and bootstrapped companies —
    perfect complement to the Fortune-500-heavy Workday / Oracle sources.
    """
    results:  list[dict] = []
    seen_ids: set[str]   = set()

    for tag in _TAGS:
        try:
            r = _SESSION.get(_API, params={"tags": tag}, timeout=20)
            if r.status_code != 200:
                log.debug(f"RemoteOK tag={tag!r}: HTTP {r.status_code}")
                time.sleep(_SLEEP)
                continue

            raw = r.json()
            # First element is metadata dict, rest are job dicts
            jobs = [j for j in raw if isinstance(j, dict) and "position" in j]

            for j in jobs:
                job_id = str(j.get("id") or j.get("slug") or "")
                if not job_id:
                    continue
                uid = f"remoteok_{job_id}"
                if uid in seen_ids:
                    continue

                title = (j.get("position") or "").strip()
                if not title or not _is_relevant(title):
                    continue

                # Date filter — epoch is Unix seconds
                epoch = j.get("epoch")
                posted_dt = None
                posted_iso = ""
                if epoch:
                    try:
                        posted_dt  = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
                        posted_iso = posted_dt.isoformat()
                    except Exception:
                        pass

                if posted_dt is not None and posted_dt < cutoff:
                    continue

                # Location
                location = (j.get("location") or "Remote").strip()
                if not location:
                    location = "Remote"

                # URL — prefer apply_url, fall back to canonical url
                url = (j.get("apply_url") or j.get("url") or "").strip()
                if not url:
                    url = f"https://remoteok.com/l/{job_id}"

                seen_ids.add(uid)
                results.append({
                    "id":        uid,
                    "source":    "remoteok",
                    "company":   (j.get("company") or "Unknown").strip(),
                    "title":     title,
                    "location":  location,
                    "url":       url,
                    "posted_at": posted_iso,
                })

            log.debug(f"RemoteOK tag={tag!r}: {len(jobs)} raw, {len(results)} total so far")

        except Exception as e:
            log.debug(f"RemoteOK tag={tag!r}: {e}")

        time.sleep(_SLEEP)

    log.info(f"RemoteOK: {len(results)} jobs across {len(_TAGS)} tags")
    return results


# ── Quick smoke-test ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)-8s %(message)s")
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    jobs = fetch_remoteok_jobs(cutoff)
    print(f"\nTotal: {len(jobs)}")
    for j in jobs[:10]:
        print(f"  {j['title'][:55]:55s} | {j['company'][:25]:25s} | {j['posted_at'][:10]}")
        print(f"  {j['url']}")
    sys.exit(0)
