"""
One scan per dashboard tab. No network: the fetch and the tracker are stubbed.

Guards the rules the buttons rely on: each tab scans only its own sources,
paid sources run only when asked for and only with a key, the monthly HN
thread keeps its long lookback, and a second click joins the running scan.
"""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as dashboard  # noqa: E402


@pytest.fixture
def fake_scan(monkeypatch):
    """Record what each fetch was asked for; persist nothing."""
    calls = []

    def fake_fetch(cutoff, only=None, stats=None):
        calls.append({"only": set(only), "hours": (datetime.now(timezone.utc) - cutoff).total_seconds() / 3600})
        if stats is not None:
            stats.update({s: {"jobs": 1, "seconds": 0.1, "tasks": 1, "method": "test", "errors": 0}
                          for s in only})
        return [{"id": s} for s in only], {s: 1 for s in only}

    class FakeTracker:
        def close(self):
            pass

    monkeypatch.setattr(dashboard, "fetch_all_sources", fake_fetch)
    monkeypatch.setattr(dashboard, "process_jobs", lambda jobs, tracker: jobs)
    monkeypatch.setattr(dashboard, "JobTracker", FakeTracker)
    monkeypatch.setattr(dashboard, "_has_key", lambda src: True)
    return calls


def _wait(group, timeout=5):
    end = time.time() + timeout
    while dashboard._scan_state[group]["running"] and time.time() < end:
        time.sleep(0.02)
    assert not dashboard._scan_state[group]["running"], f"{group} scan never finished"
    return dashboard._scan_state[group]


def test_importing_the_app_starts_no_scans():
    import threading
    assert not any(t.name in ("auto-scan", "portal-auto") for t in threading.enumerate())


def test_linkedin_tab_scans_only_linkedin(fake_scan):
    assert dashboard._start_group("linkedin", 2, paid=False)
    st = _wait("linkedin")
    assert [c["only"] for c in fake_scan] == [{"linkedin"}]
    assert st["added"] == 1 and set(st["source_stats"]) == {"linkedin"}


def test_boards_tab_never_touches_paid_sources_or_linkedin(fake_scan):
    dashboard._start_group("boards", 2, paid=True)      # paid flag is irrelevant here
    _wait("boards")
    scanned = set().union(*(c["only"] for c in fake_scan))
    assert scanned == dashboard.SCAN_GROUPS["boards"]
    assert not scanned & {"linkedin", "google_jobs", "indeed", "workday"}


def test_hacker_news_keeps_its_monthly_lookback(fake_scan):
    dashboard._start_group("boards", 2, paid=False)
    _wait("boards")
    hn = next(c for c in fake_scan if c["only"] == {"hackernews"})
    rest = next(c for c in fake_scan if "greenhouse" in c["only"])
    assert hn["hours"] == pytest.approx(720, abs=0.1)
    assert rest["hours"] == pytest.approx(2, abs=0.1)


def test_big_tab_without_paid_runs_workday_only(fake_scan):
    dashboard._start_group("big", 2, paid=False)
    st = _wait("big")
    assert [c["only"] for c in fake_scan] == [{"workday"}]
    assert sorted(st["skipped"]) == ["google_jobs: paid, not run", "indeed: paid, not run",
                                     "ziprecruiter: paid, not run"]


def test_big_tab_with_paid_includes_sources_that_have_keys(fake_scan, monkeypatch):
    monkeypatch.setattr(dashboard, "_has_key", lambda src: src == "google_jobs")
    dashboard._start_group("big", 2, paid=True)
    st = _wait("big")
    assert fake_scan[0]["only"] == {"workday", "google_jobs"}
    assert st["skipped"] == ["indeed: no key in .env", "ziprecruiter: no key in .env"]


def test_a_second_click_joins_the_running_scan(fake_scan, monkeypatch):
    import threading
    release = threading.Event()
    real = dashboard.fetch_all_sources

    def slow(*a, **k):
        release.wait(2)
        return real(*a, **k)

    monkeypatch.setattr(dashboard, "fetch_all_sources", slow)
    c = dashboard.app.test_client()
    assert c.post("/api/group-scan/linkedin", json={"hours": 2}).status_code == 200
    again = c.post("/api/group-scan/linkedin", json={"hours": 2})
    assert again.status_code == 409 and again.get_json()["running"] is True
    release.set()
    _wait("linkedin")


def test_a_failed_scan_reports_the_error_and_frees_the_button(fake_scan, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(dashboard, "fetch_all_sources", boom)
    dashboard._start_group("linkedin", 2, paid=False)
    st = _wait("linkedin")
    assert st["error"] == "network down"
    assert dashboard._scan_locks["linkedin"].acquire(blocking=False), "lock was never released"
    dashboard._scan_locks["linkedin"].release()


def test_status_lists_every_tab_and_its_sources(fake_scan):
    d = dashboard.app.test_client().get("/api/group-scan/status").get_json()
    assert set(d["groups"]) == {"linkedin", "boards", "big"}
    assert d["sources"]["big"] == ["google_jobs", "indeed", "workday", "ziprecruiter"]
    assert set(d["paid_keys"]) == {"google_jobs", "indeed", "ziprecruiter"}


def test_unknown_group_is_rejected():
    assert dashboard.app.test_client().post("/api/group-scan/nope").status_code == 404
