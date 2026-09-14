"""
LinkedIn source tests — no network (the session is stubbed).

Chiefly guards two things that were got wrong before:
  1. f_TPR must be derived from the cutoff, in seconds, clamped to 1h-24h
  2. jobs must NOT be dropped by an absolute job-ID gap heuristic. Measured
     evidence: inside one f_TPR=r3600 window the ID span was ~82M and a
     posting LinkedIn labelled "Just now" sat 82M below the batch max, so any
     absolute threshold deletes brand-new jobs.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sources.linkedin as li  # noqa: E402


def _card(jid: str, title: str, company: str, age: str = "1 hour ago",
          date: str = "2026-08-12") -> str:
    return f"""
    <li><div class="base-card" data-entity-urn="urn:li:jobPosting:{jid}">
      <h3 class="base-search-card__title">{title}</h3>
      <h4 class="base-search-card__subtitle">{company}</h4>
      <span class="job-search-card__location">Boston, MA</span>
      <time datetime="{date}">{age}</time>
    </div></li>"""


class FakeResp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


@pytest.fixture
def captured(monkeypatch):
    """Stub the session; record every request's params and URL."""
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params or {}})
        # Easy-Apply probe returns a disjoint set so nothing is subtracted
        if (params or {}).get("f_AL") == "true":
            return FakeResp(_card("9999", "Easy Job", "EasyCo"))
        if (params or {}).get("start", 0) >= 25:
            return FakeResp("")          # page 2 empty -> stop paging
        return FakeResp(
            _card("4453331917", "Data Analyst", "FreshCo", "Just now")
            + _card("4371331917", "Data Scientist", "OldIdCo", "Just now")
        )

    monkeypatch.setattr(li._SESSION, "get", fake_get)
    monkeypatch.setattr(li, "_QUERIES", ["data analyst"])
    monkeypatch.setattr(li.time, "sleep", lambda *_: None)
    return calls


# ── f_TPR derivation ──────────────────────────────────────────────────────

@pytest.mark.parametrize("hours,expected", [
    (1, "r3600"),
    (2, "r7200"),
    (24, "r86400"),
    (0.25, "r3600"),    # clamped up to the 1h floor
    (72, "r86400"),     # clamped down to the 24h ceiling
])
def test_f_tpr_derived_from_cutoff(captured, hours, expected):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    li.fetch_linkedin_jobs(cutoff)
    tprs = {c["params"].get("f_TPR") for c in captured}
    assert tprs == {expected}, f"{hours}h should map to {expected}, got {tprs}"


def test_f_tpr_r3600_is_actually_sent(captured):
    """The 1-hour case specifically — this is the one reported as broken."""
    li.fetch_linkedin_jobs(datetime.now(timezone.utc) - timedelta(hours=1))
    assert all(c["params"]["f_TPR"] == "r3600" for c in captured)
    assert captured, "no requests were made"


# ── endpoint handling ─────────────────────────────────────────────────────

def test_uses_search_results_endpoint(captured):
    li.fetch_linkedin_jobs(datetime.now(timezone.utc) - timedelta(hours=1))
    assert any("search-results" in c["url"] for c in captured)


def test_falls_back_when_primary_endpoint_fails(monkeypatch):
    """A 404 on one path must transparently fall through to the other."""
    seen = []

    def fake_get(url, params=None, timeout=None):
        seen.append(url)
        if url.endswith("search-results"):
            return FakeResp("nope", status=404)
        if (params or {}).get("f_AL") == "true":
            return FakeResp(_card("9999", "Easy Job", "EasyCo"))   # disjoint set
        if (params or {}).get("start", 0) >= 25:
            return FakeResp("")
        return FakeResp(_card("4453331917", "Data Analyst", "FreshCo"))

    monkeypatch.setattr(li._SESSION, "get", fake_get)
    monkeypatch.setattr(li, "_QUERIES", ["data analyst"])
    monkeypatch.setattr(li.time, "sleep", lambda *_: None)
    monkeypatch.setattr(li, "_SEARCH_URL", li._SEARCH_URLS[0])

    jobs = li.fetch_linkedin_jobs(datetime.now(timezone.utc) - timedelta(hours=1))
    assert any(u.endswith("/search") for u in seen), "never tried the fallback path"
    assert jobs, "fallback endpoint returned data but no jobs were parsed"


