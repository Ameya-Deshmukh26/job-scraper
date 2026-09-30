# ── Job Scraper Configuration ──────────────────────────────────────────────
# Edit this file to customize what you're looking for.

# ── API keys ───────────────────────────────────────────────────────────────
# Keys live in .env next to this file (gitignored, never committed). Loaded
# here because config is the first project import in both app.py and
# main.py, and some sources read their key at import time. A variable that
# is already set in the real environment wins over .env.
#
# Blank entries are skipped rather than exported as "". The template ships
# with empty slots, and an empty OPIK_WORKSPACE made the Opik SDK send a
# blank workspace instead of falling back to its saved default (HTTP 403).
import os as _os
from pathlib import Path as _Path

try:
    from dotenv import dotenv_values as _dotenv_values
    for _k, _v in _dotenv_values(_Path(__file__).with_name(".env")).items():
        if _v and _v.strip() and not _os.environ.get(_k):
            _os.environ[_k] = _v.strip()
except ImportError:
    pass

# ── Resume Tailoring ───────────────────────────────────────────────────────
# Get a key at https://console.anthropic.com — or set the ANTHROPIC_API_KEY env var.
ANTHROPIC_API_KEY = ""  # or: export ANTHROPIC_API_KEY=sk-ant-...


# ── Search profile ─────────────────────────────────────────────────────────
# Who is searching, for what, and where lives in search_profile.py. The
# defaults here only cover a profile file that predates a setting.
SETUP_DONE = False
YOUR_NAME = ""
CANDIDATE_SUMMARY = ""
SEARCH_TITLES: list[str] = []
SOURCE_QUERIES: dict[str, list[str]] = {}
KEYWORDS: list[str] = []
SEARCH_COUNTRY = "United States"
SEARCH_CITIES: list[str] = []
US_ONLY = True
LOCATION_FILTER: list[str] = []
PREFERRED_LOCATIONS: list[str] = []
EXCLUDE_LEVELS: list[str] = []
EXCLUDE_SENIOR = True
MAX_YEARS_REQUIRED = 5
HIGHEST_DEGREE = "bachelors"
RANK_TOP_TITLES: list[str] = []
RANK_GOOD_TITLES: list[str] = []
RANK_BONUS_WORDS: list[str] = []
NEEDS_SPONSORSHIP = False
NOT_STAFFING: list[str] = []
BLOCKED_COMPANIES: list[str] = []
BASE_TEX_PATH = ""
RESUME_OUTPUT_DIR = ""
ENABLE_AUTO_APPLY = False

from search_profile import *  # noqa: E402,F401,F403

# ── Countries ──────────────────────────────────────────────────────────────
# SEARCH_COUNTRY -> the codes each source wants. iso2/iso3 are ISO 3166;
# indeed is the country's Indeed host.
COUNTRIES = {
    "United States":        {"iso2": "us", "iso3": "USA", "indeed": "www.indeed.com"},
    "India":                {"iso2": "in", "iso3": "IND", "indeed": "in.indeed.com"},
    "United Kingdom":       {"iso2": "gb", "iso3": "GBR", "indeed": "uk.indeed.com"},
    "Canada":               {"iso2": "ca", "iso3": "CAN", "indeed": "ca.indeed.com"},
    "Australia":            {"iso2": "au", "iso3": "AUS", "indeed": "au.indeed.com"},
    "Singapore":            {"iso2": "sg", "iso3": "SGP", "indeed": "sg.indeed.com"},
    "United Arab Emirates": {"iso2": "ae", "iso3": "ARE", "indeed": "ae.indeed.com"},
    "Germany":              {"iso2": "de", "iso3": "DEU", "indeed": "de.indeed.com"},
    "Ireland":              {"iso2": "ie", "iso3": "IRL", "indeed": "ie.indeed.com"},
    "Netherlands":          {"iso2": "nl", "iso3": "NLD", "indeed": "nl.indeed.com"},
}
COUNTRY = COUNTRIES.get(SEARCH_COUNTRY, COUNTRIES["United States"])
IN_US = SEARCH_COUNTRY == "United States"

# Resume files. With no BASE_TEX_PATH the resume is resume.tex in the project
# folder, which is where first-time setup writes one.
PROJECT_DIR = _Path(__file__).resolve().parent
RESUME_TEX = _Path(BASE_TEX_PATH) if BASE_TEX_PATH else PROJECT_DIR / "resume.tex"
RESUME_DIR = _Path(RESUME_OUTPUT_DIR) if RESUME_OUTPUT_DIR else PROJECT_DIR / "resumes"


# How far back to look on each run (hours). 1 = last 60 minutes.
# Use --hours N flag to override at runtime (e.g. first run: --hours 24)
LOOKBACK_HOURS = 6

# Polling interval when running in --loop mode (minutes)
POLL_INTERVAL_MINUTES = 15

# Enable LinkedIn scraping (guest API, no login needed)
ENABLE_LINKEDIN = True

# ── Overnight / Auto-apply ─────────────────────────────────────────────────
# python main.py --overnight   → runs every 2 hrs, auto-applies to GH + Lever
OVERNIGHT_POLL_HOURS    = 2     # how often to scan overnight
OVERNIGHT_LOOKBACK_HRS  = 3     # look back 3 hours each scan



