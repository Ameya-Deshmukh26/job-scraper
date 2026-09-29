# ── Your search profile ────────────────────────────────────────────────────
# Everything that describes the person searching lives in this one file.
#
# It comes filled in with a starter search: MBA-track roles (product,
# strategy, consulting, brand, analytics) across India's main job hubs, for
# someone early in their career. It works as-is. To make it yours, open this
# folder in Claude Code and type "set me up", or just tell Claude what to
# change ("add Pune", "I have 4 years of experience").
#
# Company board lists and scan timing stay in config.py.

# False until the starter search has been personalised. It only controls the
# reminder banner on the dashboard; the search runs either way.
SETUP_DONE = False

# Shown in the dashboard header and used to name tailored resumes.
YOUR_NAME = ""

# ── About you ─────────────────────────────────────────────────────────────
# One or two sentences the AI ranker reads before judging fit. Plain facts:
# degree, years and kind of experience, anything that rules jobs in or out.
CANDIDATE_SUMMARY = ("Recent MBA graduate with 0-3 years of work experience, "
                     "targeting product management, strategy, consulting, "
                     "brand and business analytics roles in India.")

# ── What to search for ─────────────────────────────────────────────────────
# Typed into each job site's search box, most important first: the paid
# sites only use the first few (Indeed the first 3).
SEARCH_TITLES = [
    "Associate Product Manager",
    "Product Manager",
    "Business Analyst",
    "Strategy Associate",
    "Management Consultant",
    "Product Marketing Manager",
    "Brand Manager",
    "Category Manager",
    "Founder's Office",
    "Program Manager",
]

# Per-site search terms, when one site needs different wording from
# SEARCH_TITLES. A site not listed here uses SEARCH_TITLES.
SOURCE_QUERIES: dict[str, list[str]] = {}

# A job's title must contain at least one of these (lowercase) or it is
# dropped. Specific on purpose: a bare "consultant" or "analyst" would let in
# thousands of IT roles (SAP Consultant, Data Analyst, QA Analyst).
KEYWORDS = [
    "product manager",
    "product analyst",
    "product marketing",
    "product owner",
    "business analyst",
    "strategy",
    "management consultant",
    "strategy consultant",
    "business consultant",
    "consulting analyst",
    "brand manager",
    "category manager",
    "founder's office",
    "founders office",
    "founder’s office",
    "program manager",
    "growth manager",
    "business development",
    "management trainee",
]

# ── Where ──────────────────────────────────────────────────────────────────
# Country every source searches in (see COUNTRIES in config.py).
SEARCH_COUNTRY = "India"

# Cities searched one by one on Indeed (paid, so keep it to 1-2).
SEARCH_CITIES = ["Bengaluru, Karnataka", "Mumbai, Maharashtra"]

# Drop jobs outside the United States. Only for US job searches.
US_ONLY = False

# A job's location must contain one of these (lowercase) or it is dropped.
# "india" keeps anywhere in India; the city names catch boards that write
# just "Bangalore" or "Gurgaon" with no country.
LOCATION_FILTER = [
    "india",
    "bengaluru", "bangalore",
    "mumbai", "navi mumbai", "bombay", "thane",
    "delhi", "new delhi", "gurugram", "gurgaon", "noida", "ncr",
    "pune",
    "hyderabad",
    "chennai",
    "kolkata",
    "ahmedabad",
]

# Locations that get a small ranking boost (lowercase). Empty: no favourite yet.
PREFERRED_LOCATIONS: list[str] = []

# ── Level ──────────────────────────────────────────────────────────────────
# Titles containing any of these are dropped as too senior. Do not add a
# bare "manager": it would drop Product Manager, Brand Manager and most
# other MBA-track roles.
EXCLUDE_LEVELS = [
    "director",
    "head of",
    " head",         # "Strategy Head", "Brand Head"
    " vp",
    "vice president",
    "chief ",
    "principal",
    "general manager",
    "senior manager",
    "partner",
]

# Also drop "Senior" / "Sr." titles.
EXCLUDE_SENIOR = True

# Drop a job when its description asks for this many years or more.
MAX_YEARS_REQUIRED = 5

# ── Ranking ────────────────────────────────────────────────────────────────
# Title contains one of these -> strongest match.
RANK_TOP_TITLES = ["product manager", "strategy", "founder's office", "founders office"]
# Title contains one of these -> good match.
RANK_GOOD_TITLES = ["business analyst", "product analyst", "product marketing",
                    "management consultant", "strategy consultant", "brand manager",
                    "category manager", "program manager", "growth manager"]
# Small boost when the title mentions any of these.
RANK_BONUS_WORDS = ["mba", "associate", "growth"]

# Companies never treated as staffing agencies, even if the name looks like
# one. Lowercase substrings.
NOT_STAFFING = ["tata consultancy"]

# Needs US work-visa (H-1B) sponsorship. Leave False unless searching for
# US jobs on a visa.
NEEDS_SPONSORSHIP = False

# ── Resume tailoring (optional) ────────────────────────────────────────────
# "" means resume.tex in this folder, which setup can create for you.
BASE_TEX_PATH = ""

# Where tailored resumes are saved. "" means the `resumes` folder here.
RESUME_OUTPUT_DIR = ""

# ── Auto-apply ─────────────────────────────────────────────────────────────
# Lets a bot submit applications on its own. Leave False.
ENABLE_AUTO_APPLY = False
