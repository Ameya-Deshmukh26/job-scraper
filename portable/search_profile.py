# ── Your search profile ────────────────────────────────────────────────────
# Everything that describes the person searching lives in this one file.
# Claude Code fills it in during first-time setup (type "set me up"), and
# can change it any time: just tell it what you want different.
#
# Company board lists and scan timing stay in config.py.

# False until first-time setup has filled this file in.
SETUP_DONE = False

# Shown in the dashboard header and used to name tailored resumes.
YOUR_NAME = ""

# ── About you ─────────────────────────────────────────────────────────────
# One or two sentences the AI ranker reads before judging fit. Plain facts:
# degree, years and kind of experience, anything that rules jobs in or out.
CANDIDATE_SUMMARY = ""

# ── What to search for ─────────────────────────────────────────────────────
# Typed into each job site's search box. Keep it to titles you would
# actually apply to (6-10 is plenty): every entry is a request to every
# source, and the paid sources only use the first few.
SEARCH_TITLES: list[str] = []

# A job's title must contain at least one of these (lowercase) or it is
# dropped. Broader than SEARCH_TITLES on purpose, to catch variants.
KEYWORDS: list[str] = []

# ── Where ──────────────────────────────────────────────────────────────────
# Country every source searches in (see COUNTRIES in config.py).
SEARCH_COUNTRY = "India"

# Cities searched one by one on Indeed (paid, so keep it to 1-2).
SEARCH_CITIES: list[str] = []

# Drop jobs outside the United States. Only for US job searches.
US_ONLY = False

# If not empty, a job's location must contain one of these (lowercase) or it
# is dropped. Include spelling variants: "bengaluru" and "bangalore".
LOCATION_FILTER: list[str] = []

# Locations that get a small ranking boost (lowercase).
PREFERRED_LOCATIONS: list[str] = []

# ── Level ──────────────────────────────────────────────────────────────────
# Titles containing any of these are dropped as too senior. Do not add a
# bare "manager": it would drop Product Manager, Brand Manager and most
# other MBA-track roles.
EXCLUDE_LEVELS = [
    "director",
    "head of",
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
RANK_TOP_TITLES: list[str] = []
# Title contains one of these -> good match.
RANK_GOOD_TITLES: list[str] = []
# Small boost when the title mentions any of these.
RANK_BONUS_WORDS: list[str] = []

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