# ── Notifications ──────────────────────────────────────────────────────────
ENABLE_WINDOWS_TOAST = True

# Create a Discord webhook: Server Settings > Integrations > Webhooks
# Paste the URL here to also get Discord alerts. Leave empty to disable.
DISCORD_WEBHOOK_URL = ""

# ── Greenhouse Companies ───────────────────────────────────────────────────
# These are the board tokens used in the Greenhouse public API.
# URL pattern: https://boards.greenhouse.io/{token}
# 404s are silently skipped. Add/remove companies freely.
# Only confirmed-live boards (HTTP 200 with >0 jobs, June 2026 audit).
# 85 dead slugs removed — they 404'd and wasted a request every scan.
GREENHOUSE_COMPANIES = [
    # --- auto-discovered from YC via discover_boards.py ---
    "aclu", "akidolabs", "albedo", "alpaca", "ansabiotechnologies", "aon3d", "apolloio", "assemblyai", "astranis", "axle", "baubap", "bird", "bitmovin", "carbonchain", "caribou", "clear", "coast", "cortex", "culturebiosciences", "daybreakhealth", "diligent", "dots", "enveritas", "extend", "faire", "focalsystems", "gather", "generalproximity", "gigs", "givecampus", "glide", "goatgroup", "gocardless", "grey", "hackerrank", "haven", "heartaerospace", "hive", "hubblenetwork", "humaninterest", "instawork", "inversionspace", "kalshi", "laika", "legalist", "lob", "lucidbots", "luminate", "marqvision", "mattermost", "maymobility", "meruhealth", "mesh", "nabis", "niraenergy", "novacredit", "observeai", "odeko", "ophelia", "outschool", "pairteam", "papa", "pelago", "postscript", "prodigal", "prolific", "pronto", "prospa", "qventus", "radar", "recidiviz", "reflex", "regent", "remi", "roofr", "saltsecurity", "sendbird", "sfox", "sirum", "smartasset", "submittable", "super", "swayable", "tempo", "usergems", "veriff", "warp", "webflow", "xendit", "zerocater",
    # --- auto-discovered from YC via discover_boards.py ---
    "icarus", "momentic", "orbitaloperations", "parallel", "starcloud", "weave",
    # Fintech / Payments
    "stripe", "brex", "mercury", "robinhood", "coinbase", "chime",
    "affirm", "marqeta", "payoneer", "betterment", "sofi",
    "tabapay", "lithic",
    # Data / Analytics / AI Infrastructure
    "databricks", "fivetran", "hightouch", "amplitude", "mixpanel",
    "starburst", "clickhouse", "singlestore", "imply", "transform",
    # AI / LLM Startups
    "anthropic", "xai", "togetherai", "fireworksai",
    "stabilityai", "imbue", "scaleai", "heygen",
    "vectara", "truefoundry", "deepmind",
    # Enterprise SaaS
    "figma", "airtable", "lattice", "gusto", "checkr", "remote",
    "carta", "algolia", "contentful", "asana", "smartsheet",
    "intercom", "salesloft", "descript", "lokalise",
    # Cloud / Infra
    "mongodb", "elastic", "planetscale", "vercel", "coreweave",
    # Cybersecurity
    "orca",
    # Consumer / Marketplace
    "airbnb", "lyft", "pinterest", "instacart", "poshmark",
    "duolingo", "coursera", "udemy",
    # Healthcare
    "modernhealth", "cloverhealth", "cerebral",
    # Logistics / Ops
    "flexport", "project44",
    # Media / Gaming
    "roblox",
    # Other high-sponsorship tech
    "twilio", "okta", "hubspot", "dropbox",
    "cloudflare", "datadog", "newrelic", "honeycomb",
]

# ── Ashby Companies ───────────────────────────────────────────────────────
# URL pattern: https://jobs.ashbyhq.com/{slug}
# Only confirmed-valid slugs (HTTP 200 from GraphQL, May 2026 audit)
# Note: anthropic, perplexity-ai, mistral, brex, rippling, gong, scale-ai
#       etc. are on Greenhouse/Lever — they show NULL on Ashby.
ASHBY_COMPANIES = [
    # --- auto-discovered from YC via discover_boards.py ---
    "airgoods", "artie", "avoca", "benchling", "bluedot", "capimoney", "casca", "clueso", "conduit", "cosine", "deepgram", "electricair", "escape", "finni-health", "goveagle", "hockeystack", "hyperbound", "inkeep", "latent", "lio", "litellm", "magicpatterns", "mux", "numeral", "pirros", "pylon", "salient", "solveintelligence", "tennr", "twenty", "vanta", "vitalize", "vooma", "wallbit",
    # --- auto-discovered from YC via discover_boards.py ---
    "afterquery", "agentmail", "auctor", "complir", "dedalus-labs", "finto", "flai", "fleetline", "hud", "humanarchive", "idler", "lance", "lucis", "mastra", "mercura", "nox-metals", "reacher", "sazabi", "solva", "uplane", "veritus",
    # AI / LLM labs
    "openai",           # 707 jobs
    "harvey",           # 247 jobs
    "cohere",           # 130 jobs
    "cursor",           # 82 jobs
    "cognition",        # 60 jobs
    "moonshot-ai",      # 5 jobs
    # Finance / Fintech
    "ramp",             # 122 jobs
    # Data / Cloud infra
    "baseten",          # 63 jobs
    "watershed",        # 39 jobs
    "modal",            # 29 jobs
    # Dev tools
    "linear",           # 23 jobs
    "posthog",          # 16 jobs
    "infisical",        # 15 jobs
    "mintlify",         # 13 jobs
    "railway",          # 9 jobs
    "resend",           # 4 jobs
    "vercel",           # 0 now but active board
    "clerk",            # 0 now but active board
    "wiz",              # 0 now but active board
    "mercury",          # 0 now but active board
]

