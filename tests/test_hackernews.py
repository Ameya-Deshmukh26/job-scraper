"""
Hacker News "Who is hiring" source tests — no network.

The parser reads freeform comments, so the risk is precision, not plumbing.
An earlier version matched loose words ("AI", "analytics") and emitted junk
titles like "Ai" plus prose such as "Here's how we're thinking about AI at
Ashby". These tests pin the strict behaviour.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sources.hackernews as hn  # noqa: E402


# -- title extraction ------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Acme | Data Scientist | Remote", "Data Scientist"),
    ("Acme | Senior AI Engineer | NYC", "Senior AI Engineer"),
    ("Acme | Machine Learning Engineer | SF", "Machine Learning Engineer"),
    ("Acme | Analytics Engineer | Remote", "Analytics Engineer"),
    ("Acme | Data Engineer | Boston", "Data Engineer"),
    ("Acme | Research Scientist | Remote", "Research Scientist"),
])
def test_real_titles_are_matched(text, expected):
    assert hn._pick_role(text) == expected


@pytest.mark.parametrize("text", [
    "Here's how we're thinking about AI at Ashby",     # prose, not a role
    "Acme | Backend Engineer | SF",                    # wrong discipline
    "Acme | Product Designer | Remote",
    "We use AI to make analytics easy for everyone",   # loose words only
    "Our platform is powered by machine learning",     # no role noun
    "Acme | Account Executive | NYC",
])
def test_prose_and_irrelevant_roles_are_rejected(text):
    assert hn._pick_role(text) is None


def test_no_bare_ai_titles():
    """The old bug: 'Ai' as a job title."""
    for t in ["An AI company hiring now", "we love AI and data"]:
        assert hn._pick_role(t) not in ("Ai", "AI", "ai")


# -- company extraction ----------------------------------------------------

@pytest.mark.parametrize("text,html,expected", [
    ("Middesk | Data Scientist | NYC", 'href="https://middesk.com"', "Middesk"),
    ("Snout https://snout.com/ | Roles | Remote", 'href="https://snout.com/"', "Snout"),
    ("Sumble is the newco building infra | ML Engineer", 'href="https://x.com"', "Sumble"),
    ("Tonic AI  builds the platform | Data Scientist", 'href="https://y.com"', "Tonic AI"),
])
def test_company_is_trimmed_to_the_name(text, html, expected):
    assert hn._company_of(text, html) == expected


def test_company_falls_back_to_domain_when_segment_is_prose():
    got = hn._company_of("We are hiring several excellent people right now | Data Scientist",
                         'href="https://acmerobotics.com/careers"')
    assert got == "Acmerobotics"


def test_company_ignores_aggregator_domains():
    """Link-shortener / job-board domains are not the employer."""
    got = hn._company_of("Lots and lots of words that are clearly not a name here",
                         'href="https://grnh.se/abc123"')
    assert got == "Unknown"


# -- location extraction ---------------------------------------------------

def test_remote_wins():
    assert hn._location_of("Acme | Data Scientist | Remote US | Full Time") == "Remote"


def test_location_never_echoes_the_title():
    """Regression: location came back as 'Senior AI Engine' / 'Machine Learning'."""
    loc = hn._location_of("Gauss Labs | Senior AI Engineer | Palo Alto, CA")
    assert "Engineer" not in loc
    assert hn._TITLE_RE.search(loc) is None


def test_location_skips_employment_type():
    loc = hn._location_of("Acme | Data Scientist | Full Time | Boston, MA")
    assert "Full" not in loc


def test_location_unknown_is_labelled():
    assert hn._location_of("Acme | Data Scientist") == "Unspecified"


# -- thread selection ------------------------------------------------------

def test_only_who_is_hiring_threads_are_used(monkeypatch):
    """'Who wants to be hired' is the candidates thread, not the jobs thread."""
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"hits": [
                {"objectID": "1", "title": "Ask HN: Who wants to be hired? (August 2026)"},
                {"objectID": "2", "title": "Ask HN: Who is hiring? (August 2026)"},
            ]}
    monkeypatch.setattr(hn._SESSION, "get", lambda *a, **k: R())
    assert hn._newest_thread()["objectID"] == "2"


def test_thread_listing_failure_returns_no_jobs(monkeypatch):
    monkeypatch.setattr(hn, "_newest_thread", lambda: None)
    from datetime import datetime, timezone
    assert hn.fetch_hackernews_jobs(datetime.now(timezone.utc)) == []


# -- startup registry (startups.py) ----------------------------------------

def test_startup_registry_matches_slug_and_display_name():
    import startups
    startups.reload_registry()
    reg = startups.registry()
    if not reg:
        pytest.skip("no data/board_probe.json; run discover_boards.py --probe")
    # slug form and display-name form must resolve to the same company
    a = startups.annotate({"company": "nox-metals", "source": "ashby"})
    b = startups.annotate({"company": "Nox Metals", "source": "hiringcafe"})
    assert a["is_startup"] and b["is_startup"]
    assert a["yc_batch"] == b["yc_batch"]


def test_startup_sources_are_always_startups():
    import startups
    j = startups.annotate({"company": "Some Unknown Co", "source": "hackernews"})
    assert j["is_startup"] is True


def test_big_company_is_not_a_startup():
    import startups
    j = startups.annotate({"company": "JPMorgan Chase", "source": "oracle_hcm"})
    assert j["is_startup"] is False
    assert j["yc_batch"] is None


def test_annotate_always_sets_the_three_fields():
    import startups
    j = startups.annotate({"company": "Whatever", "source": "workday"})
    for k in ("is_startup", "yc_batch", "team_size"):
        assert k in j


def _registry_or_skip():
    import startups
    startups.reload_registry()
    if not startups.registry():
        pytest.skip("no data/board_probe.json; run discover_boards.py --probe")
    return startups


def test_large_yc_alumni_are_not_startups():
    """
    YC alumni never stop being YC companies, but Stripe (7,000 staff),
    Checkr (800) and Benchling (750) are not startups. The badge is only
    useful if it means "small company".
    """
    startups = _registry_or_skip()
    for co in ("stripe", "checkr", "benchling"):
        j = startups.annotate({"company": co, "source": "greenhouse"})
        assert j["is_startup"] is False, f"{co} (team {j['team_size']}) tagged as startup"
        assert j["yc_batch"], f"{co} should still expose its YC batch"


def test_small_yc_companies_are_startups():
    startups = _registry_or_skip()
    for co in ("agentmail", "twenty", "avoca"):
        j = startups.annotate({"company": co, "source": "ashby"})
        assert j["is_startup"] is True, f"{co} should be a startup"
        assert j["team_size"] <= startups.MAX_TEAM
