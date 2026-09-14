"""
Job Scraper: LinkedIn, Indeed, HiringCafe, Hacker News, and direct
company portals (Greenhouse, Lever, Ashby, Workday, Oracle HCM, Avature, FAANG).

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
from sources.ashby import fetch_ashby_jobs
from sources.greenhouse import fetch_greenhouse_jobs
from sources.lever import fetch_lever_jobs
from sources.linkedin import fetch_linkedin_jobs
from sources.goldman_sachs import fetch_goldman_sachs_jobs
from sources.oracle_hcm import fetch_oracle_hcm_jobs
from sources.deloitte import fetch_deloitte_jobs
from sources.faang import fetch_faang_jobs
from sources.indeed import fetch_indeed_jobs
from sources.hackernews import fetch_hackernews_jobs
from sources.hiringcafe import fetch_hiringcafe_jobs
from sources.workday import fetch_workday_jobs
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
        |
        (?<![-–\d.])\b([5-9]|\d{2,})\s+years?   # bare "7 years..." (not "3-5 years")
    )
    \s*(?:of\s+)?(?:[\w/&,.-]+\s+){0,5}experience   # up to 5 qualifier words before "experience"
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

# Source groups so the dashboard can scan a subset (e.g. only portals)
PORTAL_SOURCE_NAMES = {"greenhouse", "lever", "ashby", "workday",
                       "goldman_sachs", "oracle_hcm", "deloitte", "faang"}

# Sources that cost real money per run (Firecrawl credits). Never included in
# a broad scan - they only run when named explicitly via `only=`.
PAID_SOURCE_NAMES = {"indeed"}


def fetch_all_sources(cutoff: datetime, only: set | None = None) -> tuple[list[dict], dict]:
    """
    Fetch every enabled source in parallel.
    `only` limits the run to a subset of source names (see PORTAL_SOURCE_NAMES).
    Returns (jobs, per-source raw counts).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def want(name: str) -> bool:
        if name in PAID_SOURCE_NAMES:
            return only is not None and name in only   # explicit opt-in only
        return only is None or name in only

    tasks: list[tuple[str, callable]] = []
    if want("greenhouse"):
        tasks += [("greenhouse", lambda c=c: fetch_greenhouse_jobs(c, cutoff))
                  for c in GREENHOUSE_COMPANIES]
    if want("lever"):
        tasks += [("lever", lambda c=c: fetch_lever_jobs(c, cutoff))
                  for c in LEVER_COMPANIES]
    if want("ashby"):
        tasks += [("ashby", lambda c=c: fetch_ashby_jobs(c, cutoff))
                  for c in ASHBY_COMPANIES]
    if want("linkedin") and ENABLE_LINKEDIN:
        tasks.append(("linkedin", lambda: fetch_linkedin_jobs(cutoff, us_only=US_ONLY)))
    if want("hiringcafe"):
        tasks.append(("hiringcafe", lambda: fetch_hiringcafe_jobs(cutoff)))
    if want("hackernews"):
        tasks.append(("hackernews", lambda: fetch_hackernews_jobs(cutoff)))
    if want("workday") and WORKDAY_COMPANIES:
        # One task per company — the fetcher is slow (5 keywords × 3 pages each),
        # so running the 30 boards concurrently is a huge win
        tasks += [("workday", lambda c=c: fetch_workday_jobs([c], cutoff))
                  for c in WORKDAY_COMPANIES]
    if want("goldman_sachs"):
        tasks.append(("goldman_sachs", lambda: fetch_goldman_sachs_jobs(cutoff)))
    if want("deloitte"):
        tasks.append(("deloitte", lambda: fetch_deloitte_jobs(cutoff)))
    if want("faang"):
        tasks.append(("faang", lambda: fetch_faang_jobs(cutoff)))
    if want("indeed"):
        tasks.append(("indeed", lambda: fetch_indeed_jobs(cutoff)))
    if want("oracle_hcm") and ORACLE_HCM_COMPANIES:
        tasks += [("oracle_hcm", lambda c=c: fetch_oracle_hcm_jobs([c], cutoff))
                  for c in ORACLE_HCM_COMPANIES]

    jobs: list[dict] = []
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                result = fut.result()
                jobs.extend(result)
                counts[name] = counts.get(name, 0) + len(result)
            except Exception as e:
                log.debug(f"{name}: {e}")
                counts.setdefault(name, 0)
    return jobs, counts


def process_jobs(jobs: list[dict], tracker: JobTracker, jd_check: bool = True) -> list[dict]:
    """
    Filter, dedupe, JD-check (in parallel), and persist a batch of fetched jobs.
    Returns the list of genuinely new jobs. Tracker is only touched from the
    calling thread (SQLite connections are not thread-safe).
    """
    from concurrent.futures import ThreadPoolExecutor

    # Phase 1 — cheap filters + dedupe against DB and within the batch
    candidates: list[dict] = []
    batch_keys: set = set()
    for job in jobs:
        if not _matches_keyword(job["title"]):
            continue
        if not _is_right_level(job["title"]):
            continue
        if not _matches_location(job["location"]):
            continue
        key = (job["title"].strip().lower(), job["company"].strip().lower())
        if job["id"] in batch_keys or key in batch_keys:
            continue
        if tracker.seen(job["id"]):
            continue
        if tracker.seen_by_title_company(job["title"], job["company"]):
            tracker.mark_seen({**job, "title": "__repost__"})
            continue
        batch_keys.add(job["id"])
        batch_keys.add(key)
        candidates.append(job)

    # Phase 2 — JD experience check, parallel (each is an HTTP fetch)
    if jd_check and candidates:
        with ThreadPoolExecutor(max_workers=8) as pool:
            ok_flags = list(pool.map(lambda j: _jd_ok_for_experience(j["url"]), candidates))
    else:
        ok_flags = [True] * len(candidates)

    # Phase 3 — persist
    new_jobs: list[dict] = []
    for job, ok in zip(candidates, ok_flags):
        tracker.mark_seen(job)   # seen either way so we never re-check it
        if ok:
            new_jobs.append(job)
    return new_jobs


def run_once(tracker: JobTracker, lookback_hours: float) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    t0 = time.time()
    jobs, counts = fetch_all_sources(cutoff)
    log.info(f"  Fetched {len(jobs)} raw jobs from {len(counts)} sources "
             f"in {time.time() - t0:.1f}s")

    new_jobs = process_jobs(jobs, tracker)

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

    # boards + the always-on feed sources (LinkedIn, HiringCafe, Hacker News)
    extra = (1 if ENABLE_LINKEDIN else 0) + 2
    sources = (len(GREENHOUSE_COMPANIES) + len(LEVER_COMPANIES)
               + len(ASHBY_COMPANIES) + len(WORKDAY_COMPANIES) + extra)

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
