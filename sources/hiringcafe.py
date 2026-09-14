"""
HiringCafe — Playwright scraper.

HiringCafe is a Next.js SPA; plain requests returns bare HTML with no job
content.  We use Playwright (headless Chromium) to load each search URL,
then try two strategies in order:

  1. Parse __NEXT_DATA__ — Next.js embeds pre-fetched JSON in
     <script id="__NEXT_DATA__">.  The job data lives at:
       props.pageProps.ssrHits[]
     Each hit has:
       requisition_id        → short slug used in /job/<id> URL
       v5_processed_job_data.core_job_title
       v5_processed_job_data.company_name
       v5_processed_job_data.formatted_workplace_location
       v5_processed_job_data.estimated_publish_date  (ISO string)
       v5_processed_job_data.estimated_publish_date_millis

  2. Fall back to rendered HTML — find all <a href="/job/..."> links and
     extract surrounding card text for title / company / date.

We never visit individual job detail pages (too slow).

Search URL pattern:
  https://hiring.cafe/?searchState={"searchQuery":"<term>"}
"""

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

log = logging.getLogger(__name__)

_BASE_URL = "https://hiringcafe.com/"
# HiringCafe moved domains (hiring.cafe -> hiringcafe.com) and changed the job
# route. Measured Aug 2026: /job/<id> now 404s, /jobs/<id> serves only the app
# shell, and ?job=<id> is the one that actually renders the posting.
_JOB_BASE = "https://hiringcafe.com/?job="

# Match ids from either the old /job/<id> path or the current ?job=<id> query
_JOB_ID_RE = re.compile(r'(?:/jobs?/|[?&]job=)([A-Za-z0-9]{8,})')

# Keywords to search for — aligned with config.py KEYWORDS
_SEARCH_QUERIES = [
    "data analyst",
    "data scientist",
    "ml engineer",
    "data engineer",
    "analytics engineer",
    "ai engineer",
    "gen ai",
    "llm engineer",
    "business analyst",
]

# Pages to fetch per query
_PAGES_PER_QUERY = 2

# Relative-date patterns: "2 days ago", "3 weeks ago", "1 month ago", "just now"
_REL_DATE_RE = re.compile(
    r'(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago',
    re.IGNORECASE,
)

# Senior-level title words to filter out (defense-in-depth)
_SENIOR_TITLE_WORDS = [
    "senior", "sr.", " sr ", "staff", "principal", "manager",
    "director", "head of", "vp ", "vice president",
]


def _parse_relative_date(text: str) -> str:
    """
    Find the first relative-date phrase in text and return an ISO datetime string.
    Returns "" if no relative date is found.
    """
    now = datetime.now(timezone.utc)
    m = _REL_DATE_RE.search(text)
    if not m:
        if re.search(r'\bjust\s+now\b', text, re.IGNORECASE):
            return now.isoformat()
        return ""
    n = int(m.group(1))
    unit = m.group(2).lower()
    deltas = {
        "second": timedelta(seconds=n),
        "minute": timedelta(minutes=n),
        "hour":   timedelta(hours=n),
        "day":    timedelta(days=n),
        "week":   timedelta(weeks=n),
        "month":  timedelta(days=n * 30),
        "year":   timedelta(days=n * 365),
    }
    dt = now - deltas.get(unit, timedelta(0))
    return dt.isoformat()


def _is_senior_title(title: str) -> bool:
    """Return True if the title indicates a level too senior to include."""
    t = title.lower()
    return any(word in t for word in _SENIOR_TITLE_WORDS)


def _build_url(query: str, page: int) -> str:
    state = json.dumps({"searchQuery": query}, separators=(",", ":"))
    encoded_state = quote(state, safe="")
    if page == 0:
        return f"{_BASE_URL}?searchState={encoded_state}"
    return f"{_BASE_URL}?searchState={encoded_state}&page={page}"


