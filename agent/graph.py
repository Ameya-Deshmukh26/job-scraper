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
                                        |            |   (retry: validator
                                      refuse        END   found fabrication)
                                        |
                                       END

Two entry paths and one self-correcting cycle. The validator is the loop
condition, so the agent cannot exit while it is still fabricating. At the
retry cap it routes to `refuse`, which discards the text entirely and
returns the reason: anything handed back will be pasted, so the only safe
failure mode is returning nothing. Pass strict=False to get flagged text.
"""
from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from .llm import MODEL, backend
from .nodes import (
    AgentState,
    load_corpus_node,
    rank_jobs_node,
    refuse_node,
    route_after_validate,
    route_entry,
    tailor_node,
    validate_node,
)
from .tracing import run_traced

log = logging.getLogger(__name__)


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("load_corpus", load_corpus_node)
    g.add_node("rank_jobs", rank_jobs_node)
    g.add_node("tailor", tailor_node)
    g.add_node("validate_tailoring", validate_node)
    g.add_node("refuse", refuse_node)

    g.add_edge(START, "load_corpus")
    g.add_conditional_edges(
        "load_corpus", route_entry,
        {"rank": "rank_jobs", "tailor": "tailor"},
    )
    g.add_edge("rank_jobs", END)
    g.add_edge("tailor", "validate_tailoring")
    g.add_conditional_edges(
        "validate_tailoring", route_after_validate,
        {"retry": "tailor", "refuse": "refuse", "done": END},
    )
    g.add_edge("refuse", END)
    return g.compile()


GRAPH = build_graph()


# ── convenience wrappers ──────────────────────────────────────────────────

def rank(jobs: list[dict]) -> list[dict]:
    """Discovery path: score and order jobs, with LLM reasoning when available."""
    return rank_with_notes(jobs)[0]


def rank_with_notes(jobs: list[dict]) -> tuple[list[dict], list[str]]:
    """Same as rank(), but also returns the run's notes for API surfacing."""
    out = run_traced(
        "agent.rank",
        lambda: GRAPH.invoke({"jobs": jobs, "notes": []}),
        candidates=len(jobs), model=MODEL, backend=backend(),
    )
    notes = out.get("notes", [])
    for note in notes:
        log.info(f"  {note}")
    return out.get("ranked", []), notes


def tailor(job: dict, target_bullets: int = 5, max_retries: int = 2,
           strict: bool = True) -> dict:
    """
    Tailoring path: rewrite bullets for one job, validated and retried.

    strict=True (the default) means output that still fails validation at the
    retry cap is refused: `bullets` comes back empty with `refused` set and a
    reason. Pass strict=False to receive the flagged text instead.

    Returns {bullets, validation, notes, refused, refusal_reason}.
    """
    out = run_traced(
        "agent.tailor",
        lambda: GRAPH.invoke({
            "jobs": [],
            "selected_job": job,
            "target_bullets": target_bullets,
            "max_retries": max_retries,
            "attempts": 0,
            "strict": strict,
            "notes": [],
        }),
        job_title=job.get("title", ""), company=job.get("company", ""),
        target_bullets=target_bullets, max_retries=max_retries,
        strict=strict, model=MODEL, backend=backend(),
    )
    for note in out.get("notes", []):
        log.info(f"  {note}")
    return {
        "bullets": out.get("tailored", []),
        "validation": out.get("validation"),
        "notes": out.get("notes", []),
        "refused": bool(out.get("refused")),
        "refusal_reason": out.get("refusal_reason", ""),
    }


def mermaid() -> str:
    """Graph topology as mermaid - handy for the README and interviews."""
    try:
        return GRAPH.get_graph().draw_mermaid()
    except Exception as e:
        return f"(could not render: {e})"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

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