def test_all_endpoints_failing_returns_empty_not_crash(monkeypatch):
    monkeypatch.setattr(li._SESSION, "get",
                        lambda url, params=None, timeout=None: FakeResp("", status=999))
    monkeypatch.setattr(li, "_QUERIES", ["data analyst"])
    monkeypatch.setattr(li.time, "sleep", lambda *_: None)
    assert li.fetch_linkedin_jobs(datetime.now(timezone.utc) - timedelta(hours=1)) == []


# ── the removed heuristic must stay removed ───────────────────────────────

def test_old_job_id_is_not_dropped(captured):
    """
    Regression: 'OldIdCo' has an ID ~82M below the newest in the same batch,
    which the deleted heuristic would have discarded, even though LinkedIn
    reports it as "Just now". Both jobs must survive.
    """
    jobs = li.fetch_linkedin_jobs(datetime.now(timezone.utc) - timedelta(hours=1))
    companies = {j["company"] for j in jobs}
    assert "FreshCo" in companies
    assert "OldIdCo" in companies, "stale-ID heuristic appears to have come back"


def test_no_absolute_id_gap_threshold_in_source():
    """Belt and braces: the magic constant must not reappear."""
    src = Path(li.__file__).read_text(encoding="utf-8")
    assert "_ID_GAP_THRESHOLD" not in src
    assert "40_000_000" not in src


# ── parsing / filtering that must keep working ────────────────────────────

def test_easy_apply_ids_are_excluded(monkeypatch):
    """A job appearing in the f_AL=true set must be dropped."""
    def fake_get(url, params=None, timeout=None):
        if (params or {}).get("start", 0) >= 25:
            return FakeResp("")
        # same id in both the Easy-Apply probe and the main listing
        return FakeResp(_card("555", "Data Analyst", "EasyOnly"))

    monkeypatch.setattr(li._SESSION, "get", fake_get)
    monkeypatch.setattr(li, "_QUERIES", ["data analyst"])
    monkeypatch.setattr(li.time, "sleep", lambda *_: None)
    assert li.fetch_linkedin_jobs(datetime.now(timezone.utc) - timedelta(hours=1)) == []


def test_reposted_marker_is_dropped(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        if (params or {}).get("f_AL") == "true":
            return FakeResp(_card("9999", "Easy", "EasyCo"))
        if (params or {}).get("start", 0) >= 25:
            return FakeResp("")
        return FakeResp(_card("4453331917", "Data Analyst", "RepostCo",
                              age="Reposted 3 hours ago"))

    monkeypatch.setattr(li._SESSION, "get", fake_get)
    monkeypatch.setattr(li, "_QUERIES", ["data analyst"])
    monkeypatch.setattr(li.time, "sleep", lambda *_: None)
    jobs = li.fetch_linkedin_jobs(datetime.now(timezone.utc) - timedelta(hours=1))
    assert jobs == [], "a card marked 'Reposted' should be skipped"


def test_job_fields_are_parsed(captured):
    jobs = li.fetch_linkedin_jobs(datetime.now(timezone.utc) - timedelta(hours=1))
    j = next(x for x in jobs if x["company"] == "FreshCo")
    assert j["id"] == "li_4453331917"
    assert j["source"] == "LinkedIn"
    assert j["title"] == "Data Analyst"
    assert j["url"] == "https://www.linkedin.com/jobs/view/4453331917"
    assert j["posted_at"] == "2026-08-12"
