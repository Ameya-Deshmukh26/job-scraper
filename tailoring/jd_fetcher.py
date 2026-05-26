"""Fetch and clean job description text from a posting URL."""
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


def fetch_jd(url: str) -> str:
    """Return cleaned job description text, truncated to 4 000 chars."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        return f"[Could not fetch job description: {exc}]"

    soup = BeautifulSoup(resp.text, "html.parser")

    if "greenhouse.io" in url:
        text = _greenhouse(soup)
    elif "lever.co" in url:
        text = _lever(soup)
    else:
        text = _generic(soup)

    return _clean(text)


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
