"""
Dashboard web server.

  python app.py           # starts at http://localhost:5000
  python app.py --port 8080
"""

import argparse
import logging
import time
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from config import ENABLE_AUTO_APPLY, OVERNIGHT_LOOKBACK_HRS, OVERNIGHT_POLL_HOURS, US_ONLY
from main import (run_once, _is_us, _matches_keyword, _is_right_level,
                  _matches_location, fetch_all_sources, process_jobs)
from tracker import JobTracker
from sources.h1b import is_h1b_sponsor
from startups import annotate as annotate_startup
from ranking import _STAFFING as _STAFFING_RE

log = logging.getLogger(__name__)
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

_scan_lock      = threading.Lock()
_overnight_stop = threading.Event()
_overnight_thread: threading.Thread | None = None
_overnight_next_scan: list[float | None]   = [None]   # mutable box for thread to update


def _overnight_loop():
    from autoapply.runner import run_auto_apply
    log.info("Overnight loop started")
    while not _overnight_stop.is_set():
        _overnight_next_scan[0] = None          # signal: scanning now
        tracker = JobTracker()
        new_jobs = run_once(tracker, OVERNIGHT_LOOKBACK_HRS)
        if ENABLE_AUTO_APPLY and new_jobs:
            result = run_auto_apply(new_jobs, tracker)
            log.info(f"Auto-apply: {result['succeeded']} ok / {result['failed']} failed")
        tracker.close()

        wake_at = time.time() + OVERNIGHT_POLL_HOURS * 3600
        _overnight_next_scan[0] = wake_at
        # Sleep in 10-second chunks so stop signal is responsive
        while not _overnight_stop.is_set() and time.time() < wake_at:
            time.sleep(10)

    _overnight_next_scan[0] = None
    log.info("Overnight loop stopped")


# ── API ────────────────────────────────────────────────────────────────────

@app.get("/api/jobs")
def api_jobs():
    tracker = JobTracker()
    jobs = tracker.all_jobs()
    tracker.close()
    if US_ONLY:
        jobs = [j for j in jobs if _is_us(j.get("location", ""))]
    # Tag each job with H-1B sponsor status (cached lookup, fast)
    from ranking import match_score
    for j in jobs:
        j["h1b_sponsor"] = is_h1b_sponsor(j.get("company", ""))
        j["match"] = match_score(j)
        annotate_startup(j)
        # Staffing/contract shops are ranked down, so flag them explicitly:
        # contract roles matter for STEM OPT (needs a paid E-Verify employer).
        j["is_staffing"] = bool(_STAFFING_RE.search(j.get("company") or ""))
    return jsonify(jobs)


# -- Hacker News "Who is hiring" scan (free, startup-heavy) ----------------

_hn_lock = threading.Lock()
_hn_state: dict = {"running": False, "added": 0, "fetched": 0,
                   "error": None, "finished_at": None}


def _do_hn_scan(hours: float):
    global _hn_state
    import datetime
    from datetime import timedelta, timezone as _tz
    from sources.hackernews import fetch_hackernews_jobs
    try:
        cutoff = datetime.datetime.now(_tz.utc) - timedelta(hours=hours)
        jobs = fetch_hackernews_jobs(cutoff)
        tracker = JobTracker()
        added = len(process_jobs(jobs, tracker, jd_check=False))
        tracker.close()
        _hn_state.update(running=False, added=added, fetched=len(jobs), error=None,
                         finished_at=datetime.datetime.now().isoformat())
    except Exception as exc:
        log.exception("HN scan failed")
        _hn_state.update(running=False, error=str(exc),
                         finished_at=datetime.datetime.now().isoformat())
    finally:
        _hn_lock.release()


@app.post("/api/hn-scan")
def api_hn_scan():
    hours = float(request.json.get("hours", 720) if request.is_json else 720)
    if not _hn_lock.acquire(blocking=False):
        return jsonify({"error": "HN scan already running"}), 409
    _hn_state.update(running=True, added=0, fetched=0, error=None, finished_at=None)
    threading.Thread(target=_do_hn_scan, args=(hours,), daemon=True).start()
    return jsonify({"started": True, "hours": hours})


@app.get("/api/hn-scan/status")
def api_hn_scan_status():
    return jsonify(_hn_state)


