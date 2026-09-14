# Job Scout Agent

A LangGraph agent that ranks scraped job postings against a candidate profile
and rewrites resume bullets for a target role, with a **deterministic
fabrication validator** in the loop so the agent cannot ship invented claims.

Built on top of a job scraper that pulls from 13+ ATS sources
(LinkedIn guest API, Ashby GraphQL, Workday CXS, Oracle HCM, Avature,
Greenhouse, Lever, Amazon/Netflix career APIs, HiringCafe, RemoteOK) and
tracks ~3,000 postings in SQLite.

## Graph

```
load_corpus
     |
route_entry ──────────────────────────────┐
     │ (no job selected)                  │ (job selected)
     ▼                                    ▼
rank_jobs                              tailor ◄──────────────┐
     │                                    │                  │
    END                          validate_tailoring           │
                                          │                  │
                                route_after_validate ─────────┘
                                          │       retry: validator
                                         END       found fabrication
```

Two entry paths and one self-correcting cycle. The validator is the loop
condition, so the graph cannot reach `END` while it is still fabricating —
up to `max_retries`, after which output is returned **flagged** rather than
silently accepted.

## The validator (`validator.py`)

Zero LLM calls. Three independent checks per bullet:

| Check | Rule |
|---|---|
| `unsupported_claim` | bullet must match a corpus item above a similarity floor |
| `fabricated_metric` | every number must already appear in the base resume |
| `skill_inflation` | every technology named must appear in the base resume |

Metric lock is the important one: an LLM asked to "make this sound stronger"
will quietly turn `500+ users` into `5,000+ users`. That is caught
mechanically, not by asking the model to behave.

Thresholds are tunable and **recorded in every report**, so a run is
reproducible and auditable:

```json
{"ok": false,
 "thresholds": {"provenance_floor": 0.34, "strict_metrics": true,
                "corpus_items": 15, "legit_numbers": 20},
 "provenance": {"0": "boehringer-ingelheim-0 (1.00)"},
 "findings": [{"kind": "fabricated_metric", "severity": "error",
               "detail": "numbers not in corpus: ['5000+', '95%']"}]}
```

## Corpus (`corpus.py`)

The base LaTeX resume is parsed into typed, addressable `CorpusItem`s
(id, section, org, role, period, text, numbers). Tailoring may only reframe
these items — nothing is generated from scratch, which is what makes
fabrication a *checkable property* rather than a hope.

## LLM backend (`llm.py`)

Resolved at runtime, in priority order:

1. **`sdk`** — `claude-agent-sdk` driving the Claude Code CLI; reuses the
   existing subscription/SSO login, no API key
2. **`api`** — `ANTHROPIC_API_KEY` via `langchain-anthropic`
3. **`none`** — no LLM; ranking falls back to the heuristic scorer and
   tailoring returns corpus text verbatim

The graph runs end to end under all three. Only ranking *reasoning* and
bullet *rewriting* quality change, which keeps the whole thing testable with
no credentials.

## Observability (`tracing.py`)

Every node is wrapped in `@traced`, emitting an Opik span with timing plus
metrics (`corpus_items`, `jobs_ranked`, `bullets_generated`,
`validation_ok`, `fabrication_findings`). No-ops cleanly when Opik is
unconfigured — and the credential check runs *before* the import, because
importing opik costs ~10s.

Self-hosted:
```bash
export OPIK_URL_OVERRIDE=http://localhost:5173/api
```

## Ranking (`nodes.py`)

Heuristic-first: the existing `ranking.match_score` (role fit, level,
staffing-agency penalty, H-1B sponsorship from USCIS data, location,
freshness) is the prior. An optional LLM pass adjusts the score 50/50 and
adds a one-line fit reason and an honest gap. The heuristic alone is a
usable product; the LLM is an enhancement, not a dependency.

## Usage

```python
from agent.graph import rank, tailor

ranked = rank(jobs)                      # discovery path
result = tailor({"title": ..., "company": ..., "jd": ...})
result["bullets"]      # grounded, validated bullets
result["validation"]   # full report with provenance
```

HTTP:
```
GET  /api/agent/status              # which backend + tracing are live
POST /api/agent/tailor/<job_id>     # bullets + validation report
```

## Tests

```bash
python -m pytest tests/test_agent.py -q     # 24 passed
```

No network, no LLM, no API keys. Covers corpus parsing, all three validator
checks (including the true-negative case where a skills-section technology
must *not* be flagged), both routing decisions, the retry cap, and an
end-to-end proof that a persistently-fabricating tailor step burns its
retries and exits flagged rather than clean.

## Design note

The agent does not submit applications. It ranks, explains gaps, and drafts
grounded materials; a human reviews and applies. Auto-submission is limited
to public Greenhouse/Lever forms in a separate module, deliberately outside
the agent's authority.
