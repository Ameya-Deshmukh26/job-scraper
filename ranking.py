"""
Match scoring for the dashboard — ranks jobs by fit for Ameya's profile
(2-3 yrs exp, DS/ML/AI focus, needs H-1B sponsorship, Boston-based,
open to relocation). Pure heuristics, no LLM, so it runs on every
/api/jobs response at zero cost.

Score range 0-100. Rough bands: 75+ strong, 55-74 decent, <55 weak.
"""
import re
from datetime import datetime, timezone

# Title tiers — what the role actually is
_TIER_A = ["data scientist", "machine learning engineer", "ml engineer",
           "ai engineer", "applied scientist", "research engineer"]
_TIER_B = ["data analyst", "analytics engineer", "data engineer",
           "business intelligence", "bi analyst", "nlp engineer",
           "business analyst", "ai analyst"]

# Junior-friendly markers (fits 2-3 yrs experience)
_JUNIOR = re.compile(r"\b(junior|associate|entry[- ]level|early career|"
                     r"graduate|new grad|university|campus|i{1,2})\b\.?$|"
                     r"\b(junior|associate|entry[- ]level|early career|"
                     r"graduate|new grad)\b", re.IGNORECASE)

# GenAI/LLM signals — matches Ameya's strongest recent experience
_GENAI = ["llm", "genai", "gen ai", "generative", "nlp", "agent", "rag"]

# Staffing-agency tells in company names — high-volume, low-conversion
_STAFFING = re.compile(
    r"staffing|recruit|consultan|talent|jobs via|jobright|dice\b|"
    r"infotech|softech|tek\s?(doors|systems|club)|hire|\bhr\b|"
    r"solutions? (inc|llc|group)|resourc|global source|placement",
    re.IGNORECASE,
)


def match_score(job: dict) -> int:
    title    = (job.get("title") or "").lower()
    company  = job.get("company") or ""
    location = (job.get("location") or "").lower()
    source   = (job.get("source") or "").lower()

    score = 50.0

    # Role fit
    if any(t in title for t in _TIER_A):
        score += 20
    elif any(t in title for t in _TIER_B):
        score += 14
    else:
        score -= 8   # matched only a weak keyword like bare "analytics"

    # Level fit
    if _JUNIOR.search(job.get("title") or ""):
        score += 8

    # GenAI/LLM alignment
    if any(g in title for g in _GENAI):
        score += 5

    # Company quality
    if _STAFFING.search(company):
        score -= 22
    if job.get("h1b_sponsor"):
        score += 12   # sponsorship track record is critical on OPT

    # Location
    if any(loc in location for loc in ["boston", "cambridge", "massachusetts"]):
        score += 6
    elif "remote" in location or location.strip() == "united states":
        score += 4

    # Direct-ATS sources are auto-applyable and less crowded than LinkedIn
    if source in ("greenhouse", "lever", "ashby"):
        score += 5

    # Freshness (seen_at is UTC "YYYY-MM-DD HH:MM:SS")
    try:
        seen = datetime.fromisoformat(job.get("seen_at", "")).replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - seen).total_seconds() / 3600
        if age_h <= 2:
            score += 8
        elif age_h <= 24:
            score += 4
    except Exception:
        pass

    return max(0, min(100, round(score)))
