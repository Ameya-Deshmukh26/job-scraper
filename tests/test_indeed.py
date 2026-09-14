"""
Indeed source tests — no network.

Guards the bug where the extractor returned job_key with a literal "jk="
prefix, producing links like ...viewjob?jk=jk=abc123 (two '=' signs), and the
related case where it invented a slug instead of a real 16-hex job key.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sources.indeed as ind  # noqa: E402


# ── job key normalisation ─────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("8dfcd548a3e8b162",     "8dfcd548a3e8b162"),   # already clean
    ("jk=8dfcd548a3e8b162",  "8dfcd548a3e8b162"),   # the reported bug
    ("JK=8dfcd548a3e8b162",  "8dfcd548a3e8b162"),   # case-insensitive
    ("?jk=8dfcd548a3e8b162", "8dfcd548a3e8b162"),
    ("&jk=8dfcd548a3e8b162", "8dfcd548a3e8b162"),
    ("jk=jk=8dfcd548a3e8b162", "8dfcd548a3e8b162"), # doubled prefix
    ("  8dfcd548a3e8b162  ", "8dfcd548a3e8b162"),
    ('"8dfcd548a3e8b162"',   "8dfcd548a3e8b162"),
    ("8dfcd548a3e8b162&from=x", "8dfcd548a3e8b162"),
])
def test_clean_jk_normalises(raw, expected):
    assert ind._clean_jk(raw) == expected


@pytest.mark.parametrize("raw", [
    "", "   ", None,
    "not_available", "N/A", "none", "null", "unknown",
    "snowflake-data-engineer",      # invented slug, not a real key
    "jk=snowflake-data-engineer",
    "zzzz",                         # too short
    "not-hex-at-all-here-ok",       # non-hex
    # Real fabrications found in the DB - the model invented all of these
    "abcde12345",                   # 10 hex chars, plausible but wrong length
    "X-URL-1", "not_provided", "unique_key_1", "upcoming-id-here",
    "DataEngineer_Chicago", "Data Engineer", "19", "xyz123464",
    "0ff8eef0369b51a",              # 15 chars - one short
    "0ff8eef0369b51ac1",            # 17 chars - one long
])
def test_clean_jk_rejects_untrustworthy(raw):
    assert ind._clean_jk(raw) is None


# ── URL construction ──────────────────────────────────────────────────────

def _run_with(jobs, monkeypatch):
    monkeypatch.setattr(ind, "_scrape", lambda q, l, d: jobs)
    monkeypatch.setattr(ind, "_QUERIES", ["data scientist"])
    monkeypatch.setattr(ind, "_LOCATIONS", ["Boston, MA"])
    return ind.fetch_indeed_jobs(datetime.now(timezone.utc) - timedelta(days=1))


def test_prefixed_job_key_yields_single_equals(monkeypatch):
    out = _run_with([{"title": "Data Scientist", "company": "Pfizer",
                      "job_key": "jk=0ff8eef0369b51ac"}], monkeypatch)
    url = out[0]["url"]
    assert url == "https://www.indeed.com/viewjob?jk=0ff8eef0369b51ac"
    assert url.count("=") == 1, f"malformed link: {url}"
    assert "jk=jk" not in url


def test_clean_job_key_unchanged(monkeypatch):
    out = _run_with([{"title": "MLE", "company": "Chewy",
                      "job_key": "8dfcd548a3e8b162"}], monkeypatch)
    assert out[0]["url"].endswith("?jk=8dfcd548a3e8b162")
    assert out[0]["id"] == "indeed_8dfcd548a3e8b162"


def test_invalid_job_key_falls_back_to_search(monkeypatch):
    """An invented slug must not become a dead viewjob link."""
    out = _run_with([{"title": "Snowflake Data Engineer", "company": "Robert Half",
                      "job_key": "snowflake-data-engineer"}], monkeypatch)
    url = out[0]["url"]
    assert "viewjob" not in url
    assert url.startswith("https://www.indeed.com/jobs?q=")
    assert "Snowflake" in url


def test_missing_job_key_falls_back_to_search(monkeypatch):
    out = _run_with([{"title": "Data Analyst", "company": "Acme"}], monkeypatch)
    assert out[0]["url"].startswith("https://www.indeed.com/jobs?q=")


def test_no_stored_url_has_double_equals(monkeypatch):
    """Whole-batch invariant across every job_key shape we have seen."""
    out = _run_with([
        {"title": "A", "company": "C1", "job_key": "jk=0ff8eef0369b51ac"},
        {"title": "B", "company": "C2", "job_key": "8dfcd548a3e8b162"},
        {"title": "C", "company": "C3", "job_key": "not_available"},
        {"title": "D", "company": "C4", "job_key": "invented-slug-here"},
        {"title": "E", "company": "C5"},
    ], monkeypatch)
    for j in out:
        assert "jk=jk" not in j["url"], j["url"]
        if "viewjob" in j["url"]:
            assert j["url"].count("=") == 1, j["url"]


def test_dedup_across_prefixed_and_clean_keys(monkeypatch):
    """'jk=abc' and 'abc' are the same job and must collapse to one row."""
    out = _run_with([
        {"title": "Data Scientist", "company": "Pfizer", "job_key": "jk=0ff8eef0369b51ac"},
        {"title": "Data Scientist", "company": "Pfizer", "job_key": "0ff8eef0369b51ac"},
    ], monkeypatch)
    assert len(out) == 1


# ── misc ──────────────────────────────────────────────────────────────────

def test_rows_missing_title_or_company_are_skipped(monkeypatch):
    out = _run_with([{"title": "", "company": "X", "job_key": "8dfcd548a3e8b162"},
                     {"title": "Y", "company": "", "job_key": "8dfcd548a3e8b163"}],
                    monkeypatch)
    assert out == []


def test_posted_relative_ages_parse():
    assert ind._posted_to_iso("Just posted")
    assert ind._posted_to_iso("Posted 3 days ago")
    assert ind._posted_to_iso("not_available") == ""
    assert ind._posted_to_iso("") == ""
