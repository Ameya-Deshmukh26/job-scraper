"""
Agent tests — no network, no LLM, no API keys required.

The load-bearing test is test_retry_loop_fires_on_fabrication: it proves the
graph cannot exit while the validator is still finding invented facts.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import nodes  # noqa: E402
from agent.corpus import corpus_numbers, load_corpus, numbers_in, strip_tex  # noqa: E402
from agent.graph import build_graph  # noqa: E402
from agent.nodes import _extract_json_array, route_after_validate, route_entry  # noqa: E402
from agent.validator import validate_bullets  # noqa: E402


@pytest.fixture(scope="module")
def corpus():
    return load_corpus()


# ── corpus ────────────────────────────────────────────────────────────────

def test_corpus_parses_all_bullets(corpus):
    assert len(corpus) >= 15
    assert all(it.text for it in corpus)
    assert all(it.id for it in corpus)


def test_corpus_has_work_and_projects(corpus):
    sections = {it.section for it in corpus}
    assert any("WORK" in s.upper() for s in sections)
    assert any("PROJECT" in s.upper() for s in sections)


def test_corpus_extracts_real_metrics(corpus):
    nums = corpus_numbers(corpus)
    for known in {"500+", "60%", "2M+", "40%", "89%"}:
        assert known in nums, f"{known} missing from corpus metrics"


def test_strip_tex_removes_markup():
    assert strip_tex(r"Served \textbf{500+ users} with \textbf{60\%} gain") == \
        "Served 500+ users with 60% gain"


@pytest.mark.parametrize("text,expected", [
    ("serving 500+ users", "500+"),
    ("60% latency reduction", "60%"),
    ("processing 2M+ records", "2M+"),
    ("0.21 validation loss", "0.21"),
])
def test_numbers_in_extracts_claims(text, expected):
    assert expected in numbers_in(text)


# ── validator ─────────────────────────────────────────────────────────────

def test_validator_passes_grounded_bullets(corpus):
    rep = validate_bullets([
        "Deployed production RAG pipeline using LangChain and OpenAI API serving "
        "500+ users with 60% latency reduction.",
    ], corpus)
    assert rep.ok, rep.summary()
    assert rep.provenance


def test_validator_catches_invented_metrics(corpus):
    rep = validate_bullets([
        "Deployed RAG pipeline serving 5000+ users with 95% latency reduction.",
    ], corpus)
    assert not rep.ok
    assert any(f.kind == "fabricated_metric" for f in rep.errors)


def test_validator_catches_skill_inflation(corpus):
    """
    Terraform and Kafka appear nowhere in the base resume, so naming them is
    inflation. (Kubernetes was used here originally, but the base resume now
    genuinely lists it, which correctly stopped being a finding.)
    """
    rep = validate_bullets([
        "Built Terraform modules and Kafka streaming across production clusters.",
    ], corpus)
    assert not rep.ok
    assert any(f.kind == "skill_inflation" for f in rep.errors)


def test_validator_allows_skills_section_tech(corpus):
    """Snowflake is in TECHNICAL SKILLS, so naming it is not inflation."""
    rep = validate_bullets([
        "Designed dbt data models in PostgreSQL and Snowflake improving KPIs 12%.",
    ], corpus)
    assert not any(f.kind == "skill_inflation" for f in rep.errors), rep.summary()


def test_validator_flags_unsupported_claim(corpus):
    rep = validate_bullets(["Managed vendor procurement and office relocation logistics."], corpus)
    assert not rep.ok


def test_validator_records_thresholds(corpus):
    rep = validate_bullets(["anything"], corpus)
    assert "provenance_floor" in rep.thresholds
    assert rep.thresholds["corpus_items"] == len(corpus)


def test_validator_report_is_serializable(corpus):
    import json
    rep = validate_bullets(["Deployed RAG pipeline serving 9999+ users."], corpus)
    json.dumps(rep.as_dict())      # must not raise


# ── LLM output parsing ────────────────────────────────────────────────────
# Regression: the model wraps JSON in a ```json fence, which silently produced
# "assessed: 0" runs that were indistinguishable from having nothing to do.

def test_extract_json_from_markdown_fence():
    raw = '```json\n[{"i":0,"fit":68,"reason":"good fit"}]\n```'
    assert _extract_json_array(raw)[0]["fit"] == 68


def test_extract_json_from_bare_array():
    assert _extract_json_array('[{"i":1,"fit":40}]')[0]["i"] == 1


def test_extract_json_with_prose_preamble():
    raw = 'Here is my assessment:\n```json\n[{"i":0,"fit":50}]\n```\nHope that helps.'
    assert _extract_json_array(raw)[0]["fit"] == 50


def test_extract_json_multiline_real_response():
    """The exact shape observed from the live model, including newlines."""
    raw = ('```json\n[{"i":0,"fit":68,"reason":"DS/SQL fit good","gap":"H-1B uncertain"},\n'
           '{"i":1,"fit":32,"reason":"Staffing repost","gap":"rarely sponsor"}]\n```')
    rows = _extract_json_array(raw)
    assert len(rows) == 2 and rows[1]["fit"] == 32


@pytest.mark.parametrize("bad", ["", None, "no array here", "{\"i\": 0}"])
def test_extract_json_raises_on_unusable(bad):
    with pytest.raises(ValueError):
        _extract_json_array(bad)


# ── routing ───────────────────────────────────────────────────────────────

def test_route_entry_picks_rank_without_selection():
    assert route_entry({"jobs": [{"title": "x"}]}) == "rank"


def test_route_entry_picks_tailor_with_selection():
    assert route_entry({"selected_job": {"title": "x"}}) == "tailor"


def test_route_after_validate_done_when_clean():
    assert route_after_validate({"validation": {"ok": True}, "attempts": 1}) == "done"


def test_route_after_validate_retries_when_dirty():
    assert route_after_validate(
        {"validation": {"ok": False}, "attempts": 1, "max_retries": 2}) == "retry"


def test_route_after_validate_stops_at_cap():
    assert route_after_validate(
        {"validation": {"ok": False}, "attempts": 3, "max_retries": 2}) == "done"


# ── graph ─────────────────────────────────────────────────────────────────

def test_rank_path_orders_by_match(monkeypatch):
    monkeypatch.setattr(nodes, "backend", lambda: "none")
    graph = build_graph()
    out = graph.invoke({"jobs": [
        {"title": "Data Analyst", "company": "Staffing Agency LLC",
         "location": "Remote", "source": "linkedin", "seen_at": ""},
        {"title": "Machine Learning Engineer", "company": "Anthropic",
         "location": "Boston, MA", "source": "greenhouse", "seen_at": "",
         "h1b_sponsor": True},
    ], "notes": []})
    ranked = out["ranked"]
    assert len(ranked) == 2
    assert ranked[0]["company"] == "Anthropic", "better job should rank first"
    assert ranked[0]["match"] >= ranked[1]["match"]


def test_tailor_path_produces_validated_bullets(monkeypatch):
    monkeypatch.setattr(nodes, "backend", lambda: "none")
    graph = build_graph()
    out = graph.invoke({
        "jobs": [], "selected_job": {"title": "Data Scientist", "company": "Chewy"},
        "target_bullets": 3, "max_retries": 2, "attempts": 0, "notes": [],
    })
    assert len(out["tailored"]) == 3
    assert out["validation"]["ok"] is True


def test_retry_loop_fires_on_fabrication(monkeypatch):
    """
    The agent must not be able to exit while fabricating. Feed it a tailor
    step that always invents a metric and assert it burns its retries and
    returns the output flagged rather than clean.
    """
    calls = {"n": 0}

    def fabricating_complete(system, user):
        calls["n"] += 1
        return ('[{"source_id":"boehringer-ingelheim-0",'
                '"text":"Deployed RAG pipeline serving 7777+ users with 99% uplift."}]')

    monkeypatch.setattr(nodes, "backend", lambda: "sdk")
    monkeypatch.setattr(nodes, "complete", fabricating_complete)

    graph = build_graph()
    out = graph.invoke({
        "jobs": [], "selected_job": {"title": "Data Scientist", "company": "X"},
        "target_bullets": 1, "max_retries": 2, "attempts": 0, "notes": [],
    })

    assert calls["n"] >= 3, f"expected initial + 2 retries, got {calls['n']}"
    assert out["validation"]["ok"] is False
    kinds = {f["kind"] for f in out["validation"]["findings"]}
    assert "fabricated_metric" in kinds


def test_graph_compiles_and_has_expected_nodes():
    g = build_graph().get_graph()
    names = set(g.nodes)
    for n in {"load_corpus", "rank_jobs", "tailor", "validate_tailoring"}:
        assert n in names