# ── Indeed scan (Firecrawl - costs credits, manual trigger only) ──────────

_indeed_lock = threading.Lock()
_indeed_state: dict = {"running": False, "added": 0, "fetched": 0,
                       "error": None, "finished_at": None}


def _do_indeed_scan(hours: float):
    global _indeed_state
    import datetime
    from datetime import timedelta, timezone as _tz
    from sources.indeed import fetch_indeed_jobs
    try:
        cutoff = datetime.datetime.now(_tz.utc) - timedelta(hours=hours)
        jobs = fetch_indeed_jobs(cutoff)
        tracker = JobTracker()
        added = len(process_jobs(jobs, tracker, jd_check=False))
        tracker.close()
        _indeed_state.update(running=False, added=added, fetched=len(jobs),
                             error=None,
                             finished_at=datetime.datetime.now().isoformat())
    except Exception as exc:
        log.exception("indeed scan failed")
        _indeed_state.update(running=False, error=str(exc),
                             finished_at=datetime.datetime.now().isoformat())
    finally:
        _indeed_lock.release()


@app.post("/api/indeed-scan")
def api_indeed_scan():
    hours = float(request.json.get("hours", 24) if request.is_json else 24)
    if not _indeed_lock.acquire(blocking=False):
        return jsonify({"error": "Indeed scan already running"}), 409
    _indeed_state.update(running=True, added=0, fetched=0, error=None, finished_at=None)
    threading.Thread(target=_do_indeed_scan, args=(hours,), daemon=True).start()
    return jsonify({"started": True, "hours": hours})


@app.get("/api/indeed-scan/status")
def api_indeed_scan_status():
    return jsonify(_indeed_state)


# ── LangGraph agent ───────────────────────────────────────────────────────

@app.get("/api/agent/status")
def api_agent_status():
    """Which LLM backend and tracing are live."""
    from agent.llm import backend
    from agent.tracing import opik_enabled
    return jsonify({"llm_backend": backend(), "opik_tracing": opik_enabled()})


_agent_rank_lock = threading.Lock()
_agent_rank_state: dict = {"running": False, "assessed": 0, "error": None,
                           "finished_at": None, "backend": None}


def _do_agent_rank(limit: int):
    """Run the graph's rank path over the freshest jobs and persist reasoning."""
    global _agent_rank_state
    import datetime
    from agent.graph import rank_with_notes
    from agent.llm import backend
    try:
        tracker = JobTracker()
        jobs = [j for j in tracker.all_jobs() if not j.get("applied")][:limit]
        ranked, notes = rank_with_notes(jobs)
        assessed = 0
        for j in ranked:
            if j.get("fit_reason") or j.get("fit_gap"):
                tracker.save_agent_assessment(
                    j["job_id"], j.get("match"),
                    j.get("fit_reason"), j.get("fit_gap"))
                assessed += 1
        tracker.close()
        _agent_rank_state.update(
            running=False, assessed=assessed, error=None, backend=backend(),
            candidates=len(jobs), notes=notes,
            finished_at=datetime.datetime.now().isoformat())
    except Exception as exc:
        log.exception("agent rank failed")
        _agent_rank_state.update(running=False, error=str(exc),
                                 finished_at=datetime.datetime.now().isoformat())
    finally:
        _agent_rank_lock.release()


@app.post("/api/agent/rank")
def api_agent_rank():
    limit = int(request.json.get("limit", 40) if request.is_json else 40)
    if not _agent_rank_lock.acquire(blocking=False):
        return jsonify({"error": "Agent rank already running"}), 409
    _agent_rank_state.update(running=True, assessed=0, error=None, finished_at=None)
    threading.Thread(target=_do_agent_rank, args=(limit,), daemon=True).start()
    return jsonify({"started": True, "limit": limit})


@app.get("/api/agent/rank/status")
def api_agent_rank_status():
    return jsonify(_agent_rank_state)


