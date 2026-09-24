"""
Per-source latency stats — no network (the fetchers are stubbed).

These guard the reporting layer that answers "which source is eating the
scan budget", after a live scan showed Workday taking 790s of a ~1400s run.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


def test_every_scanned_source_has_a_method():
    """
    A source missing from SOURCE_METHOD renders as "unknown" in the dashboard
    and falls out of the method buckets, so the totals silently stop adding up.
    """
    known = set(main.SOURCE_METHOD)
    missing = (main.PORTAL_SOURCE_NAMES | main.PAID_SOURCE_NAMES) - known
    assert not missing, f"sources with no access method declared: {sorted(missing)}"


def test_stats_report_time_jobs_and_request_count(monkeypatch):
    """stats= fills in per-source detail without changing the return shape."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)

    def fake_greenhouse(company, _cutoff):
        return [{"title": f"Job at {company}"}]

    monkeypatch.setattr(main, "fetch_greenhouse_jobs", fake_greenhouse)
    monkeypatch.setattr(main, "GREENHOUSE_COMPANIES", ["a", "b", "c"])

    stats = {}
    jobs, counts = main.fetch_all_sources(cutoff, only={"greenhouse"}, stats=stats)

    assert len(jobs) == 3
    assert counts == {"greenhouse": 3}

    gh = stats["greenhouse"]
    assert gh["jobs"] == 3
    assert gh["tasks"] == 3          # one request per company, not one per source
    assert gh["errors"] == 0
    assert gh["method"] == "REST API"
    assert gh["seconds"] >= 0


def test_a_failing_source_is_counted_not_swallowed(monkeypatch):
    """
    A source that throws must report its errors and still cost visible time.
    Silently returning zero jobs is how a dead source hides for weeks.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)

    def boom(company, _cutoff):
        raise RuntimeError("board is down")

    monkeypatch.setattr(main, "fetch_lever_jobs", boom)
    monkeypatch.setattr(main, "LEVER_COMPANIES", ["x", "y"])

    stats = {}
    jobs, counts = main.fetch_all_sources(cutoff, only={"lever"}, stats=stats)

    assert jobs == []
    assert stats["lever"]["errors"] == 2
    assert stats["lever"]["tasks"] == 2
    assert stats["lever"]["jobs"] == 0


def test_stats_is_optional():
    """Callers that only want counts must not be forced to pass a dict."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    jobs, counts = main.fetch_all_sources(cutoff, only=set())
    assert jobs == [] and counts == {}


def test_paid_sources_stay_out_of_a_broad_scan():
    """Indeed costs Firecrawl credits, so it must never join an unnamed scan."""
    assert "indeed" in main.PAID_SOURCE_NAMES
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    _, counts = main.fetch_all_sources(cutoff, only=set())
    assert "indeed" not in counts
