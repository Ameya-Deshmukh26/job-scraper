"""
Job Scraper — Greenhouse, Lever, LinkedIn, Remotive, TheMuse, Adzuna.

Usage
-----
  python main.py                  # one-shot, last 1 hour
  python main.py --hours 24       # catch-up scan
  python main.py --loop           # continuous every 15 min
  python main.py --loop --interval 10
  python main.py --history        # print last 50 seen jobs
"""

import argparse
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from config import (
    ADZUNA_APP_ID,
    ADZUNA_APP_KEY,
    ASHBY_COMPANIES,
    ENABLE_AUTO_APPLY,
    ENABLE_LINKEDIN,
    EXCLUDE_LEVELS,
    EXCLUDE_SENIOR,
    GREENHOUSE_COMPANIES,
    KEYWORDS,
    LEVER_COMPANIES,
    LOCATION_FILTER,
    LOOKBACK_HOURS,
    ORACLE_HCM_COMPANIES,
    OVERNIGHT_LOOKBACK_HRS,
    OVERNIGHT_POLL_HOURS,
    POLL_INTERVAL_MINUTES,
    US_ONLY,
    WORKDAY_COMPANIES,
)
from notifier import notify
from sources.adzuna import fetch_adzuna_jobs
from sources.ashby import fetch_ashby_jobs
from sources.greenhouse import fetch_greenhouse_jobs
from sources.lever import fetch_lever_jobs
from sources.linkedin import fetch_linkedin_jobs
from sources.goldman_sachs import fetch_goldman_sachs_jobs
from sources.oracle_hcm import fetch_oracle_hcm_jobs
from sources.deloitte import fetch_deloitte_jobs
from sources.remoteok import fetch_remoteok_jobs
from sources.hiringcafe import fetch_hiringcafe_jobs
from sources.remotive import fetch_remotive_jobs
from sources.workday import fetch_workday_jobs
from sources.themuse import fetch_themuse_jobs
from tracker import JobTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("job_scraper.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Location words that indicate non-US jobs ───────────────────────────────
_NON_US = [
    # South Asia
    "india", "bangalore", "bengaluru", "mumbai", "pune", "hyderabad",
    "delhi", "chennai", "kolkata", "noida", "gurugram", "gurgaon",
    "pakistan", "karachi", "lahore", "islamabad",
    "bangladesh", "dhaka",
    "sri lanka",
    # Europe
    "united kingdom", " uk,", "(uk)", "london", "manchester", "edinburgh",
    "germany", "berlin", "munich", "frankfurt", "hamburg",
    "france", "paris", "lyon",
    "netherlands", "amsterdam",
    "ireland", "dublin",
    "spain", "madrid", "barcelona",
    "italy", "milan", "rome",
    "sweden", "stockholm",
    "switzerland", "zurich", "geneva",
    "denmark", "copenhagen",
    "finland", "helsinki",
    "norway", "oslo",
    "belgium", "brussels",
    "austria", "vienna",
    "portugal", "lisbon",
    "poland", "warsaw", "krakow",
    "czech republic", "prague",
    "romania", "bucharest",
    "hungary", "budapest",
    "ukraine", "kyiv",
    "russia", "moscow",
    "greece", "athens",
    "turkey", "istanbul",
    # Canada
    "canada", "toronto", "vancouver", "ottawa", "montreal", "calgary",
    # Australia / NZ / Pacific
    "australia", "sydney", "melbourne", "brisbane",
    "new zealand", "auckland",
    # East Asia
    "china", "beijing", "shanghai", "shenzhen", "guangzhou", "hangzhou",
    "japan", "tokyo", "osaka",
    "south korea", "seoul",
    "taiwan", "taipei",
    "hong kong",
    # Southeast Asia
    "singapore",
    "thailand", "bangkok",
    "vietnam", "hanoi", "ho chi minh",
    "philippines", "manila",
    "malaysia", "kuala lumpur",
    "indonesia", "jakarta",
    # Middle East
    "israel", "tel aviv",
    "saudi arabia", "riyadh",
    "uae", "dubai", "abu dhabi",
    # Latin America
    "brazil", "são paulo", "sao paulo", "rio de janeiro",
    "mexico", "mexico city", "monterrey", "guadalajara",
    "argentina", "buenos aires",
    "colombia", "bogota",
    "chile", "santiago",
    # Africa
    "south africa", "johannesburg", "cape town",
    "nigeria", "lagos",
    "kenya", "nairobi",
    "egypt", "cairo",
]

# ── Filters ────────────────────────────────────────────────────────────────

def _is_us(location: str) -> bool:
    """Return False if location clearly points outside the US."""
    loc = location.lower()
    for marker in _NON_US:
        if marker in loc:
            return False
    return True


def _matches_keyword(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in KEYWORDS)


def _is_right_level(title: str) -> bool:
    """Return False if the title indicates a level too senior for 2-3 yr experience."""
    t = title.lower()
    if any(lvl in t for lvl in EXCLUDE_LEVELS):
        return False
    if EXCLUDE_SENIOR and ("senior" in t or " sr " in t or t.startswith("sr ") or t.startswith("sr.")):
        return False
    return True


def _matches_location(location: str) -> bool:
    if US_ONLY and not _is_us(location):
        return False
    if not LOCATION_FILTER:
        return True
    loc = location.lower()
    return any(f in loc for f in LOCATION_FILTER)


# ── JD experience check ────────────────────────────────────────────────────
# Patterns that signal 5+ years required — too senior for 2-3 yr experience

_EXP_TOO_HIGH = re.compile(
    r"""
    (?:
        \b([5-9]|\d{2,})\s*\+\s*years?          # "5+ years"
        |
        \b([5-9]|\d{2,})\s+or\s+more\s+years?   # "5 or more years"
        |
        minimum\s+(?:of\s+)?([5-9]|\d{2,})\s+years?   # "minimum 5 years"
        |
        at\s+least\s+([5-9]|\d{2,})\s+years?    # "at least 5 years"
        |
        \b([5-9]|\d{2,})\s*[-–]\s*\d+\s+years?  # "5-8 years" (lower bound ≥ 5)
    )
    \s*(?:of\s+)?(?:professional\s+|relevant\s+|related\s+|work\s+)?experience
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _jd_ok_for_experience(url: str) -> bool:
    """
    Fetch the JD and return False if it clearly requires 5+ years experience.
    Returns True on any fetch error (benefit of the doubt).
    """
    try:
        from tailoring.jd_fetcher import fetch_jd
        jd = fetch_jd(url)
        if jd.startswith("[Could not fetch"):
            return True   # can't fetch → don't penalise
        if _EXP_TOO_HIGH.search(jd):
            log.debug(f"JD filter: 5+ yrs required — skipping {url}")
            return False
        return True
    except Exception:
        return True   # any error → include the job


# ── Core scan ──────────────────────────────────────────────────────────────

def run_once(tracker: JobTracker, lookback_hours: float) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    new_jobs: list[dict] = []

    def _process(jobs: list[dict]):
        for job in jobs:
            if not _matches_keyword(job["title"]):
                continue
            if not _is_right_level(job["title"]):
                continue
            if not _matches_location(job["location"]):
                continue
            if tracker.seen(job["id"]):
                continue
            # Dedup reposts: same title+company already tracked under different ID
            if tracker.seen_by_title_company(job["title"], job["company"]):
                tracker.mark_seen({**job, "title": "__repost__"})
                continue
            # Fetch JD and check experience requirement
            if not _jd_ok_for_experience(job["url"]):
                tracker.mark_seen(job)   # mark seen so we don't re-check it
                continue
            new_jobs.append(job)
            tracker.mark_seen(job)

    # Greenhouse
    for company in GREENHOUSE_COMPANIES:
        try:
            _process(fetch_greenhouse_jobs(company, cutoff))
        except Exception as e:
            log.debug(f"Greenhouse {company}: {e}")
        time.sleep(0.08)

    # Lever
    for company in LEVER_COMPANIES:
        try:
            _process(fetch_lever_jobs(company, cutoff))
        except Exception as e:
            log.debug(f"Lever {company}: {e}")
        time.sleep(0.08)

    # LinkedIn
    if ENABLE_LINKEDIN:
        try:
            log.info("  Scanning LinkedIn...")
            _process(fetch_linkedin_jobs(cutoff, us_only=US_ONLY))
        except Exception as e:
            log.debug(f"LinkedIn: {e}")

    # Remotive
    try:
        _process(fetch_remotive_jobs(cutoff))
    except Exception as e:
        log.debug(f"Remotive: {e}")

    # TheMuse
    try:
        _process(fetch_themuse_jobs(cutoff))
    except Exception as e:
        log.debug(f"TheMuse: {e}")

    # HiringCafe
    try:
        _process(fetch_hiringcafe_jobs(cutoff))
    except Exception as e:
        log.debug(f"HiringCafe: {e}")

    # RemoteOK (startup / small-company remote jobs)
    try:
        _process(fetch_remoteok_jobs(cutoff))
    except Exception as e:
        log.debug(f"RemoteOK: {e}")

    # Workday
    if WORKDAY_COMPANIES:
        try:
            _process(fetch_workday_jobs(WORKDAY_COMPANIES, cutoff))
        except Exception as e:
            log.debug(f"Workday: {e}")

    # Goldman Sachs (custom GraphQL API — no date field, tracker handles dedup)
    try:
        _process(fetch_goldman_sachs_jobs(cutoff))
    except Exception as e:
        log.debug(f"Goldman Sachs: {e}")

    # Deloitte (Avature ATS — HTML scrape, no date field, tracker handles dedup)
    try:
        _process(fetch_deloitte_jobs(cutoff))
    except Exception as e:
        log.debug(f"Deloitte: {e}")

    # Oracle HCM (JPMorgan, Goldman Sachs lateral, Oracle Corp, etc.)
    if ORACLE_HCM_COMPANIES:
        try:
            _process(fetch_oracle_hcm_jobs(ORACLE_HCM_COMPANIES, cutoff))
        except Exception as e:
            log.debug(f"Oracle HCM: {e}")

    # Adzuna (optional)
    if ADZUNA_APP_ID and ADZUNA_APP_KEY:
        try:
            _process(fetch_adzuna_jobs(cutoff, ADZUNA_APP_ID, ADZUNA_APP_KEY))
        except Exception as e:
            log.debug(f"Adzuna: {e}")

    if new_jobs:
        log.info(f"  {len(new_jobs)} new job(s) found:")
        for job in new_jobs:
            log.info(
                f"  [{job['source']:12s}] {job['company']} — "
                f"{job['title']} | {job['location']}"
            )
            log.info(f"  {'':14s}{job['url']}")
            notify(job)
    else:
        log.info("  No new matching jobs.")

    return new_jobs


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Job board scraper")
    parser.add_argument("--hours", type=float, default=LOOKBACK_HOURS)
    parser.add_argument("--loop",  action="store_true")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL_MINUTES)
    parser.add_argument("--history",  action="store_true")
    parser.add_argument("--overnight", action="store_true",
                        help="Overnight mode: scan every 2h, auto-apply to GH+Lever")
    args = parser.parse_args()

    tracker = JobTracker()

    if args.history:
        rows = tracker.recent(50)
        if not rows:
            print("No jobs tracked yet.")
        for r in rows:
            print(f"{r['seen_at'][:16]}  {r['company']:20s}  {r['title']}")
            print(f"                       {r['url']}")
        tracker.close()
        return

    extra = (1 if ENABLE_LINKEDIN else 0) + 2  # LinkedIn + Remotive + TheMuse
    sources = len(GREENHOUSE_COMPANIES) + len(LEVER_COMPANIES) + extra
    if ADZUNA_APP_ID:
        sources += 1

    if args.overnight:
        from autoapply.runner import run_auto_apply
        log.info(
            f"OVERNIGHT MODE | scan every {OVERNIGHT_POLL_HOURS}h | "
            f"lookback {OVERNIGHT_LOOKBACK_HRS}h | auto-apply={ENABLE_AUTO_APPLY}"
        )
        while True:
            log.info("── Overnight scan ────────────────────────────────────")
            new_jobs = run_once(tracker, OVERNIGHT_LOOKBACK_HRS)
            if ENABLE_AUTO_APPLY and new_jobs:
                result = run_auto_apply(new_jobs, tracker)
                log.info(
                    f"  Auto-apply: {result['succeeded']} succeeded, "
                    f"{result['failed']} failed of {result['attempted']} attempted"
                )
            log.info(f"  Sleeping {OVERNIGHT_POLL_HOURS}h until next scan...")
            time.sleep(OVERNIGHT_POLL_HOURS * 3600)

    elif args.loop:
        log.info(f"Loop | {args.interval} min | {sources} sources | US_ONLY={US_ONLY}")
        while True:
            log.info("── Scanning ──────────────────────────────────────────")
            run_once(tracker, args.hours)
            log.info(f"Sleeping {args.interval} min...")
            time.sleep(args.interval * 60)
    else:
        log.info(f"One-shot | {args.hours}h lookback | {sources} sources | US_ONLY={US_ONLY}")
        run_once(tracker, args.hours)
        tracker.close()


if __name__ == "__main__":
    main()