@app.post("/api/agent/tailor/<job_id>")
def api_agent_tailor(job_id: str):
    """
    Run the tailoring path of the LangGraph agent for one tracked job.
    Returns grounded bullets plus the deterministic validation report.
    """
    from agent.graph import tailor as agent_tailor
    from tailoring.jd_fetcher import fetch_jd

    tracker = JobTracker()
    job = next((j for j in tracker.all_jobs() if j["job_id"] == job_id), None)
    tracker.close()
    if job is None:
        return jsonify({"error": "job not found"}), 404

    jd = fetch_jd(job["url"])
    if jd.startswith("[Could not"):
        jd = ""
    try:
        result = agent_tailor(
            {"title": job["title"], "company": job["company"], "jd": jd},
            target_bullets=int(request.args.get("bullets", 5)),
        )
    except Exception as exc:
        log.exception("agent tailor failed")
        return jsonify({"error": str(exc)}), 500

    return jsonify({
        "job":        {"title": job["title"], "company": job["company"], "url": job["url"]},
        "jd_chars":   len(jd),
        "bullets":    result["bullets"],
        "validation": result["validation"],
        "notes":      result["notes"],
    })


@app.get("/api/stats")
def api_stats():
    tracker = JobTracker()
    stats = tracker.stats()
    tracker.close()
    return jsonify(stats)


@app.post("/api/jobs/<job_id>/toggle")
def api_toggle(job_id: str):
    tracker = JobTracker()
    new_state = tracker.toggle_applied(job_id)
    tracker.close()
    return jsonify({"applied": new_state})


@app.post("/api/jobs/<job_id>/clear-review")
def api_clear_review(job_id: str):
    tracker = JobTracker()
    tracker.clear_review(job_id)
    tracker.close()
    return jsonify({"needs_review": False})


@app.get("/api/overnight/status")
def overnight_status():
    running = _overnight_thread is not None and _overnight_thread.is_alive()
    nxt     = _overnight_next_scan[0]
    return jsonify({
        "running":        running,
        "next_scan_at":   nxt,           # epoch float or None if scanning now
        "poll_hours":     OVERNIGHT_POLL_HOURS,
    })


@app.post("/api/overnight/start")
def overnight_start():
    global _overnight_thread
    if _overnight_thread and _overnight_thread.is_alive():
        return jsonify({"running": True, "msg": "Already running"})
    _overnight_stop.clear()
    _overnight_thread = threading.Thread(target=_overnight_loop, daemon=True, name="overnight")
    _overnight_thread.start()
    return jsonify({"running": True, "msg": "Started"})


@app.post("/api/overnight/stop")
def overnight_stop():
    _overnight_stop.set()
    return jsonify({"running": False, "msg": "Stopping after current task…"})


@app.post("/api/scan")
def api_scan():
    hours = float(request.json.get("hours", 1) if request.is_json else 1)
    if not _scan_lock.acquire(blocking=False):
        return jsonify({"error": "Scan already running"}), 409

    def _do_scan():
        try:
            tracker = JobTracker()
            run_once(tracker, hours)
            tracker.close()
        finally:
            _scan_lock.release()

    threading.Thread(target=_do_scan, daemon=True).start()
    return jsonify({"started": True, "hours": hours})


# ── Headed (visible) apply ────────────────────────────────────────────────

_headed_sessions: dict = {}   # job_id → {"status": "running"|"success"|"failed", "reason": str}


def _run_headed(job_id: str, job_url: str, profile: dict):
    from autoapply.headed import apply_headed
    _headed_sessions[job_id] = {"status": "running", "reason": ""}
    ok, reason = apply_headed(job_url, profile)
    _headed_sessions[job_id] = {
        "status": "success" if ok else "failed",
        "reason": reason,
    }
    if ok:
        tracker = JobTracker()
        tracker.mark_auto_applied(job_id)
        tracker.clear_review(job_id)
        tracker.close()


@app.post("/api/jobs/<job_id>/apply-headed")
def api_apply_headed(job_id: str):
    import json
    from pathlib import Path
    profile_path = Path(__file__).parent / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    tracker = JobTracker()
    job = next((j for j in tracker.all_jobs() if j["job_id"] == job_id), None)
    tracker.close()
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if _headed_sessions.get(job_id, {}).get("status") == "running":
        return jsonify({"error": "Already running"}), 409

    t = threading.Thread(
        target=_run_headed,
        args=(job_id, job["url"], profile),
        daemon=True,
    )
    t.start()
    return jsonify({"started": True, "company": job["company"], "title": job["title"]})


@app.get("/api/jobs/<job_id>/headed-status")
def api_headed_status(job_id: str):
    return jsonify(_headed_sessions.get(job_id, {"status": "not_started", "reason": ""}))


