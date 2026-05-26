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

- **Multi-source scraping** — Greenhouse (80+ companies), Lever (30+), Ashby (30+), Workday (27 Fortune 500 companies), Goldman Sachs (custom GraphQL API), Remotive, HiringCafe, LinkedIn, Adzuna
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

| Source | Type | Companies |
|---|---|---|
| Greenhouse | ATS API | 80+ startups & tech cos |
| Lever | ATS API | 30+ companies |
| Ashby | ATS API | 30+ AI/dev-tool startups |
| Workday | CXS JSON API | 27 Fortune 500 (Capital One, Walmart, Cisco, Boeing, Citi, Wells Fargo, BofA, Accenture, …) |
| Goldman Sachs | Custom GraphQL | `api-higher.gs.com` |
| LinkedIn | Guest API | Keyword search |
| Remotive | Public API | Remote-first jobs |
| HiringCafe | Public API | Aggregator |
| Adzuna | REST API | Indeed/ZipRecruiter/SimplyHired aggregate |

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

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
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
http://localhost:5000
```

- **All Jobs tab** — full feed from all sources, filterable by keyword / source / location
- **Portal Radar tab** — company-portal jobs only, newest first, grouped by ATS:
  1. Workday — Fortune 500
  2. Goldman Sachs
  3. Greenhouse · Lever · Ashby
- **Scan Now** button — trigger an immediate portal scan
- **Countdown timer** — shows time until next automatic hourly scan

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
