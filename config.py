# ── Job Scraper Configuration ──────────────────────────────────────────────
# Edit this file to customize what you're looking for.

# ── Resume Tailoring ───────────────────────────────────────────────────────
# Get a key at https://console.anthropic.com — or set the ANTHROPIC_API_KEY env var.
ANTHROPIC_API_KEY = ""  # or: export ANTHROPIC_API_KEY=sk-ant-...
BASE_TEX_PATH = "C:/Users/ameya/Downloads/Ameya_Deshmukh_BASE_v3.tex"


# How far back to look on each run (hours). 1 = last 60 minutes.
# Use --hours N flag to override at runtime (e.g. first run: --hours 24)
LOOKBACK_HOURS = 6

# Polling interval when running in --loop mode (minutes)
POLL_INTERVAL_MINUTES = 15

# Filter to US-based jobs only (removes India, UK, Canada, etc.)
US_ONLY = True

# Enable LinkedIn scraping (guest API, no login needed)
ENABLE_LINKEDIN = True

# ── Overnight / Auto-apply ─────────────────────────────────────────────────
# python main.py --overnight   → runs every 2 hrs, auto-applies to GH + Lever
OVERNIGHT_POLL_HOURS    = 2     # how often to scan overnight
OVERNIGHT_LOOKBACK_HRS  = 3     # look back 3 hours each scan
ENABLE_AUTO_APPLY       = True  # set False to disable bot submissions

# ── Keywords ───────────────────────────────────────────────────────────────
# Job title must contain at least one of these (case-insensitive)
KEYWORDS = [
    "data analyst",
    "data scientist",
    "machine learning",
    "ml engineer",
    "data engineer",
    "analytics engineer",
    "business intelligence",
    "bi analyst",
    "business analyst",
    "ai analyst",
    "ai engineer",
    "gen ai",
    "generative ai",
    "llm",
    "applied scientist",
    "nlp engineer",
    "research scientist",
    "analytics",
]

# ── Experience level filter ────────────────────────────────────────────────
# Titles containing any of these words are excluded (targets 2-3 yr exp roles)
# Add "senior" here if you want to exclude Sr. roles too
EXCLUDE_LEVELS = [
    "staff ",        # Staff Engineer, Staff ML Engineer
    "principal",     # Principal Engineer / Scientist
    "manager",       # Engineering Manager, Data Manager
    "director",      # Director of Engineering
    "head of",       # Head of Data
    " vp",           # VP of Engineering
    "vice president",
    "tech lead",
    "lead engineer",
    "lead data",
    "lead ml",
    "lead scientist",
    "distinguished",
    "fellow",
    "(l5)", "(l6)", "(l7)", "(l8)",
    " l5,", " l6,", " l7,",
]

# Set True to also exclude "Senior" titles (Senior usually = 4-6 yrs)
EXCLUDE_SENIOR = True

# Fine-grained location allowlist (leave empty to rely on US_ONLY flag alone)
# Example: ["remote", "new york", "boston", "san francisco"]
LOCATION_FILTER = []  # empty = accept all US locations


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

# ── Oracle HCM Companies ───────────────────────────────────────────────────
# Tuple of (tenant_hostname, site_code, display_name)
# Tenant hostname format: {company}.fa.{region}.oraclecloud.com
# Site code is embedded in the careers page URL under /sites/{code}/
ORACLE_HCM_COMPANIES: list[tuple[str, str, str]] = [
    # Finance / Banking (all confirmed HTTP 200)
    ("jpmc.fa.oraclecloud.com",     "CX_1001",      "JPMorgan Chase"),
    ("hdpc.fa.us2.oraclecloud.com", "LateralHiring", "Goldman Sachs"),
    ("egug.fa.us2.oraclecloud.com", "CX_1",          "American Express"),
    # Technology (all confirmed HTTP 200)
    ("eeho.fa.us2.oraclecloud.com", "jobsearch",     "Oracle Corporation"),
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