# ── LinkedIn scan (Apify) ─────────────────────────────────────────────────

_li_scan_lock = threading.Lock()
_li_scan_state: dict = {"running": False, "added": 0, "error": None, "finished_at": None}


def _do_linkedin_scan(hours: float):
    global _li_scan_state
    import datetime
    from datetime import timedelta, timezone as _tz
    from sources.linkedin import fetch_linkedin_jobs  # free guest API, no token
    try:
        cutoff = datetime.datetime.now(_tz.utc) - timedelta(hours=hours)
        jobs = fetch_linkedin_jobs(cutoff, us_only=True)
        tracker = JobTracker()
        added = len(process_jobs(jobs, tracker, jd_check=False))
        tracker.close()
        _li_scan_state.update(running=False, added=added, fetched=len(jobs),
                               error=None,
                               finished_at=datetime.datetime.now().isoformat())
    except Exception as exc:
        _li_scan_state.update(running=False, error=str(exc),
                               finished_at=datetime.datetime.now().isoformat())
    finally:
        _li_scan_lock.release()


@app.post("/api/linkedin-scan")
def api_linkedin_scan():
    hours = float(request.json.get("hours", 2) if request.is_json else 2)
    if not _li_scan_lock.acquire(blocking=False):
        return jsonify({"error": "LinkedIn scan already running"}), 409
    _li_scan_state.update(running=True, added=0, error=None, finished_at=None)
    threading.Thread(target=_do_linkedin_scan, args=(hours,), daemon=True).start()
    return jsonify({"started": True, "hours": hours})


@app.get("/api/linkedin-scan/status")
def api_linkedin_scan_status():
    return jsonify(_li_scan_state)


# ── HiringCafe scan ───────────────────────────────────────────────────────

_hc_scan_lock = threading.Lock()
_hc_scan_state: dict = {"running": False, "added": 0, "error": None, "finished_at": None}


def _do_hiringcafe_scan(hours: float):
    global _hc_scan_state
    from sources.hiringcafe import fetch_hiringcafe_jobs
    import datetime
    from datetime import timedelta, timezone
    try:
        cutoff = datetime.datetime.now(timezone.utc) - timedelta(hours=hours)
        jobs = fetch_hiringcafe_jobs(cutoff)
        tracker = JobTracker()
        added = len(process_jobs(jobs, tracker, jd_check=False))
        tracker.close()
        _hc_scan_state.update(running=False, added=added, error=None,
                               finished_at=datetime.datetime.now().isoformat())
    except Exception as exc:
        _hc_scan_state.update(running=False, error=str(exc),
                               finished_at=datetime.datetime.now().isoformat())
    finally:
        _hc_scan_lock.release()


@app.post("/api/hiringcafe-scan")
def api_hiringcafe_scan():
    hours = float(request.json.get("hours", 2) if request.is_json else 2)
    if not _hc_scan_lock.acquire(blocking=False):
        return jsonify({"error": "HiringCafe scan already running"}), 409
    _hc_scan_state.update(running=True, added=0, error=None, finished_at=None)
    threading.Thread(target=_do_hiringcafe_scan, args=(hours,), daemon=True).start()
    return jsonify({"started": True, "hours": hours})


@app.get("/api/hiringcafe-scan/status")
def api_hiringcafe_scan_status():
    return jsonify(_hc_scan_state)


# ── RemoteOK scan (startups + small companies) ────────────────────────────────

_rok_scan_lock = threading.Lock()
_rok_scan_state: dict = {"running": False, "added": 0, "error": None, "finished_at": None}


def _do_remoteok_scan(hours: float):
    global _rok_scan_state
    from sources.remoteok import fetch_remoteok_jobs
    import datetime
    from datetime import timedelta, timezone as _tz
    try:
        cutoff = datetime.datetime.now(_tz.utc) - timedelta(hours=hours)
        jobs   = fetch_remoteok_jobs(cutoff)
        tracker = JobTracker()
        added = len(process_jobs(jobs, tracker, jd_check=False))
        tracker.close()
        _rok_scan_state.update(running=False, added=added, error=None,
                               finished_at=datetime.datetime.now().isoformat())
    except Exception as exc:
        _rok_scan_state.update(running=False, error=str(exc),
                               finished_at=datetime.datetime.now().isoformat())
    finally:
        _rok_scan_lock.release()


