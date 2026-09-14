"""
LangGraph wiring for the job agent.

    load_corpus
         |
    route_entry ------------------------------.
         |                                     |
      (rank)                                (tailor)
         |                                     |
    rank_jobs                              tailor  <---------.
         |                                     |              |
        END                              validate_tailoring   |
                                               |              |
                                     route_after_validate ----'
                                               |      (retry: validator
                                              END      found fabrication)

Two entry paths and one self-correcting cycle: the validator is the loop
condition, so the agent cannot exit while it is still fabricating (up to
max_retries, after which output is returned flagged rather than silently).
"""
from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from .nodes import (
    AgentState,
    load_corpus_node,
    rank_jobs_node,
    route_after_validate,
    route_entry,
    tailor_node,
    validate_node,
)

log = logging.getLogger(__name__)


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("load_corpus", load_corpus_node)
    g.add_node("rank_jobs", rank_jobs_node)
    g.add_node("tailor", tailor_node)
    g.add_node("validate_tailoring", validate_node)

    g.add_edge(START, "load_corpus")
    g.add_conditional_edges(
        "load_corpus", route_entry,
        {"rank": "rank_jobs", "tailor": "tailor"},
    )
    g.add_edge("rank_jobs", END)
    g.add_edge("tailor", "validate_tailoring")
    g.add_conditional_edges(
        "validate_tailoring", route_after_validate,
        {"retry": "tailor", "done": END},
    )
    return g.compile()


GRAPH = build_graph()


# ── convenience wrappers ──────────────────────────────────────────────────

def rank(jobs: list[dict]) -> list[dict]:
    """Discovery path: score and order jobs, with LLM reasoning when available."""
    return rank_with_notes(jobs)[0]


def rank_with_notes(jobs: list[dict]) -> tuple[list[dict], list[str]]:
    """Same as rank(), but also returns the run's notes for API surfacing."""
    out = GRAPH.invoke({"jobs": jobs, "notes": []})
    notes = out.get("notes", [])
    for note in notes:
        log.info(f"  {note}")
    return out.get("ranked", []), notes


def tailor(job: dict, target_bullets: int = 5, max_retries: int = 2) -> dict:
    """
    Tailoring path: rewrite bullets for one job, validated and retried.
    Returns {bullets, validation, notes}.
    """
    out = GRAPH.invoke({
        "jobs": [],
        "selected_job": job,
        "target_bullets": target_bullets,
        "max_retries": max_retries,
        "attempts": 0,
        "notes": [],
    })
    for note in out.get("notes", []):
        log.info(f"  {note}")
    return {
        "bullets": out.get("tailored", []),
        "validation": out.get("validation"),
        "notes": out.get("notes", []),
    }


def mermaid() -> str:
    """Graph topology as mermaid - handy for the README and interviews."""
    try:
        return GRAPH.get_graph().draw_mermaid()
    except Exception as e:
        return f"(could not render: {e})"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from .llm import backend

    print(f"backend: {backend()}\n")
    print(mermaid())

    print("\n=== tailor path ===")
    res = tailor({
        "title": "Data Scientist, Product Analytics",
        "company": "Whatnot",
        "jd": "Product analytics, experimentation and A/B testing, SQL, "
              "Python, building metrics and dashboards for a marketplace.",
    }, target_bullets=4)
    rep = res["validation"] or {}
    print(f"\nvalidation ok={rep.get('ok')} thresholds={rep.get('thresholds')}")
    for b in res["bullets"]:
        print(f"  - {b}")
    for f in rep.get("findings", []):
        print(f"  [{f['severity']}] {f['kind']}: {f['detail']}")
