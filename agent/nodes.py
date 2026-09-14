"""
Graph nodes. Each is a pure state -> partial-state function, traced in Opik.

Ranking is heuristic-first (the existing ranking.match_score) with an
optional LLM pass that adds a fit reason and an honest gap. Tailoring is
grounded in the CV corpus and checked by the deterministic validator, which
can send it back for a bounded number of retries.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Annotated, Any, TypedDict

from .corpus import load_corpus
from .llm import backend, complete
from .tracing import log_metric, traced
from .validator import validate_bullets

log = logging.getLogger(__name__)

MAX_RANK_CANDIDATES = 25      # jobs sent to the LLM reranker per run


def _extract_json_array(raw: str) -> list:
    """
    Parse a JSON array out of an LLM response.

    The model reliably wraps output in a ```json fence and sometimes adds a
    sentence before it, so strip fences first and fall back to a bracket scan.
    Raises ValueError with the offending text so callers can surface it.
    """
    if not raw:
        raise ValueError("empty response")
    text = raw.strip()

    # ```json ... ``` or ``` ... ```
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if fence:
        text = fence.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            raise ValueError(f"no JSON array found in: {raw[:200]!r}")
        data = json.loads(m.group(0))

    if not isinstance(data, list):
        raise ValueError(f"expected a JSON array, got {type(data).__name__}")
    return data


class AgentState(TypedDict, total=False):
    # inputs
    jobs: list[dict]
    selected_job: dict | None
    target_bullets: int
    max_retries: int
    # working
    corpus: list[Any]
    ranked: list[dict]
    tailored: list[str]
    validation: dict | None
    attempts: int          # tailor passes made; retries done == attempts - 1
    notes: Annotated[list[str], lambda a, b: (a or []) + (b or [])]


# ── nodes ─────────────────────────────────────────────────────────────────

@traced("load_corpus")
def load_corpus_node(state: AgentState) -> AgentState:
    items = load_corpus()
    log_metric("corpus_items", len(items))
    return {"corpus": items, "notes": [f"corpus: {len(items)} items"]}


@traced("rank_jobs")
def rank_jobs_node(state: AgentState) -> AgentState:
    from ranking import match_score

    jobs = state.get("jobs") or []
    for j in jobs:
        j.setdefault("match", match_score(j))
    ranked = sorted(jobs, key=lambda j: -(j.get("match") or 0))
    log_metric("jobs_ranked", len(ranked))

    top = ranked[:MAX_RANK_CANDIDATES]
    if backend() == "none" or not top:
        return {"ranked": ranked,
                "notes": [f"ranked {len(ranked)} jobs (heuristic only)"]}

    listing = "\n".join(
        f"{i}. {j.get('title','?')} @ {j.get('company','?')} "
        f"[{j.get('location','?')}] heuristic={j.get('match')}"
        for i, j in enumerate(top)
    )

    # Ground the profile in the actual corpus rather than a hardcoded blurb.
    # Without this the model invents gaps that contradict real experience
    # (e.g. calling pharma "unfamiliar" despite the Boehringer Ingelheim role).
    corpus = state.get("corpus") or []
    if corpus:
        history = "\n".join(
            f"- {it.org} ({it.period}, {it.role}): {it.text}"
            for it in corpus if "WORK" in it.section.upper()
        )
        profile = f"CANDIDATE EXPERIENCE (the ground truth):\n{history}\n"
    else:
        profile = ("CANDIDATE: ~2-3 years in data science, ML and GenAI "
                   "engineering (LangChain RAG, PySpark, SQL, Tableau).\n")

    system = (
        f"{profile}\n"
        "The candidate has ~2-3 years of experience, needs H-1B sponsorship, "
        "and is based in Boston but open to relocation. Assess job fit against "
        "the experience above. Be blunt about real gaps, but do NOT claim a "
        "domain is unfamiliar if the experience above covers it. Never inflate fit."
    )
    user = (
        f"Jobs:\n{listing}\n\n"
        "Return ONLY a JSON array. One object per job index you assessed:\n"
        '[{"i":0,"fit":78,"reason":"<12 words>","gap":"<12 words or empty>"}]\n'
        "fit is 0-100. Prefer roles matching the candidate's level; penalise "
        "staffing-agency reposts and senior-only roles."
    )
    raw = complete(system, user)
    applied = 0
    note = ""
    try:
        for row in _extract_json_array(raw):
            i = int(row.get("i", -1))
            if 0 <= i < len(top):
                fit = row.get("fit")
                if isinstance(fit, (int, float)):
                    # blend: heuristic is the prior, LLM adjusts
                    top[i]["match"] = round(0.5 * top[i]["match"] + 0.5 * float(fit))
                top[i]["fit_reason"] = (row.get("reason") or "")[:90]
                top[i]["fit_gap"] = (row.get("gap") or "")[:90]
                applied += 1
    except Exception as e:
        # Surface this: an unparseable response must not look like "nothing to do"
        note = f" (LLM output unparseable: {e})"
        log.warning(f"rank_jobs: {e}")

    ranked = sorted(jobs, key=lambda j: -(j.get("match") or 0))
    log_metric("llm_reranked", applied)
    return {"ranked": ranked,
            "notes": [f"ranked {len(ranked)} jobs, LLM reasoned over {applied}{note}"]}


@traced("tailor")
def tailor_node(state: AgentState) -> AgentState:
    job = state.get("selected_job") or {}
    corpus = state.get("corpus") or []
    want = state.get("target_bullets", 5)
    prior = state.get("validation")
    attempt = state.get("attempts", 0) + 1

    # Work-experience items are what gets rewritten; projects stay as-is
    work = [it for it in corpus if "WORK" in it.section.upper()] or corpus

    if backend() == "none":
        bullets = [it.text for it in work[:want]]
        return {"tailored": bullets, "attempts": attempt,
                "notes": [f"tailor: corpus-verbatim ({len(bullets)} bullets, no LLM)"]}

    inventory = "\n".join(f"- [{it.id}] ({it.org}) {it.text}" for it in work)
    jd = (job.get("jd") or job.get("description") or "").strip()[:3000]

    feedback = ""
    if prior and not prior.get("ok"):
        issues = "\n".join(
            f"- {f['kind']}: {f['detail']}" for f in prior.get("findings", [])
        )
        feedback = (
            "\n\nYour previous attempt FAILED validation. Fix exactly these "
            f"problems and change nothing else:\n{issues}\n"
            "Use ONLY numbers that appear verbatim in the inventory above, and "
            "name ONLY technologies that appear there."
        )

    system = (
        "You rewrite resume bullets to match a job description. Hard rules:\n"
        "- Reframe existing facts only. Never invent work, metrics or tools.\n"
        "- Every number must appear verbatim in the provided inventory.\n"
        "- Only name technologies that appear in the inventory.\n"
        "- One sentence per bullet, 20-30 words, past-tense, measurable outcome.\n"
        "- Never begin a bullet with: Wrote, Maintained, Conducted, Delivered, Presented.\n"
        "- No em dashes."
    )
    user = (
        f"TARGET ROLE: {job.get('title','?')} at {job.get('company','?')}\n"
        f"JOB DESCRIPTION:\n{jd or '(not available - use the title)'}\n\n"
        f"BULLET INVENTORY (the only facts you may use):\n{inventory}\n\n"
        f"Rewrite {want} bullets aimed at this role. Return ONLY a JSON array "
        'of objects: [{"source_id":"<id from inventory>","text":"<bullet>"}]'
        f"{feedback}"
    )

    raw = complete(system, user)
    bullets: list[str] = []
    try:
        for row in _extract_json_array(raw):
            t = (row.get("text") or "").strip()
            if t:
                bullets.append(t)
    except Exception as e:
        log.warning(f"tailor: {e}")

    if not bullets:      # LLM unusable this pass - fall back, stay honest
        bullets = [it.text for it in work[:want]]
        return {"tailored": bullets, "attempts": attempt,
                "notes": ["tailor: LLM output unusable, fell back to corpus text"]}

    log_metric("bullets_generated", len(bullets))
    return {"tailored": bullets[:want], "attempts": attempt,
            "notes": [f"tailor: {len(bullets[:want])} bullets (attempt {attempt})"]}


@traced("validate_tailoring")
def validate_node(state: AgentState) -> AgentState:
    bullets = state.get("tailored") or []
    corpus = state.get("corpus") or []
    report = validate_bullets(bullets, corpus)
    log_metric("validation_ok", report.ok)
    log_metric("fabrication_findings", len(report.errors))
    return {"validation": report.as_dict(),
            "notes": [f"validate: {report.summary()}"]}


# ── conditional edges ─────────────────────────────────────────────────────

def route_entry(state: AgentState) -> str:
    """Discovery run, or tailoring run for one selected job."""
    return "tailor" if state.get("selected_job") else "rank"


def route_after_validate(state: AgentState) -> str:
    """Retry tailoring while the validator still finds fabrication."""
    report = state.get("validation") or {}
    if report.get("ok"):
        return "done"
    retries_done = max(0, state.get("attempts", 1) - 1)
    if retries_done >= state.get("max_retries", 2):
        log.warning("validation still failing at retry cap - returning flagged output")
        return "done"
    return "retry"