@app.post("/api/remoteok-scan")
def api_remoteok_scan():
    hours = float(request.json.get("hours", 48) if request.is_json else 48)
    if not _rok_scan_lock.acquire(blocking=False):
        return jsonify({"error": "RemoteOK scan already running"}), 409
    _rok_scan_state.update(running=True, added=0, error=None, finished_at=None)
    threading.Thread(target=_do_remoteok_scan, args=(hours,), daemon=True).start()
    return jsonify({"started": True, "hours": hours})


@app.get("/api/remoteok-scan/status")
def api_remoteok_scan_status():
    return jsonify(_rok_scan_state)


# ── Portal scan (Greenhouse + Lever + Ashby + Workday combined) ───────────────

PORTAL_SOURCES = {"greenhouse", "lever", "ashby", "workday", "goldman_sachs", "oracle_hcm", "deloitte", "faang"}

_portal_scan_lock  = threading.Lock()
_portal_scan_state: dict = {
    "running":      False,
    "added":        0,
    "error":        None,
    "finished_at":  None,
    "last_scan_at": None,
    "sources":      {},    # source_name → raw job count returned by fetcher
}
_portal_auto_next: list[float | None] = [None]   # epoch of next auto-scan
_PORTAL_INTERVAL   = 3600                         # auto-scan every 60 minutes
_PORTAL_LOOKBACK   = 2.0                          # look back 2 hours each run


def _do_portal_scan(hours: float):
    """Fetch all portal sources (Greenhouse, Lever, Ashby, Workday, Goldman
    Sachs, Oracle HCM, Deloitte) in parallel, filter, and persist."""
    import datetime as _dt
    from datetime import timedelta, timezone

    try:
        cutoff = _dt.datetime.now(timezone.utc) - timedelta(hours=hours)
        all_jobs, source_counts = fetch_all_sources(cutoff, only=PORTAL_SOURCES)

        tracker = JobTracker()
        added = len(process_jobs(all_jobs, tracker, jd_check=False))
        tracker.close()

        now_iso = _dt.datetime.now().isoformat()
        _portal_scan_state.update(
            running=False, added=added, error=None,
            finished_at=now_iso, last_scan_at=now_iso,
            sources=source_counts,
        )
    except Exception as exc:
        _portal_scan_state.update(
            running=False, error=str(exc),
            finished_at=_dt.datetime.now().isoformat(),
        )
    finally:
        _portal_scan_lock.release()


def _portal_auto_loop():
    """Background thread: run a portal scan every _PORTAL_INTERVAL seconds."""
    while True:
        if _portal_scan_lock.acquire(blocking=False):
            _portal_scan_state.update(running=True, added=0, error=None, finished_at=None)
            threading.Thread(target=_do_portal_scan, args=(_PORTAL_LOOKBACK,),
                             daemon=True).start()
        wake_at = time.time() + _PORTAL_INTERVAL
        _portal_auto_next[0] = wake_at
        while time.time() < wake_at:
            time.sleep(10)


# Start the portal auto-scan as soon as the Flask process comes up
threading.Thread(target=_portal_auto_loop, daemon=True, name="portal-auto").start()


@app.post("/api/portal-scan")
def api_portal_scan():
    hours = float(request.json.get("hours", _PORTAL_LOOKBACK) if request.is_json else _PORTAL_LOOKBACK)
    if not _portal_scan_lock.acquire(blocking=False):
        return jsonify({"error": "Portal scan already running"}), 409
    _portal_scan_state.update(running=True, added=0, error=None, finished_at=None)
    threading.Thread(target=_do_portal_scan, args=(hours,), daemon=True).start()
    return jsonify({"started": True, "hours": hours})


@app.get("/api/portal-scan/status")
def api_portal_scan_status():
    state = dict(_portal_scan_state)
    state["next_auto_at"] = _portal_auto_next[0]
    state["interval_seconds"] = _PORTAL_INTERVAL
    return jsonify(state)


