# Job Scraper & Portal Radar

A real-time job aggregator that monitors company career portals and job boards for data / ML / AI engineering roles — and surfaces them before they hit LinkedIn.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?logo=flask)
![SQLite](https://img.shields.io/badge/SQLite-tracker-green?logo=sqlite)
![Sources](https://img.shields.io/badge/sources-10%2B-orange)

---

## Why?

By the time a job appears on LinkedIn, dozens of applications are already in. This tool scrapes **company portals directly** — Greenhouse, Lever, Ashby, Workday, and Goldman Sachs — and alerts you within minutes of a posting going live.

---

## Features

- **Multi-source scraping** - 293 company ATS boards (Greenhouse 173, Ashby 75, Lever 45) plus Workday, Oracle HCM, Avature, Goldman Sachs, Amazon/Netflix, LinkedIn, HiringCafe, Hacker News, Indeed
- **Automated board discovery** - probes Y Combinator's 6,175-company API against Greenhouse/Lever/Ashby to find live boards instead of guessing slugs, with a collision guard for generic names
- **H-1B sponsorship tagging** - every employer checked against USCIS Employer Data Hub (FY2021-23, ~44k employers); filter to sponsors only
- **Match scoring** - 0-100 per job from role fit, level, company type, sponsorship, location and freshness; sortable
- **LangGraph agent** - ranks jobs with reasoning and rewrites resume bullets, gated by a deterministic zero-LLM fabrication validator that blocks invented metrics and skill inflation
- **Live dashboard** (Flask) — two-tab UI: all sources feed + company portal radar
- **Portal Radar tab** — Workday Fortune 500 section first, Goldman Sachs section, then GH/Lever/Ashby; freshness badges (🔥 < 1h, ✨ 1–6h, 🔵 6–24h)
- **Auto-scan every hour** — background thread refreshes portal jobs; countdown timer in UI
- **Smart filtering** — keyword match on title, experience-level filter (excludes Staff/Principal/VP/Director), US-only location filter with 60+ international markers
- **Deduplication** — title+company dedup across runs so reposts don't surface twice
- **JD experience check** — fetches the job description and skips roles explicitly requiring 5+ years
- **Windows toast + Discord notifications** on new matches
- **Overnight / auto-apply mode** — runs every 2h overnight and submits Greenhouse/Lever forms automatically
- **Resume tailoring** — Claude-powered LaTeX resume tailoring per JD (via Anthropic API)

---

## Sources

| Source | Type | Coverage |
|---|---|---|
| Greenhouse | ATS API | 173 boards (auto-discovered + curated) |
| Ashby | GraphQL | 75 boards |
| Lever | ATS API | 45 boards |
| Workday | CXS JSON API | 30 Fortune 500 (Capital One, Walmart, Cisco, Citi, Wells Fargo, ...) |
| Oracle HCM | REST | JPMorgan, Goldman lateral, Amex, Oracle |
| Avature | HTML | Deloitte |
| Goldman Sachs | Custom GraphQL | `api-higher.gs.com` |
| Amazon / Netflix | Public JSON | amazon.jobs, Netflix Eightfold |
| LinkedIn | Guest API | Dynamic `f_TPR` window, Easy Apply excluded |
| HiringCafe | Public API + Playwright | Aggregator |
| Hacker News | Algolia API | Monthly "Who is hiring" thread, startup-heavy |
| Indeed | Firecrawl | Paid credits, opt-in only |

Google, Meta, Apple and Microsoft career APIs are bot-walled and deliberately
not attempted. Handshake requires SSO. Removed as unproductive: Adzuna,
Remotive, TheMuse, RemoteOK (zero jobs returned across the tracker's history).

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Ameya-Deshmukh26/job-scraper.git
cd job-scraper

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure keywords, companies, and optional API keys
#    Edit config.py

# 4. One-shot scan (last 6 hours)
python main.py

# 5. Continuous scan every 15 min
python main.py --loop

# 6. Launch the live dashboard
python app.py
# → open http://localhost:5000
```

---

## Configuration

Who is searching lives in **`search_profile.py`**; company board lists and
scan timing live in `config.py`. API keys go in `.env` (gitignored).

| Setting (`search_profile.py`) | Description |
|---|---|
| `SEARCH_TITLES` | Typed into every job site's search box |
| `KEYWORDS` | A title must contain one of these to be kept |
| `SEARCH_COUNTRY` | Country every source searches (see `COUNTRIES` in config.py) |
| `SEARCH_CITIES` | Cities for the paid Indeed search |
| `LOCATION_FILTER` / `US_ONLY` | Which locations are kept |
| `EXCLUDE_LEVELS` / `EXCLUDE_SENIOR` | Titles skipped as too senior |
| `MAX_YEARS_REQUIRED` | Skip jobs whose description asks for this many years or more |
| `RANK_*`, `PREFERRED_LOCATIONS` | Match-score tiers and boosts |
| `NEEDS_SPONSORSHIP` | H-1B tagging and scoring; off skips the USCIS download |
| `BASE_TEX_PATH` | LaTeX resume for tailoring ("" = `./resume.tex`) |

| Setting (`config.py`) | Description |
|---|---|
| `LOOKBACK_HOURS` | How far back each scan looks |
| `GREENHOUSE_COMPANIES`, `LEVER_COMPANIES`, `ASHBY_COMPANIES` | Board slugs |
| `WORKDAY_COMPANIES`, `ORACLE_HCM_COMPANIES` | `(host, board, name)` tuples |
| `DISCORD_WEBHOOK_URL` | Discord alerts (optional) |

## Sharing a copy

```
python make_portable.py
```

Builds `JobScout.zip` next to this repo for someone else to use. It contains
only git-tracked files, with a blank `search_profile.py`, an empty `.env`,
and a `CLAUDE.md` that has Claude Code run a guided setup (roles, cities,
experience, optional API keys) the first time the folder is opened. The
build refuses to zip if any file contains a key value from this machine, a
credential-shaped string, or personal details. The shipped setup files live
in `portable/`.

---|---|---|
| `KEYWORDS` | data analyst, ML engineer, … | Title must match at least one |
| `EXCLUDE_LEVELS` | staff, principal, director, … | Titles to skip |
| `EXCLUDE_SENIOR` | `True` | Also skip "Senior" roles |
| `US_ONLY` | `True` | Filter out non-US locations |
| `LOOKBACK_HOURS` | `6` | How far back each scan looks |
| `GREENHOUSE_COMPANIES` | 80+ | Greenhouse board tokens |
| `LEVER_COMPANIES` | 30+ | Lever slugs |
| `ASHBY_COMPANIES` | 30+ | Ashby slugs |
| `WORKDAY_COMPANIES` | 27 | `(subdomain, board, name)` tuples |
| `ANTHROPIC_API_KEY` | — | For resume tailoring (optional) |
| `DISCORD_WEBHOOK_URL` | — | For Discord alerts (optional) |
| `ADZUNA_APP_ID/KEY` | — | For Adzuna (optional) |

---

## Dashboard

```
python app.py      # then open http://localhost:5000
```

Four tabs, each with one **Scan** button. Every tab's scan runs its group of
sources through the same engine, so each shows per-source jobs and timing.

| Tab | Sources | Scan |
|---|---|---|
| **All** | every job, filterable by keyword / source / location | **Scan everything** runs the three below |
| **LinkedIn** | LinkedIn guest search (Easy Apply excluded) | free |
| **Boards** | Greenhouse, Lever, Ashby, Amazon/Netflix, Goldman, Oracle HCM, Deloitte, HN Who's Hiring, HiringCafe, Insight Global | free |
| **Workday + Google** | Workday career sites, Google Jobs (SerpApi), Indeed (Firecrawl) | asks before spending credits |

An hourly background scan covers Boards plus Workday, never LinkedIn or a paid
source. API: `POST /api/group-scan/<linkedin|boards|big>` with
`{"hours": 2, "paid": false}`, and `GET /api/group-scan/status`.

---

## Architecture

```
job_scraper/
├── main.py              # CLI entry point (one-shot / loop / overnight)
├── app.py               # Flask dashboard + portal scan API
├── config.py            # All configuration
├── tracker.py           # SQLite job tracker (seen_jobs.db)
├── notifier.py          # Windows toast + Discord notifications
├── sources/
│   ├── greenhouse.py    # Greenhouse public API
│   ├── lever.py         # Lever public API
│   ├── ashby.py         # Ashby public API
│   ├── workday.py       # Workday CXS undocumented JSON API
│   ├── goldman_sachs.py # Goldman Sachs GraphQL API (higher.gs.com)
│   ├── linkedin.py      # LinkedIn guest API
│   ├── remotive.py      # Remotive public API
│   ├── hiringcafe.py    # HiringCafe API
│   └── adzuna.py        # Adzuna REST API
├── tailoring/           # Claude-powered resume tailoring
├── autoapply/           # Overnight auto-apply runner
└── templates/
    └── index.html       # Dashboard UI (Vanilla JS + CSS)
```

---

## Workday Company List

All 27 entries confirmed HTTP 200 against the Workday CXS API:

CVS Health · Cigna · Humana · Pfizer · Johnson & Johnson · Nationwide · Travelers · PayPal · Capital One · Morgan Stanley · Visa · Wells Fargo · Bank of America · Citigroup · Walmart · Target · HP · Dell · Intel · Micron Technology · Salesforce · Workday · Cisco · T-Mobile · Verizon · Boeing · Accenture

---

## Notes

- **No login required** for any source — all endpoints are public
- Goldman Sachs API has no `postedDate` field; tracker dedup handles new-vs-seen distinction
- LinkedIn scraping uses the guest (unauthenticated) API; rate-limited to avoid blocks
- `seen_jobs.db` is gitignored — your scan history stays local

---

## License

MIT

---

## Development

```bash
# Test suite: 125 tests, fully offline (no network, API keys or browser)
python -m pytest tests/ -q

# Discover new startup boards from the YC directory
python discover_boards.py --fetch-yc
python discover_boards.py --probe 500
python discover_boards.py --write-config

# Optional API keys, read from the environment (never committed)
export FIRECRAWL_API_KEY=...   # enables Indeed + JS-rendered JD fallback
export ANTHROPIC_API_KEY=...   # or sign in to Claude Code and the agent reuses that

# Agent tracing. Either one enables it; without them the agent runs
# identically and just logs spans locally.
export OPIK_API_KEY=...        # Comet cloud (free tier)
export OPIK_WORKSPACE=...      # optional, defaults to your default workspace
export OPIK_URL_OVERRIDE=http://localhost:5173/api   # or a self-hosted instance
```

CI runs the suite on Python 3.11 and 3.12, plus a lint gate and a check that
no credential-shaped strings are committed.

## License

MIT. See [LICENSE](LICENSE).
