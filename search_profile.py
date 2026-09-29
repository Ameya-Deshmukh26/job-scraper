# ── Your search profile ────────────────────────────────────────────────────
# Everything that describes the person searching lives in this one file:
# what to search for, where, at what level, and how to rank results.
# Company board lists and scan timing stay in config.py.
#
# config.py imports this file, so `from config import KEYWORDS` etc. keep
# working everywhere.

# Set to True once the profile below has been filled in. The portable copy
# ships with False, which is how Claude Code knows to run first-time setup.
SETUP_DONE = True

# Shown in the dashboard header and used to name tailored resumes.
YOUR_NAME = "Ameya Deshmukh"

# ── What to search for ─────────────────────────────────────────────────────
# Typed into each job site's search box (LinkedIn, Google Jobs, Indeed,
# Workday, Amazon, ...). Keep it to the titles you would actually apply to:
# every entry is a request to every source, and the paid sources cap how
# many they use.
SEARCH_TITLES = [
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "data engineer",
    "analytics engineer",
    "AI engineer",
    "gen ai engineer",
    "business analyst AI",
]

# A job's title must contain at least one of these (case-insensitive) or it
# is dropped. Broader than SEARCH_TITLES on purpose, to catch variants.
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

# Per-site search terms, when one site needs different wording from
# SEARCH_TITLES. A site not listed here uses SEARCH_TITLES.
SOURCE_QUERIES = {
    "workday":       ["data engineer", "data scientist", "analytics engineer",
                      "ml engineer", "ai engineer", "business analyst"],
    "faang":         ["data scientist", "data analyst", "machine learning engineer",
                      "data engineer", "ai engineer", "business analyst"],
    "deloitte":      ["data analyst", "data scientist", "machine learning",
                      "data engineer", "analytics engineer", "ai engineer",
                      "business analyst"],
    "goldman_sachs": ["data analyst", "data scientist", "machine learning",
                      "data engineer", "analytics", "quantitative", "ai engineer",
                      "business analyst"],
    "staffing":      ["data-scientist", "data-analyst", "machine-learning-engineer",
                      "data-engineer", "ai-engineer", "llm", "generative-ai",
                      "business-intelligence", "analytics-engineer", "business-analyst"],
    "google_jobs":   ["entry level data scientist", "junior machine learning engineer",
                      "entry level data engineer", "AI engineer new grad",
                      "data analyst entry level"],
    "indeed":        ["data scientist", "machine learning engineer", "data analyst"],
}

# ── Where ──────────────────────────────────────────────────────────────────
# Country every source searches in, spelled as below (see COUNTRIES in
# config.py for the supported list).
SEARCH_COUNTRY = "United States"

# Cities searched one by one on Indeed (a paid source, so keep it short).
SEARCH_CITIES = ["Boston, MA", "Remote"]

# Drop jobs whose location is clearly outside the US.
US_ONLY = True

# If not empty, a job's location must contain one of these (lowercase) or it
# is dropped. Leave empty to accept anywhere in the country.
LOCATION_FILTER = []

# Locations that get a small ranking boost (lowercase substrings).
PREFERRED_LOCATIONS = ["boston", "cambridge", "massachusetts"]

# ── Level ──────────────────────────────────────────────────────────────────
# Titles containing any of these are dropped as too senior.
# NOTE: "manager" is here because for data roles it means a people manager.
# For product, marketing or MBA-track roles, remove it, or "Product Manager"
# and "Associate Product Manager" will all be filtered out.
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

# Also drop "Senior" / "Sr." titles (senior usually means 4-6 years).
EXCLUDE_SENIOR = True

# Drop a job when its description asks for this many years or more
# ("5+ years", "minimum 5 years", "5-8 years").
MAX_YEARS_REQUIRED = 5

# ── About you ─────────────────────────────────────────────────────────────
# One or two sentences the AI ranker reads before judging fit. Plain facts:
# experience, degree, and anything that rules jobs in or out.
CANDIDATE_SUMMARY = ("The candidate has ~2-3 years of experience, needs H-1B "
                     "sponsorship, and is based in Boston but open to relocation.")

# ── Ranking ────────────────────────────────────────────────────────────────
# Title contains one of these -> strongest match.
RANK_TOP_TITLES = ["data scientist", "machine learning engineer", "ml engineer",
                   "ai engineer", "applied scientist", "research engineer"]
# Title contains one of these -> good match.
RANK_GOOD_TITLES = ["data analyst", "analytics engineer", "data engineer",
                    "business intelligence", "bi analyst", "nlp engineer",
                    "business analyst", "ai analyst"]
# Small boost when the title mentions any of these.
RANK_BONUS_WORDS = ["llm", "genai", "gen ai", "generative", "nlp", "agent", "rag"]

# Companies never treated as staffing agencies, even if the name looks like
# one ("Tata Consultancy Services"). Lowercase substrings.
NOT_STAFFING: list[str] = []

# Needs US work-visa (H-1B) sponsorship. When False the H-1B sponsor data is
# never downloaded, and the H-1B tags and filter are hidden.
NEEDS_SPONSORSHIP = True

# ── Resume tailoring (optional) ────────────────────────────────────────────
# A LaTeX resume using \resumeItem{...} bullets. Leave "" to switch the
# resume-tailoring buttons off.
BASE_TEX_PATH = "C:/Users/ameya/Downloads/Ameya_Deshmukh_BASE_v3.tex"

# Where tailored resumes are saved. "" means a `resumes` folder in the project.
RESUME_OUTPUT_DIR = "C:/Users/ameya/Downloads"

# ── Auto-apply ─────────────────────────────────────────────────────────────
# Lets the overnight mode submit Greenhouse / Lever applications on its own
# using profile.json. Keep False unless you have filled profile.json in and
# want the bot submitting applications for you.
ENABLE_AUTO_APPLY = True