def _parse_iso_or_relative(date_str: str) -> str:
    """
    Normalise a date string to ISO format.  Accepts:
      - ISO strings (2024-03-15, 2024-03-15T12:00:00Z, etc.)
      - Epoch milliseconds as string or int
      - Relative strings ("2 days ago", "just now")
    Returns "" if unparseable.
    """
    if not date_str:
        return ""
    s = str(date_str).strip()
    # Try epoch millis (large integers)
    if re.fullmatch(r'\d{12,}', s):
        try:
            dt = datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
            return dt.isoformat()
        except (ValueError, OSError):
            pass
    # Try ISO first
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        pass
    # Try relative
    return _parse_relative_date(s)


def _extract_from_next_data(html: str) -> list[dict]:
    """
    Parse <script id="__NEXT_DATA__"> and return normalised job dicts.

    HiringCafe structure:
      next_data.props.pageProps.ssrHits[]
        .requisition_id             → slug for /job/<id>
        .v5_processed_job_data
          .core_job_title
          .company_name
          .formatted_workplace_location
          .estimated_publish_date   (ISO string)
          .estimated_publish_date_millis

    Returns [] if the script is absent or contains no job data.
    """
    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
                  html, re.DOTALL)
    if not m:
        return []
    try:
        next_data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []

    try:
        hits = next_data["props"]["pageProps"]["ssrHits"]
    except (KeyError, TypeError):
        log.debug("HiringCafe: __NEXT_DATA__ present but ssrHits missing")
        return []

    if not hits:
        log.debug("HiringCafe: __NEXT_DATA__ ssrHits is empty")
        return []

    log.debug(f"HiringCafe: __NEXT_DATA__ ssrHits has {len(hits)} entries")

    results: list[dict] = []
    for raw in hits:
        if not isinstance(raw, dict):
            continue
        # Skip internal pinned entries
        if raw.get("source") == "hiring_cafe_pin":
            continue

        # The short slug used in /job/<id> URL paths is stored as requisition_id
        job_id = str(raw.get("requisition_id") or raw.get("id") or "").strip()
        if not job_id:
            continue

        v5 = raw.get("v5_processed_job_data") or {}
        ec = raw.get("enriched_company_data") or {}
        ji = raw.get("job_information") or {}

        title = str(
            v5.get("core_job_title") or
            ji.get("title") or
            ji.get("job_title_raw") or ""
        ).strip()
        if not title:
            continue

        company = str(
            v5.get("company_name") or
            ec.get("name") or ""
        ).strip()

        location = str(
            v5.get("formatted_workplace_location") or ""
        ).strip()
        if not location:
            location = "United States"

        # Prefer the ISO date string; fall back to millis
        date_raw = (
            v5.get("estimated_publish_date") or
            v5.get("estimated_publish_date_millis") or
            ""
        )
        posted_at = _parse_iso_or_relative(str(date_raw))

        results.append({
            "id":        f"hiringcafe_{job_id}",
            "source":    "hiringcafe",
            "company":   company,
            "title":     title,
            "location":  location,
            "url":       f"{_JOB_BASE}{job_id}",
            "posted_at": posted_at,
        })

    return results


