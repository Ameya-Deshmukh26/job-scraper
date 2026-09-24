"""
Retro-audit: find already-tracked jobs whose JD demands 5+ years.

Every dashboard scan used to persist jobs without reading the job description,
so the "5+ years required" filter never ran on anything in the tracker. This
script fetches the JD for jobs already saved and flags the ones that are too
senior, so they drop out of the feed.

Flagged jobs are NOT deleted. They stay in the table so repost dedup keeps
working; they are marked via needs_review + review_reason and hidden in the UI.

Usage
-----
  python audit_experience.py --limit 200            # newest 200 unapplied
  python audit_experience.py --limit 200 --source linkedin
  python audit_experience.py --stats                # what has been flagged
"""
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor

from main import _EXP_TOO_HIGH
from tailoring.jd_fetcher import fetch_jd
from tracker import JobTracker

logging.basicConfig(level=logging.WARNING, format="%(message)s")

REASON = "requires 5+ years experience"


def _verdict(job):
    """Return (job, years_required_snippet) or (job, None) if acceptable."""
    try:
        jd = fetch_jd(job["url"])
    except Exception:
        return job, None
    if not jd or jd.startswith("[Could not"):
        return job, None          # cannot read it, so do not penalise
    m = _EXP_TOO_HIGH.search(jd)
    return job, (m.group(0).strip()[:60] if m else None)


def audit(limit, source=None, workers=6):
    tracker = JobTracker()
    jobs = [j for j in tracker.all_jobs()
            if not j.get("applied")
            and not (j.get("review_reason") or "").startswith("requires 5+")]
    if source:
        jobs = [j for j in jobs if (j.get("source") or "").lower() == source.lower()]
    jobs = jobs[:limit]
    if not jobs:
        print("nothing to audit")
        tracker.close()
        return

    print(f"auditing {len(jobs)} jobs" + (f" from {source}" if source else "") + " ...")
    flagged = unreadable = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for job, snippet in ex.map(_verdict, jobs):
            if snippet:
                tracker.mark_needs_review(job["job_id"], REASON)
                flagged += 1
                print(f"  TOO SENIOR  {job['company'][:22]:<22} "
                      f"{job['title'][:40]:<40} [{snippet}]")
            else:
                unreadable += 1
    tracker.close()
    print(f"\nflagged {flagged} as too senior; {unreadable} looked fine or were unreadable")


def stats():
    tracker = JobTracker()
    rows = tracker.conn.execute(
        "SELECT source, COUNT(*) n FROM seen_jobs "
        "WHERE review_reason LIKE 'requires 5+%' GROUP BY source ORDER BY n DESC"
    ).fetchall()
    total = tracker.conn.execute(
        "SELECT COUNT(*) FROM seen_jobs WHERE review_reason LIKE 'requires 5+%'"
    ).fetchone()[0]
    tracker.close()
    print(f"{total} jobs flagged as requiring 5+ years")
    for r in rows:
        print(f"  {r['source']:<14} {r['n']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--source", default=None)
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    if a.stats:
        stats()
    else:
        audit(a.limit, a.source)
