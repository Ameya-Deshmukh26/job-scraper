"""
Google for Jobs (SerpApi) tests. No network and no key: _search is stubbed.

Every search is a paid credit, so the budget guards matter as much as the
parsing: the cap, stopping on a stale page, and doing nothing without a key.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402
import sources.google_jobs as gj  # noqa: E402


def _job(n: int, posted: str, apply=None, company="Acme") -> dict:
    return {
        "title": f"Data Scientist {n}",
        "company_name": company,
        "location": "Atlanta, GA",
        "job_id": f"job-{n}",
        "share_link": f"https://www.google.com/search?ibp=htl;jobs&htidocid={n}",
        "detected_extensions": {"posted_at": posted, "salary": "90K-110K a year"},
        "apply_options": apply if apply is not None else
            [{"title": "Acme Careers", "link": f"https://careers.acme.com/jobs/{n}"}],
    }


def _stub(monkeypatch, pages):
    """pages(query, call_no) -> SerpApi-shaped dict. Returns the call log."""
    calls = []

    def fake_search(key, query, token):
        calls.append((query, token))
        return pages(query, len(calls))

    monkeypatch.setattr(gj, "_search", fake_search)
    monkeypatch.setattr(gj, "api_key", lambda: "test-key")
    return calls


# ── parsing ───────────────────────────────────────────────────────────────

def test_posted_at_strings_become_times():
    now = datetime.now(timezone.utc)
    assert abs((now - gj._posted_to_dt("3 hours ago")) - timedelta(hours=3)) < timedelta(seconds=5)
    assert abs((now - gj._posted_to_dt("2 days ago")) - timedelta(days=2)) < timedelta(seconds=5)
    assert abs((now - gj._posted_to_dt("30+ days ago")) - timedelta(days=30)) < timedelta(seconds=5)
    assert abs((now - gj._posted_to_dt("45 minutes ago")) - timedelta(minutes=45)) < timedelta(seconds=5)
    assert gj._posted_to_dt("") is None
    assert gj._posted_to_dt("Full-time") is None


def test_employer_link_beats_aggregators():
    job = _job(1, "1 hour ago", apply=[
        {"title": "LinkedIn", "link": "https://www.linkedin.com/jobs/view/1"},
        {"title": "Indeed", "link": "https://www.indeed.com/viewjob?jk=abc"},
        {"title": "Acme", "link": "https://jobs.acme.com/1"},
    ])
    assert gj._best_apply_link(job) == ("https://jobs.acme.com/1", "Acme")


def test_aggregator_used_when_it_is_the_only_option():
    job = _job(1, "1 hour ago", apply=[
        {"title": "Glassdoor", "link": "https://www.glassdoor.com/job/1"}])
    assert gj._best_apply_link(job)[0] == "https://www.glassdoor.com/job/1"


def test_share_link_is_the_last_resort():
    job = _job(7, "1 hour ago", apply=[])
    assert gj._best_apply_link(job)[0].startswith("https://www.google.com/")


def test_subdomain_of_an_aggregator_is_still_an_aggregator():
    assert gj._is_aggregator("https://us.bebee.com/job/1")
    assert not gj._is_aggregator("https://notlinkedin.com/job/1")


# ── fetch behaviour and credit budget ─────────────────────────────────────

def test_no_key_means_no_searches(monkeypatch):
    calls = []
    monkeypatch.setattr(gj, "api_key", lambda: "")
    monkeypatch.setattr(gj, "_search", lambda *a: calls.append(a) or {})
    assert gj.fetch_google_jobs(datetime.now(timezone.utc)) == []
    assert calls == [], "spent a credit with no key configured"


def test_old_postings_are_dropped_and_fresh_kept(monkeypatch):
    _stub(monkeypatch, lambda q, n: {"jobs_results": [
        _job(n * 10 + 1, "2 hours ago"), _job(n * 10 + 2, "5 days ago")]})
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    jobs = gj.fetch_google_jobs(cutoff)

    assert jobs and all("Data Scientist" in j["title"] for j in jobs)
    assert all(j["posted_at"] for j in jobs)
    # only the "2 hours ago" posting from each page survives
    assert all(int(j["title"].split()[-1]) % 10 == 1 for j in jobs)
    j = jobs[0]
    assert j["source"] == "google_jobs"
    assert j["url"].startswith("https://careers.acme.com/")
    assert j["pay"] == "90K-110K a year"


def test_stops_paging_a_query_once_a_page_is_all_stale(monkeypatch):
    calls = _stub(monkeypatch, lambda q, n: {
        "jobs_results": [_job(n, "20 days ago")],
        "serpapi_pagination": {"next_page_token": f"tok{n}"}})
    gj.fetch_google_jobs(datetime.now(timezone.utc) - timedelta(hours=24))

    # one page per query: a stale first page must not buy page two
    assert [t for _, t in calls] == [None] * len(gj._QUERIES)


def test_follows_next_page_token_while_results_are_fresh(monkeypatch):
    calls = _stub(monkeypatch, lambda q, n: {
        "jobs_results": [_job(n, "1 hour ago")],
        "serpapi_pagination": {"next_page_token": f"tok{n}"}})
    gj.fetch_google_jobs(datetime.now(timezone.utc) - timedelta(hours=24))
    assert any(t for _, t in calls), "never requested a second page"


def test_search_cap_is_never_exceeded(monkeypatch):
    calls = _stub(monkeypatch, lambda q, n: {
        "jobs_results": [_job(n, "1 hour ago")],
        "serpapi_pagination": {"next_page_token": f"tok{n}"}})
    gj.fetch_google_jobs(datetime.now(timezone.utc) - timedelta(hours=24))
    assert len(calls) <= gj._MAX_SEARCHES


def test_same_posting_across_queries_is_kept_once(monkeypatch):
    _stub(monkeypatch, lambda q, n: {"jobs_results": [_job(1, "1 hour ago")]})
    jobs = gj.fetch_google_jobs(datetime.now(timezone.utc) - timedelta(hours=24))
    assert len(jobs) == 1


# ── integration with the scan engine ──────────────────────────────────────

def test_google_jobs_is_paid_and_never_joins_a_broad_scan():
    assert "google_jobs" in main.PAID_SOURCE_NAMES
    assert main.SOURCE_METHOD["google_jobs"] == "SerpApi (paid)"


# ── key lookup ────────────────────────────────────────────────────────────

def test_key_pasted_into_dotenv_is_seen_without_a_restart(monkeypatch, tmp_path):
    """The server loads .env once at startup; api_key() must re-read it."""
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("SERPAPI_API_KEY=\n", encoding="utf-8")
    monkeypatch.setattr(gj, "_DOTENV", env)
    monkeypatch.setattr(gj.os, "name", "posix")      # skip the registry fallback
    assert gj.api_key() == ""

    env.write_text("SERPAPI_API_KEY=abc123\n", encoding="utf-8")   # pasted later
    assert gj.api_key() == "abc123"


def test_real_environment_wins_over_dotenv(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("SERPAPI_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setattr(gj, "_DOTENV", env)
    monkeypatch.setenv("SERPAPI_API_KEY", "from-env")
    assert gj.api_key() == "from-env"


# ── apply-link ranking ────────────────────────────────────────────────────

def test_ats_link_beats_an_unknown_board():
    """A live run picked jobserve / career.io because they weren't blocklisted."""
    job = _job(1, "1 hour ago", company="Latitude", apply=[
        {"title": "JobServe", "link": "https://www.jobserve.com/us/en/extjob/1"},
        {"title": "SomeNewBoard", "link": "https://newjobboard.example/1"},
        {"title": "Greenhouse", "link": "https://job-boards.greenhouse.io/latitude/jobs/1"},
    ])
    assert "greenhouse.io" in gj._best_apply_link(job)[0]


def test_company_domain_counts_as_the_employer():
    job = _job(1, "1 hour ago", company="Purplle.com", apply=[
        {"title": "Naukri", "link": "https://www.naukri.com/job/1"},
        {"title": "Purplle", "link": "https://careers.purplle.com/jobs/1"},
    ])
    assert gj._best_apply_link(job)[0] == "https://careers.purplle.com/jobs/1"


def test_unknown_site_beats_a_known_board():
    job = _job(1, "1 hour ago", company="Acme", apply=[
        {"title": "LinkedIn", "link": "https://www.linkedin.com/jobs/view/1"},
        {"title": "Other", "link": "https://smallboard.example/1"},
    ])
    assert gj._best_apply_link(job)[0] == "https://smallboard.example/1"
