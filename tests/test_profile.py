"""
Profile-driven behaviour and the portable build. No network.

The app used to assume one person (US, data roles, 5-year cap). These guard
the pieces that let someone else use it: the configurable experience cap,
the staffing exemptions that matter for an Indian job search, and the build
checks that keep keys and personal details out of the shared zip.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402
import make_portable as mp  # noqa: E402
from ranking import is_staffing  # noqa: E402


# ── experience cap ────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, too_senior", [
    ("5+ years of experience in data science", True),
    ("3+ years of experience", False),
    ("2-5 years of experience", False),          # the lower bound counts
    ("5-8 years of relevant experience", True),
    ("minimum of 6 years experience", True),
    ("at least 4 years of experience", False),
    ("3 to 5 years of experience", True),         # previous behaviour, kept
    ("10+ years of professional experience", True),
    ("1-3 years of experience with SQL", False),
])
def test_default_cap_of_five_matches_the_old_regex(text, too_senior):
    assert bool(main.too_senior(text, 5)) is too_senior


def test_cap_is_configurable():
    jd = "Looking for 3+ years of experience in product management."
    assert main.too_senior(jd, 5) is None
    assert main.too_senior(jd, 3) == "3+ years of experience"


def test_the_matched_phrase_is_returned_for_the_audit_log():
    assert main.too_senior("We need at least 7 years of experience.", 5) == \
        "at least 7 years of experience"


# ── staffing tells ────────────────────────────────────────────────────────

def test_staffing_exemptions_come_from_the_profile(monkeypatch):
    """NOT_STAFFING empty keeps the original flag; listing a company exempts it."""
    import ranking
    monkeypatch.setattr(ranking, "_NOT_STAFFING", [])
    assert is_staffing("Tata Consultancy Services")          # original behaviour
    monkeypatch.setattr(ranking, "_NOT_STAFFING", ["tata consultancy"])
    assert not is_staffing("Tata Consultancy Services")


@pytest.mark.parametrize("company", ["Infosys", "Accenture", "Boston Consulting Group"])
def test_large_direct_employers_are_not_staffing(company):
    assert not is_staffing(company)


@pytest.mark.parametrize("company", [
    "ABC Staffing Solutions", "Pinnacle Consultancy Services", "Robert Half Talent",
])
def test_agencies_are_still_flagged(company):
    assert is_staffing(company)


# ── portable build checks ─────────────────────────────────────────────────

_STARTER = ('SETUP_DONE = False\nSEARCH_TITLES = ["Product Manager"]\n'
            'KEYWORDS = ["product manager"]\nLOCATION_FILTER = ["india"]\n'
            'EXCLUDE_LEVELS = ["director"]\nENABLE_AUTO_APPLY = False\n')


@pytest.fixture
def fake_build(tmp_path, monkeypatch):
    """A minimal build folder that passes verify() until something is planted."""
    (tmp_path / "search_profile.py").write_text(_STARTER, encoding="utf-8")
    (tmp_path / ".env").write_text("SERPAPI_API_KEY=\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("Copyright (c) 2026 Ameya Deshmukh\n", encoding="utf-8")
    monkeypatch.setattr(mp, "BUILD", tmp_path)
    monkeypatch.setattr(mp, "real_key_values", lambda: {"SERPAPI_API_KEY": "real-key-abcdef123456"})
    return tmp_path


def _files(root):
    return [str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if p.is_file()]


def test_clean_build_passes(fake_build):
    assert mp.verify(_files(fake_build)) == []


def test_build_rejects_this_machines_key(fake_build):
    (fake_build / "app.py").write_text("K = 'real-key-abcdef123456'\n", encoding="utf-8")
    problems = mp.verify(_files(fake_build))
    assert any("SERPAPI_API_KEY" in p for p in problems)
    assert not any("real-key-abcdef123456" in p for p in problems), "leaked the value in the report"


def test_build_rejects_credential_shaped_strings(fake_build):
    (fake_build / "x.py").write_text("K = 'fc-" + "a1" * 16 + "'\n", encoding="utf-8")
    assert any("Firecrawl" in p for p in mp.verify(_files(fake_build)))


def test_build_rejects_personal_details_outside_the_license(fake_build):
    (fake_build / "x.py").write_text("P = 'C:/Users/someone/resume.tex'\n", encoding="utf-8")
    assert any("personal detail" in p for p in mp.verify(_files(fake_build)))


def test_build_rejects_a_filled_env(fake_build):
    (fake_build / ".env").write_text("SERPAPI_API_KEY=something\n", encoding="utf-8")
    assert any(".env" in p for p in mp.verify(_files(fake_build)))


def test_build_rejects_a_profile_that_skips_setup(fake_build):
    (fake_build / "search_profile.py").write_text(
        _STARTER.replace("SETUP_DONE = False", "SETUP_DONE = True"), encoding="utf-8")
    assert any("SETUP_DONE" in p for p in mp.verify(_files(fake_build)))


def test_build_rejects_an_empty_search(fake_build):
    """An empty starter profile ships a dashboard that finds nothing."""
    (fake_build / "search_profile.py").write_text(
        _STARTER.replace('["Product Manager"]', "[]"), encoding="utf-8")
    assert any("SEARCH_TITLES is empty" in p for p in mp.verify(_files(fake_build)))


def test_build_rejects_a_bare_manager_exclusion(fake_build):
    (fake_build / "search_profile.py").write_text(
        _STARTER.replace('["director"]', '["director", "manager"]'), encoding="utf-8")
    assert any("manager" in p for p in mp.verify(_files(fake_build)))


def test_build_rejects_databases_and_logs(fake_build):
    (fake_build / "seen_jobs.db").write_bytes(b"SQLite format 3\x00")
    assert any("must not ship" in p for p in mp.verify(_files(fake_build)))


def test_shipped_starter_profile_searches_mba_roles_in_india():
    starter: dict = {}
    exec((mp.PORTABLE / "search_profile.py").read_text(encoding="utf-8"), starter)
    assert starter["SETUP_DONE"] is False
    assert starter["ENABLE_AUTO_APPLY"] is False
    assert starter["SEARCH_COUNTRY"] == "India"
    assert "Associate Product Manager" in starter["SEARCH_TITLES"]
    assert "manager" not in starter["EXCLUDE_LEVELS"]
    assert not starter["NEEDS_SPONSORSHIP"]


# ── title level check: whole words, from live misses (Sept 2026) ──────────

@pytest.mark.parametrize("title", [
    "Staff, Data Scientist",                       # "staff " with a space missed the comma
    "VP Fraud Risk Business Analytics Lead",        # " vp" needed a leading space
    "Lead Treasury Quantitative Analytics (VP)",
    "Lead Machine Learning Engineer",               # only "lead ml" / "lead data" were listed
    "Data Science Lead",
    "Data Scientist III",
    "Analytics and AI Solution Architect",
    "GHR AI Engineer - Agentic Integrations AVP",
    "Data Scientist, Sr.",
])
def test_senior_titles_that_used_to_slip_through_are_caught(title):
    assert not main._is_right_level(title)


@pytest.mark.parametrize("title", [
    "Data Scientist", "Data Analyst II", "Staffing Data Analyst", "Machine Learning Engineer",
    "Software Engineer, AI (Multiple Seniority Levels)",   # "senior" inside "seniority"
])
def test_whole_word_matching_leaves_junior_titles_alone(title):
    assert main._is_right_level(title)


def test_blocked_employers_are_dropped():
    assert main._is_blocked("SynergisticIT")
    assert not main._is_blocked("Synergy Health")


def test_a_job_failing_the_years_check_is_saved_hidden(monkeypatch):
    """It used to be saved unflagged, so the dashboard showed it anyway."""
    saved, flagged = [], {}

    class T:
        def seen(self, _):
            return False

        def seen_by_title_company(self, *_):
            return False

        def mark_seen(self, job):
            saved.append(job["id"])

        def mark_needs_review(self, job_id, reason):
            flagged[job_id] = reason

    monkeypatch.setattr(main, "_jd_ok_for_experience", lambda url: url != "https://senior")
    jobs = [{"id": "a", "title": "Data Scientist", "company": "Acme", "location": "Boston, MA", "url": "https://ok"},
            {"id": "b", "title": "Data Analyst", "company": "Acme", "location": "Boston, MA", "url": "https://senior"}]
    new = main.process_jobs(jobs, T())
    assert [j["id"] for j in new] == ["a"]
    assert saved == ["a", "b"]                      # both saved, so neither is re-checked
    assert flagged == {"b": f"requires {main.MAX_YEARS_REQUIRED}+ years experience"}


def test_no_preferred_locations_means_location_never_moves_the_score(monkeypatch):
    """Relocates anywhere: Boston, Atlanta and Remote score the same."""
    import ranking
    monkeypatch.setattr(ranking, "_PREFERRED", [])
    base = {"title": "Data Scientist", "company": "Acme", "source": "greenhouse"}
    scores = {loc: ranking.match_score({**base, "location": loc})
              for loc in ["Boston, MA", "Atlanta, GA", "Remote", "United States"]}
    assert len(set(scores.values())) == 1, scores
