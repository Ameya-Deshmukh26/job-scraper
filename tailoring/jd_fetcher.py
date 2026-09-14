"""Fetch and clean job description text from a posting URL."""
import os
import re
import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# Firecrawl fallback for JS-rendered career sites (Workday, Phenom, etc.)
_FIRECRAWL_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
_FIRECRAWL_URL = "https://api.firecrawl.dev/v2/scrape"


# The guest API rate-limits bursts — serialize LinkedIn JD fetches with a
# small delay so parallel JD checks don't get 429'd into empty responses.
import threading as _threading
import time as _time
_LI_LOCK = _threading.Lock()


def _linkedin_jd(url: str) -> str:
    """LinkedIn job pages need login, but the guest jobPosting API does not.
    Extract the job ID from /jobs/view/{id} and fetch the JD directly."""
    m = re.search(r"/jobs/view/(\d+)", url)
    if not m:
        return ""
    api = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}"
    with _LI_LOCK:
        for attempt in range(3):
            resp = requests.get(api, headers=_HEADERS, timeout=15)
            if resp.status_code == 200 and len(resp.text) > 1000:
                break
            _time.sleep(1.5 * (attempt + 1))   # back off and retry
        _time.sleep(0.8)   # pace the next caller
    if resp.status_code != 200:
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    desc = soup.find(class_="show-more-less-html__markup")
    return desc.get_text("\n") if desc else ""


def _firecrawl_jd(url: str) -> str:
    """Scrape a JS-rendered page via Firecrawl. Returns markdown or ''."""
    if not _FIRECRAWL_KEY:
        return ""
    try:
        resp = requests.post(
            _FIRECRAWL_URL,
            headers={"Authorization": f"Bearer {_FIRECRAWL_KEY}",
                     "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            timeout=60,
        )
        data = resp.json()
        if data.get("success"):
            return data["data"].get("markdown", "")
    except Exception:
        pass
    return ""


def fetch_jd(url: str) -> str:
    """Return cleaned job description text, truncated to 4 000 chars."""
    # LinkedIn: use the guest API (the job page itself requires login)
    if "linkedin.com/jobs" in url:
        try:
            text = _linkedin_jd(url)
            if text:
                return _clean(text)
        except Exception as exc:
            return f"[Could not fetch job description: {exc}]"
        return "[Could not fetch job description: no guest data]"

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        # Blocked or JS-only page — try Firecrawl before giving up
        text = _firecrawl_jd(url)
        if text:
            return _clean(text)
        return f"[Could not fetch job description: {exc}]"

    soup = BeautifulSoup(resp.text, "html.parser")

    if "greenhouse.io" in url:
        text = _greenhouse(soup)
    elif "lever.co" in url:
        text = _lever(soup)
    else:
        text = _generic(soup)

    cleaned = _clean(text)
    # Thin result usually means a JS-rendered shell — Firecrawl gets the real DOM
    if len(cleaned) < 300:
        fc = _firecrawl_jd(url)
        if len(fc) > len(cleaned):
            return _clean(fc)
    return cleaned


def _greenhouse(soup):
    for sel in ["#content", ".job-description", "#job_description", ".job__description"]:
        el = soup.select_one(sel)
        if el:
            return el.get_text("\n")
    return _generic(soup)


def _lever(soup):
    for sel in [".posting-description", ".section--text", "[data-qa='job-description']"]:
        el = soup.select_one(sel)
        if el:
            return el.get_text("\n")
    return _generic(soup)


def _generic(soup):
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    for sel in ["main", "article", ".job-description", "#job-description", ".description"]:
        el = soup.select_one(sel)
        if el:
            return el.get_text("\n")
    return soup.body.get_text("\n") if soup.body else soup.get_text("\n")


def _clean(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()
    if len(text) > 4000:
        text = text[:4000] + "\n[... truncated ...]"
    return text