# ── Workday Companies ─────────────────────────────────────────────────────
# Tuples of (subdomain_with_wd_number, board_slug, display_name).
# The wd number (wd1, wd5, wd12, etc.) is company-specific — all confirmed
# working via HTTP 200 from the CXS API before being added here.
# Add/remove freely; 404s and 422s are silently skipped by the scraper.
WORKDAY_COMPANIES: list[tuple[str, str, str]] = [
    # Healthcare / Insurance (all confirmed HTTP 200)
    ("cvshealth.wd1",   "CVS_Health_Careers",          "CVS Health"),
    ("cigna.wd5",       "cignacareers",                "Cigna"),
    ("humana.wd5",      "Humana_External_Career_Site", "Humana"),
    ("pfizer.wd1",      "PfizerCareers",               "Pfizer"),
    ("jj.wd5",          "JJ",                          "Johnson & Johnson"),
    ("nationwide.wd1",  "Nationwide_Career",           "Nationwide"),
    ("travelers.wd5",   "External",                    "Travelers"),
    # Finance / Payments (all confirmed HTTP 200)
    ("paypal.wd1",      "jobs",                        "PayPal"),
    ("capitalone.wd12", "Capital_One",                 "Capital One"),
    ("ms.wd5",          "External",                    "Morgan Stanley"),
    ("visa.wd5",        "Visa",                        "Visa"),
    ("wf.wd1",          "WellsFargoJobs",              "Wells Fargo"),
    ("ghr.wd1",         "Lateral-US",                  "Bank of America"),
    ("citi.wd5",        "2",                           "Citigroup"),
    # Retail / Consumer (all confirmed HTTP 200)
    ("walmart.wd5",     "WalmartExternal",             "Walmart"),
    ("target.wd5",      "TargetCareers",               "Target"),
    # Technology Hardware / Semiconductors (all confirmed HTTP 200)
    ("hp.wd5",          "ExternalCareerSite",          "HP"),
    ("dell.wd1",        "External",                    "Dell"),
    ("intel.wd1",       "External",                    "Intel"),
    ("micron.wd1",      "External",                    "Micron Technology"),
    # Enterprise Software / Cloud (all confirmed HTTP 200)
    ("salesforce.wd12", "External_Career_Site",        "Salesforce"),
    ("workday.wd5",     "Workday",                     "Workday"),
    ("cisco.wd5",       "Cisco_Careers",               "Cisco"),
    # Telecom (all confirmed HTTP 200)
    ("tmobile.wd1",     "External",                    "T-Mobile"),
    ("verizon.wd12",    "verizon-careers",             "Verizon"),
    # Defense / Aerospace / Consulting (all confirmed HTTP 200)
    ("boeing.wd1",      "EXTERNAL_CAREERS",            "Boeing"),
    ("accenture.wd103", "AccentureCareers",            "Accenture"),
    ("globalhr.wd5",    "REC_RTX_Ext_Gateway",         "RTX / Raytheon"),
    # Asset Management / Finance (all confirmed HTTP 200)
    ("blackrock.wd1",      "BlackRock_Professional",   "BlackRock"),
    ("statestreet.wd1",    "Global",                   "State Street"),
]

# ── Lever Companies ────────────────────────────────────────────────────────
# URL pattern: https://jobs.lever.co/{slug}
# Only confirmed-live boards (June 2026 audit) — 32 dead slugs removed.
# mistral & netflix are valid boards currently showing 0 postings; kept
# because they may repopulate and cost one cheap request each.
LEVER_COMPANIES = [
    # --- auto-discovered from YC via discover_boards.py ---
    "biorender", "bolster", "canarytechnologies", "captivateiq", "copia", "culdesac", "doola", "emilabs", "epsilon3", "fampay", "finch", "fintual", "fleetzero", "gridware", "handoff", "kinter", "livingcarbon", "mashgin", "maverickx", "multiplylabs", "mytos", "nimblerx", "people-ai", "picktrace", "porter", "postera", "pyka", "quartzy", "skyways", "snappr", "starkbank", "suger", "superside", "synapticure", "tendo", "thunkable", "toku", "tovala", "twodots", "verifiable", "zippi",
    "anyscale", "pipedrive", "mistral", "netflix",
]