@app.get("/api/portal-companies")
def api_portal_companies():
    from config import GREENHOUSE_COMPANIES, LEVER_COMPANIES, ASHBY_COMPANIES, WORKDAY_COMPANIES, ORACLE_HCM_COMPANIES
    return jsonify({
        "greenhouse":    sorted(GREENHOUSE_COMPANIES),
        "lever":         sorted(LEVER_COMPANIES),
        "ashby":         sorted(ASHBY_COMPANIES),
        "workday":       [{"subdomain": s, "board": b, "name": n} for s, b, n in WORKDAY_COMPANIES],
        "goldman_sachs": ["Goldman Sachs"],
        "oracle_hcm":    [n for _, _, n in ORACLE_HCM_COMPANIES],
        "deloitte":      ["Deloitte"],
    })


@app.get("/api/portal-jobs")
def api_portal_jobs():
    tracker = JobTracker()
    jobs = tracker.all_jobs()
    tracker.close()
    portal = [
        j for j in jobs
        if (j.get("source") or "").lower() in PORTAL_SOURCES
        and j.get("title") not in ("__repost__", "", None)
    ]
    if US_ONLY:
        portal = [j for j in portal if _is_us(j.get("location", ""))]
    portal.sort(
        key=lambda j: j.get("posted_at") or j.get("seen_at") or "",
        reverse=True,
    )
    return jsonify(portal)


# ── Workday scan ──────────────────────────────────────────────────────────

_wd_scan_lock = threading.Lock()
_wd_scan_state: dict = {"running": False, "added": 0, "error": None, "finished_at": None}


def _do_workday_scan(hours: float):
    global _wd_scan_state
    from sources.workday import fetch_workday_jobs
    from config import WORKDAY_COMPANIES
    import datetime
    from datetime import timedelta, timezone
    try:
        cutoff = datetime.datetime.now(timezone.utc) - timedelta(hours=hours)
        jobs = fetch_workday_jobs(WORKDAY_COMPANIES, cutoff)
        tracker = JobTracker()
        added = len(process_jobs(jobs, tracker, jd_check=False))
        tracker.close()
        _wd_scan_state.update(running=False, added=added, error=None,
                              finished_at=datetime.datetime.now().isoformat())
    except Exception as exc:
        _wd_scan_state.update(running=False, error=str(exc),
                              finished_at=datetime.datetime.now().isoformat())
    finally:
        _wd_scan_lock.release()


@app.post("/api/workday-scan")
def api_workday_scan():
    hours = float(request.json.get("hours", 24) if request.is_json else 24)
    if not _wd_scan_lock.acquire(blocking=False):
        return jsonify({"error": "Workday scan already running"}), 409
    _wd_scan_state.update(running=True, added=0, error=None, finished_at=None)
    threading.Thread(target=_do_workday_scan, args=(hours,), daemon=True).start()
    return jsonify({"started": True, "hours": hours})


@app.get("/api/workday-scan/status")
def api_workday_scan_status():
    return jsonify(_wd_scan_state)


# ── Resume tailoring ──────────────────────────────────────────────────────

@app.post("/api/jobs/<job_id>/tailor")
def api_tailor(job_id: str):
    from tailoring.jd_fetcher import fetch_jd
    from tailoring.tailor import tailor_resume
    from tailoring.compiler import save_and_compile

    tracker = JobTracker()
    job = next((j for j in tracker.all_jobs() if j["job_id"] == job_id), None)
    tracker.close()
    if not job:
        return jsonify({"error": "Job not found"}), 404

    jd = fetch_jd(job["url"])
    try:
        latex, score = tailor_resume(jd, job["company"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    result = save_and_compile(latex, job["company"])

    tex_name = Path(result["tex_path"]).name
    pdf_name = Path(result["pdf_path"]).name if result.get("pdf_path") else None

    return jsonify({
        "score":    score,
        "tex_file": tex_name,
        "pdf_file": pdf_name,
        "error":    result.get("error"),
    })


@app.get("/api/download/<filename>")
def api_download(filename: str):
    # Guard against path traversal
    if any(c in filename for c in ("/", "\\", "..")):
        return "Invalid filename", 400
    filepath = Path("C:/Users/ameya/Downloads") / filename
    if not filepath.exists():
        return "Not found", 404
    return send_file(str(filepath), as_attachment=True, download_name=filename)


# ── Dashboard ──────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html")


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    parser = argparse.ArgumentParser()
    # PORT env var lets the preview panel assign a port; default stays 5000
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)s  %(message)s")
    app.run(host=args.host, port=args.port, debug=False)
