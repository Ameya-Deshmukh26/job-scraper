"""Fetch LinkedIn jobs via Apify curious_coder/linkedin-jobs-scraper HTTP API."""
import re
import time
import requests

APIFY_TOKEN = ""  # set via APIFY_TOKEN env var or paste here (never commit real keys)
ACTOR_ID    = "curious_coder~linkedin-jobs-scraper"

# Search URLs — entry/associate level, full-time, US, last 2 hours
_SEARCH_URLS = [
    "https://www.linkedin.com/jobs/search/?keywords=Data+Scientist&geoId=103644278&f_TPR=r7200&f_E=2%2C3&f_JT=F",
    "https://www.linkedin.com/jobs/search/?keywords=Machine+Learning+Engineer&geoId=103644278&f_TPR=r7200&f_E=2%2C3&f_JT=F",
    "https://www.linkedin.com/jobs/search/?keywords=Data+Engineer&geoId=103644278&f_TPR=r7200&f_E=2%2C3&f_JT=F",
    "https://www.linkedin.com/jobs/search/?keywords=Data+Analyst&geoId=103644278&f_TPR=r7200&f_E=2%2C3&f_JT=F",
    "https://www.linkedin.com/jobs/search/?keywords=AI+Engineer&geoId=103644278&f_TPR=r7200&f_E=2%2C3&f_JT=F",
    "https://www.linkedin.com/jobs/search/?keywords=Gen+AI+Engineer&geoId=103644278&f_TPR=r7200&f_E=2%2C3&f_JT=F",
]

_EXP_HIGH = re.compile(
    r'(?:\b([5-9]|\d{2,})\s*\+\s*years?'
    r'|\b([5-9]|\d{2,})\s+or\s+more\s+years?'
    r'|minimum\s+(?:of\s+)?([5-9]|\d{2,})\s+years?'
    r'|at\s+least\s+([5-9]|\d{2,})\s+years?'
    r'|\b([5-9]|\d{2,})\s*[-–]\s*\d+\s+years?'
    r')\s*(?:of\s+)?(?:professional\s+|relevant\s+|related\s+|work\s+)?experience',
    re.IGNORECASE,
)
_SKIP_TITLE = re.compile(
    r'\b(senior|sr\.?|staff|principal|director|manager|head\s+of|vp\b|vice\s+pres)\b',
    re.IGNORECASE,
)
_RELEVANT_TITLE = re.compile(
    r'\b(data|machine\s+learning|ml\b|ai\b|artificial\s+intelligence|analytics?'
    r'|scientist|nlp|llm|gen\s*ai|analyst|intelligence|mle\b|deep\s+learning'
    r'|applied\s+ai|applied\s+ml)\b',
    re.IGNORECASE,
)
_SKIP_COMPANY = re.compile(
    r'robert half|emonics|brooksource|bluebash|fetchjobs|skillstorm|bletchley'
    r'|jobs\s+via\s+|via\s+dice|via\s+indeed|via\s+ziprecruiter|via\s+careerbuilder'
    r'|via\s+simplyhired|via\s+monster|via\s+glassdoor|via\s+jobcase'
    r'|via\s+linkedin|staffing|recruiting|talent\s+solutions|search\s+group',
    re.IGNORECASE,
)


def _run_actor(urls: list[str], count: int = 25) -> str:
    """Start actor run, wait for finish, return datasetId."""
    resp = requests.post(
        f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs",
        params={"token": APIFY_TOKEN},
        json={"urls": urls, "count": count, "scrapeCompany": False},
        timeout=30,
    )
    resp.raise_for_status()
    run_id = resp.json()["data"]["id"]

    # Poll until finished (max 3 min)
    for _ in range(36):
        time.sleep(5)
        r = requests.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}",
            params={"token": APIFY_TOKEN},
            timeout=15,
        )
        r.raise_for_status()
        status = r.json()["data"]["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            dataset_id = r.json()["data"]["defaultDatasetId"]
            return dataset_id
    raise TimeoutError("Apify actor timed out after 3 minutes")


def _fetch_items(dataset_id: str) -> list[dict]:
    resp = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        params={"token": APIFY_TOKEN, "format": "json", "limit": 200},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _filter(items: list[dict]) -> list[dict]:
    seen_ids = set()
    out = []
    for job in items:
        title   = job.get("title", "")
        company = job.get("companyName", "")
        desc    = job.get("descriptionText", "")
        senior  = job.get("seniorityLevel", "")

        if _SKIP_TITLE.search(title):       continue
        if _SKIP_COMPANY.search(company):   continue
        if senior == "Mid-Senior level":    continue
        if _EXP_HIGH.search(desc):          continue
        if not _RELEVANT_TITLE.search(title): continue

        job_id = "li_" + str(job.get("id", ""))
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        # Detect direct company postings vs career-site aggregators
        apply_url = job.get("applyUrl", "") or ""
        is_direct = (
            "linkedin.com/jobs/apply" not in apply_url
            and not re.search(r'jobs\.lever\.co|greenhouse\.io|myworkdayjobs|smartrecruiters|ashbyhq', apply_url)
        )
        out.append({
            "id":       job_id,
            "source":   "linkedin",
            "title":    title,
            "company":  company,
            "location": job.get("location", ""),
            "url":      job.get("link", ""),
            "posted_at": job.get("postedAt", ""),
            "apply_url": apply_url,
            "applicants": job.get("applicantsCount", ""),
            "seniority": job.get("seniorityLevel", ""),
            "salary": job.get("salary", "") or "",
            "direct_posting": is_direct,
        })
    return out


def fetch_linkedin_jobs(lookback_hours: int = 2) -> list[dict]:
    """Run Apify scraper and return filtered job dicts ready for tracker.mark_seen()."""
    # Adjust f_TPR seconds based on lookback
    secs = lookback_hours * 3600
    urls = [u.replace("r7200", f"r{secs}") for u in _SEARCH_URLS]

    dataset_id = _run_actor(urls)
    items = _fetch_items(dataset_id)
    return _filter(items)
