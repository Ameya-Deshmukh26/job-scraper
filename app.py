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
from main import (run_once, _is_us, _is_blocked, _is_right_level,
                  fetch_all_sources, process_jobs)
from tracker import JobTracker
from sources.h1b import is_h1b_sponsor
from startups import annotate as annotate_startup
from ranking import is_staffing

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
    # Saved jobs get today's title rules too: many were saved before a level
    # word or a blocked employer was added. Applied jobs always stay visible.
    jobs = [j for j in jobs if j.get("applied")
            or (_is_right_level(j.get("title", "")) and not _is_blocked(j.get("company", "")))]
    # Tag each job with H-1B sponsor status (cached lookup, fast)
    from ranking import match_score
    for j in jobs:
        j["h1b_sponsor"] = is_h1b_sponsor(j.get("company", ""))
        j["match"] = match_score(j)
        annotate_startup(j)
        # Staffing/contract shops are ranked down, so flag them explicitly:
        # contract roles matter for STEM OPT (needs a paid E-Verify employer).
        j["is_staffing"] = is_staffing(j.get("company"))
    return jsonify(jobs)


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


# ── Scans: one per dashboard tab ───────────────────────────────────────────
# Every tab's Scan button runs one group of sources through fetch_all_sources,
# so each gets the same parallel fetch, filters, dedup and per-source timing.
# "All" on the dashboard starts every group.

SCAN_GROUPS: dict[str, set[str]] = {
    "linkedin": {"linkedin"},
    "boards":   {"greenhouse", "lever", "ashby", "faang", "goldman_sachs",
                 "deloitte", "hackernews", "staffing"},
    "big":      {"workday", "google_jobs", "indeed"},
}
_PAID_SOURCES = {"google_jobs": "SERPAPI_API_KEY", "indeed": "FIRECRAWL_API_KEY"}
_HN_LOOKBACK_H = 720      # the Who-is-hiring thread is monthly

_AUTO_INTERVAL = 3600     # background scan every hour...
_AUTO_LOOKBACK = 2.0      # ...looking back 2 hours
_auto_next: list[float | None] = [None]

_scan_locks = {g: threading.Lock() for g in SCAN_GROUPS}
_scan_state: dict[str, dict] = {
    g: {"running": False, "added": 0, "fetched": 0, "error": None,
        "started_at": None, "finished_at": None, "hours": None,
        "source_stats": {}, "skipped": []}
    for g in SCAN_GROUPS
}


def _has_key(source: str) -> bool:
    if source == "google_jobs":
        from sources.google_jobs import api_key   # also re-reads .env
        return bool(api_key())
    import os
    return bool(os.environ.get(_PAID_SOURCES[source]))


def _run_group(group: str, hours: float, paid: bool):
    """Body of one group scan. The caller already holds the group's lock."""
    import datetime as _dt
    from datetime import timedelta, timezone

    state = _scan_state[group]
    try:
        sources = set(SCAN_GROUPS[group])
        skipped = []
        for src in sorted(sources & set(_PAID_SOURCES)):
            if not paid:
                sources.discard(src)
                skipped.append(f"{src}: paid, not run")
            elif not _has_key(src):
                sources.discard(src)
                skipped.append(f"{src}: no key in .env")

        now = _dt.datetime.now(timezone.utc)
        stats: dict = {}
        jobs: list[dict] = []
        regular = sources - {"hackernews"}
        if regular:
            got, _ = fetch_all_sources(now - timedelta(hours=hours), only=regular, stats=stats)
            jobs += got
        if "hackernews" in sources:
            hn: dict = {}
            got, _ = fetch_all_sources(now - timedelta(hours=max(hours, _HN_LOOKBACK_H)),
                                       only={"hackernews"}, stats=hn)
            jobs += got
            stats.update(hn)

        tracker = JobTracker()
        added = len(process_jobs(jobs, tracker))
        tracker.close()
        state.update(added=added, fetched=len(jobs), source_stats=stats,
                     skipped=skipped, error=None)
    except Exception as exc:
        log.exception(f"{group} scan failed")
        state.update(error=str(exc))
    finally:
        state.update(running=False, finished_at=_dt.datetime.now().isoformat())
        _scan_locks[group].release()


def _start_group(group: str, hours: float, paid: bool) -> bool:
    """Start a group scan in the background. False if that group is already running."""
    import datetime as _dt
    if not _scan_locks[group].acquire(blocking=False):
        return False
    _scan_state[group].update(running=True, added=0, fetched=0, error=None, skipped=[],
                              hours=hours, started_at=_dt.datetime.now().isoformat(),
                              finished_at=None)
    threading.Thread(target=_run_group, args=(group, hours, paid), daemon=True,
                     name=f"scan-{group}").start()
    return True


def _auto_loop():
    """
    Hourly background scan of every free source except LinkedIn: the Boards
    group, plus Workday from the Workday + Google tab. Paid sources and
    LinkedIn only run when their button is clicked.
    """
    while True:
        _start_group("boards", _AUTO_LOOKBACK, paid=False)
        _start_group("big", _AUTO_LOOKBACK, paid=False)
        wake_at = time.time() + _AUTO_INTERVAL
        _auto_next[0] = wake_at
        while time.time() < wake_at:
            time.sleep(10)


def start_auto_scan():
    """Start the hourly background scan. Called when the dashboard launches,
    not at import, so importing app (tests, scripts) never starts scans."""
    threading.Thread(target=_auto_loop, daemon=True, name="auto-scan").start()


@app.post("/api/group-scan/<group>")
def api_group_scan(group: str):
    if group not in SCAN_GROUPS:
        return jsonify({"error": f"unknown scan group {group!r}"}), 404
    body = request.get_json(silent=True) or {}
    hours = float(body.get("hours", 2))
    paid = bool(body.get("paid", False))
    if not _start_group(group, hours, paid):
        return jsonify({"error": f"{group} scan already running", "running": True}), 409
    return jsonify({"started": True, "group": group, "hours": hours, "paid": paid})


@app.get("/api/group-scan/status")
def api_group_scan_status():
    return jsonify({
        "groups":       {g: dict(st) for g, st in _scan_state.items()},
        "sources":      {g: sorted(srcs) for g, srcs in SCAN_GROUPS.items()},
        "next_auto_at": _auto_next[0],
        "interval_seconds": _AUTO_INTERVAL,
        "paid_keys":    {src: _has_key(src) for src in _PAID_SOURCES},
    })


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
    from tailoring.compiler import OUTPUT_DIR
    filepath = OUTPUT_DIR / filename
    if not filepath.exists():
        return "Not found", 404
    return send_file(str(filepath), as_attachment=True, download_name=filename)


# ── Dashboard ──────────────────────────────────────────────────────────────

@app.get("/")
def index():
    from config import (MAX_YEARS_REQUIRED, NEEDS_SPONSORSHIP, SETUP_DONE,
                        US_ONLY, YOUR_NAME)
    name = YOUR_NAME.strip() or "Job Search"
    return render_template("index.html", user_name=name,
                           user_first=name.split()[0],
                           needs_sponsorship=NEEDS_SPONSORSHIP,
                           us_only=US_ONLY, max_years=MAX_YEARS_REQUIRED,
                           setup_done=SETUP_DONE)


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
    start_auto_scan()
    app.run(host=args.host, port=args.port, debug=False)