def _extract_from_html(html: str) -> list[dict]:
    """
    Fall-back HTML parser: find all <a href="/job/..."> links and extract
    nearby text for title, company, and date.
    Returns a list of partial dicts (posted_at may be empty).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        m = _JOB_ID_RE.match(a["href"])
        if not m:
            continue
        job_id = m.group(1)
        if job_id in seen:
            continue
        seen.add(job_id)

        # Grab surrounding text from the card (parent container)
        container = a
        for _ in range(4):   # walk up a few levels
            if container.parent:
                container = container.parent
            else:
                break

        card_text = container.get_text(" ", strip=True) if container else a.get_text(strip=True)

        # Title is usually the anchor text itself
        title = a.get_text(strip=True)
        if not title or len(title) < 3:
            title = card_text[:80] if card_text else ""

        location = "United States"
        company = ""

        # Look for relative date in card text
        posted_at = _parse_relative_date(card_text)

        results.append({
            "id":        f"hiringcafe_{job_id}",
            "source":    "hiringcafe",
            "company":   company,
            "title":     title,
            "location":  location,
            "url":       f"{_JOB_BASE}{job_id}",
            "posted_at": posted_at,
        })

    log.debug(f"HiringCafe HTML fallback: found {len(results)} job links")
    return results


def fetch_hiringcafe_jobs(cutoff: datetime) -> list[dict]:
    """
    Fetch jobs from HiringCafe matching the target keywords.
    Uses Playwright (headless Chromium) to render the Next.js SPA.
    Returns a list of normalised job dicts.
    """
    from playwright.sync_api import sync_playwright

    jobs: list[dict] = []
    seen_ids: set[str] = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = context.new_page()

        for query in _SEARCH_QUERIES:
            for pg in range(_PAGES_PER_QUERY):
                url = _build_url(query, pg)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    # Wait for job cards to appear
                    try:
                        page.wait_for_selector(
                            'a[href*="/job/"], a[href*="/jobs/"], a[href*="job="]',
                            timeout=12_000,
                        )
                    except Exception:
                        pass   # proceed even if selector never matches

                    html = page.content()
                except Exception as e:
                    log.debug(f"HiringCafe Playwright query={query!r} page={pg}: {e}")
                    break

                # Strategy 1: __NEXT_DATA__ (preferred — structured, has dates)
                page_jobs = _extract_from_next_data(html)
                used_strategy = "__NEXT_DATA__"

                # Strategy 2: rendered HTML fallback
                if not page_jobs:
                    page_jobs = _extract_from_html(html)
                    used_strategy = "HTML fallback"

                log.debug(
                    f"HiringCafe [{used_strategy}] query={query!r} page={pg}: "
                    f"{len(page_jobs)} jobs"
                )

                new_on_page = 0
                for job in page_jobs:
                    if job["id"] in seen_ids:
                        continue
                    seen_ids.add(job["id"])

                    # Defense-in-depth senior filter
                    if _is_senior_title(job["title"]):
                        log.debug(f"HiringCafe: skipping senior title: {job['title']!r}")
                        continue

                    # Apply cutoff filter — drop jobs with no parseable date
                    if not job["posted_at"]:
                        log.debug(f"HiringCafe {job['id']}: no date, skipping")
                        continue
                    try:
                        posted = datetime.fromisoformat(
                            job["posted_at"].replace("Z", "+00:00")
                        )
                        if posted.tzinfo is None:
                            posted = posted.replace(tzinfo=timezone.utc)
                        if posted < cutoff:
                            log.debug(
                                f"HiringCafe {job['id']}: too old "
                                f"({job['posted_at']}), skipping"
                            )
                            continue
                    except (ValueError, TypeError):
                        log.debug(
                            f"HiringCafe {job['id']}: unparseable date "
                            f"{job['posted_at']!r}, skipping"
                        )
                        continue

                    jobs.append(job)
                    new_on_page += 1

                log.debug(
                    f"HiringCafe kept {new_on_page} new jobs from "
                    f"query={query!r} page={pg}"
                )

                time.sleep(0.5)   # brief pause between pages

        page.close()
        context.close()
        browser.close()

    return jobs


# ── Quick smoke-test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s  %(message)s")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    print(f"Fetching HiringCafe jobs (cutoff: last 72 h)…")

    results = fetch_hiringcafe_jobs(cutoff)
    print(f"\nFound {len(results)} job(s):")
    for j in results[:10]:
        print(f"  [{j['source']}] {j['company']} — {j['title']} | {j['location']}")
        print(f"         posted_at={j['posted_at']}")
        print(f"         {j['url']}")

    sys.exit(0)
