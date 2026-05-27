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

# ── Adzuna (optional) ─────────────────────────────────────────────────────
# Free API key at https://developer.adzuna.com — 1,000 req/day free tier
# Aggregates Indeed, ZipRecruiter, SimplyHired, and more.
# Leave blank to skip Adzuna.
ADZUNA_APP_ID  = ""
ADZUNA_APP_KEY = ""

# ── Notifications ──────────────────────────────────────────────────────────
ENABLE_WINDOWS_TOAST = True

# Create a Discord webhook: Server Settings > Integrations > Webhooks
# Paste the URL here to also get Discord alerts. Leave empty to disable.
DISCORD_WEBHOOK_URL = ""

# ── Greenhouse Companies ───────────────────────────────────────────────────
# These are the board tokens used in the Greenhouse public API.
# URL pattern: https://boards.greenhouse.io/{token}
# 404s are silently skipped. Add/remove companies freely.
GREENHOUSE_COMPANIES = [
    # Fintech / Payments
    "stripe", "brex", "ramp", "mercury", "plaid", "robinhood",
    "coinbase", "chime", "affirm", "klarna", "marqeta", "payoneer",
    "wealthfront", "betterment", "sofi", "fundbox", "bluevine",
    "tabapay", "lithic",
    # Data / Analytics / AI Infrastructure
    "databricks", "snowflakecomputing", "dbtlabs", "fivetran",
    "hightouch", "rudderstack", "metabase", "hex", "deepnote",
    "amplitude", "mixpanel", "segment", "census",
    "modal", "anyscale", "cohere", "groq", "together",
    "starburst", "atlan", "montecarlodata", "greatexpectations",
    "tecton", "feast", "weights-biases",
    "clickhouse", "singlestore", "imply", "transform",
    # AI / LLM Startups (confirmed working)
    "anthropic", "xai", "togetherai", "fireworksai",
    "stabilityai", "imbue", "scaleai", "heygen",
    "vectara", "truefoundry",
    # Enterprise SaaS
    "figma", "notion", "airtable", "lattice", "rippling",
    "gusto", "checkr", "deel", "remote", "carta",
    "algolia", "contentful", "retool", "linear", "loom",
    "monday", "clickup", "asana", "smartsheet",
    "zendesk", "freshworks", "intercom", "drift",
    "salesloft", "outreach", "gong",
    "descript", "lokalise",
    # Cloud / Infra
    "hashicorp", "confluent", "mongodb", "elastic",
    "cockroachdb", "neon", "planetscale", "supabase", "vercel",
    "digitalocean", "linode", "coreweave",
    # Cybersecurity
    "crowdstrike", "sentinelone", "lacework", "orca",
    "snyk", "sysdig", "noname",
    # Consumer / Marketplace
    "airbnb", "doordash", "lyft", "pinterest", "instacart",
    "etsy", "poshmark", "offerpath", "opendoor", "offerpad",
    "duolingo", "coursera", "udemy",
    # Healthcare / Biotech
    "modernhealth", "cityblockhealth", "springhealth",
    "headspace", "oscarhealthinc", "cloverhealth",
    "ro", "hims", "cerebral", "nomi",
    # Logistics / Ops
    "flexport", "project44", "shippingbo",
    # Finance / Trading
    "palantir", "twosigma", "jane-street", "hudsonrivertrading",
    # Media / Gaming
    "roblox", "unity", "epic", "zynga",
    # Other high-sponsorship tech
    "twilio", "okta", "hubspot", "dropbox",
    "cloudflare", "datadog", "grafana", "newrelic",
    "splunk", "dynatrace", "appdynamics",
    "salesforce", "workday", "servicenow",
    "zoom", "slack", "box",
    "nvidia", "amd", "qualcomm",
    # Observability / DevTools
    "honeycomb",
    # AI Research Labs
    "deepmind",
    # Startup / Growth companies
    "cobo",
]

# ── Ashby Companies ───────────────────────────────────────────────────────
# URL pattern: https://jobs.ashbyhq.com/{slug}
ASHBY_COMPANIES = [
    # AI / LLM labs
    "anthropic", "perplexity-ai", "cursor", "cognition", "harvey",
    "cohere", "mistral", "imbue", "adept", "moonshot-ai",
    "openai",       # some roles on Ashby
    # Dev tools / infra
    "linear", "posthog", "vercel", "railway", "clerk", "turso",
    "resend", "highlight", "mintlify", "cal-com", "trigger",
    "infisical", "novu", "dub",
    # Data / Analytics
    "evidence", "cube-dev", "rill-data", "tinybird",
    # Finance / Fintech
    "mercury", "ramp",          # some roles on Ashby too
    "brex", "arc",
    # Enterprise SaaS
    "coda", "baseten", "modal",
    "watershed", "rippling",
    # Other high-growth
    "wiz", "clari", "navan", "gong", "chorus",
    "scale-ai", "labelbox",
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
LEVER_COMPANIES = [
    # Big Tech / Media
    "netflix", "reddit", "squarespace", "vimeo", "twitch",
    # AI / ML
    "scaleai", "huggingface", "together", "aleph-alpha",
    "mistral", "anyscale",
    # Fintech
    "robinhood", "wise", "nubank", "chime", "brex",
    # Data
    "airbyte", "starburst", "preset", "lightdash",
    # Dev tools
    "sentry", "launchdarkly", "split",
    # Enterprise
    "canva", "intercom", "typeform", "miro", "pipedrive",
    "invision", "lucidchart",
    # Other high-growth
    "wealthsimple", "benchling", "netsuite",
    "grammarly", "duolingo", "brainly",
]
