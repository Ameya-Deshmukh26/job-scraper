"""
Orchestrates auto-apply attempts for eligible jobs.

Rules:
- Only applies to Greenhouse and Lever (public forms, no login, no email codes)
- Caps at MAX_PER_RUN applications per scan to avoid looking spammy
- Logs every attempt (success or failure) to auto_apply.log
- Updates tracker with auto_applied status
"""
import json
import logging
import time
from pathlib import Path

from autoapply.greenhouse import apply_greenhouse
from autoapply.lever import apply_lever
from tracker import JobTracker

log = logging.getLogger(__name__)

PROFILE_PATH   = Path(__file__).parent.parent / "profile.json"
AUTO_APPLY_LOG = Path(__file__).parent.parent / "auto_apply.log"
MAX_PER_RUN    = 15   # max applications per overnight scan
DELAY_BETWEEN  = 8    # seconds between applications (avoid rate limits)


def _load_profile() -> dict:
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _log_attempt(company: str, title: str, url: str, success: bool, reason: str):
    from datetime import datetime
    line = (
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  "
        f"{'✓' if success else '✗'}  "
        f"{company:25s}  {title[:45]:45s}  {reason}\n"
        f"    {url}\n"
    )
    with open(AUTO_APPLY_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    log.info(f"  Auto-apply {'OK' if success else 'FAIL'} — {company} / {title}: {reason}")


def _can_auto_apply(job: dict) -> bool:
    source = job.get("source", "")
    return source in ("Greenhouse", "Lever")


def run_auto_apply(jobs: list[dict], tracker: JobTracker) -> dict:
    """
    Attempt auto-apply for eligible jobs.
    Returns {"attempted": N, "succeeded": N, "failed": N}
    """
    profile  = _load_profile()
    eligible = [j for j in jobs if _can_auto_apply(j)]

    if not eligible:
        log.info("  No auto-apply eligible jobs (Greenhouse/Lever only).")
        return {"attempted": 0, "succeeded": 0, "failed": 0}

    log.info(f"  Auto-applying to {min(len(eligible), MAX_PER_RUN)} of {len(eligible)} eligible jobs...")

    attempted = succeeded = failed = 0

    for job in eligible[:MAX_PER_RUN]:
        source  = job["source"]
        company = job["company"]
        title   = job["title"]
        url     = job["url"]

        try:
            if source == "Greenhouse":
                ok, reason = apply_greenhouse(url, profile)
            elif source == "Lever":
                ok, reason = apply_lever(url, profile)
            else:
                continue

            attempted += 1
            _log_attempt(company, title, url, ok, reason)

            if ok:
                succeeded += 1
                tracker.mark_auto_applied(job["id"])
            else:
                failed += 1
                tracker.mark_needs_review(job["id"], reason)

        except Exception as e:
            failed += 1
            _log_attempt(company, title, url, False, str(e))
            tracker.mark_needs_review(job["id"], str(e))

        time.sleep(DELAY_BETWEEN)

    return {"attempted": attempted, "succeeded": succeeded, "failed": failed}
