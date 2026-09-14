"""
Hacker News "Ask HN: Who is hiring?" — the best free startup job source.

A single thread is posted monthly by user `whoishiring` and collects a few
hundred top-level comments, one per company. Heavily weighted toward startups
and small engineering teams, which is exactly the segment the ATS-based
sources miss.

Free, no auth, no rate limits worth worrying about:
  thread list : /search_by_date?tags=story,author_whoishiring
  thread body : /items/<id>   (returns all comments in one call)

Comment convention (loose but consistent):
  Company | Role(s) | Location | Full Time | tech stack | apply link
"""
import html
import logging
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
_ITEM = "https://hn.algolia.com/api/v1/items/{}"

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "JobScraper/1.0 (personal job alerts)"})

# A real job title needs a role NOUN. Matching loose words like "AI" or
# "analytics" pulled in prose ("how we're thinking about AI at Ashby") and
# produced junk titles like "Ai", so require noun + domain qualifier.
_TITLE_RE = re.compile(
    r"(?<![A-Za-z])("
    r"(?:senior|sr\.?|junior|jr\.?|founding|entry[- ]level|associate)?\s*"
    r"(?:data|ml|machine[- ]learning|ai|ai/ml|ml/ai|analytics|nlp|llm|genai|"
    r"applied|research|bi|business[- ]intelligence|quantitative)"
    r"[\s/&-]{1,3}"
    r"(?:engineer|scientist|analyst|developer|researcher)s?"
    r")(?![A-Za-z])",
    re.I,
)

# Comments mentioning these are not for Ameya
_SENIOR = re.compile(r"\b(staff|principal|director|head of|vp of|vice president|"
                     r"distinguished|fellow|lead engineer|engineering manager)\b", re.I)

_REMOTE = re.compile(r"\bremote\b", re.I)
_URL = re.compile(r'href="([^"]+)"')
_NOT_A_NAME = {"we", "i", "our", "my", "the", "this", "that", "hi", "hello",
               "hey", "looking", "hiring", "join", "come", "help", "apply",
               "seeking", "want", "wanted", "please", "there", "here", "at"}
_HOST_BLOCKLIST = {"grnh", "greenhouse", "lever", "ashbyhq", "workable", "news",
                   "ycombinator", "notion", "docs", "google", "youtube", "linkedin",
                   "uctalent", "bit", "tinyurl", "forms", "airtable"}


def _newest_thread() -> dict | None:
    """Most recent 'Who is hiring?' story (not 'Who wants to be hired')."""
    try:
        r = _SESSION.get(_SEARCH, params={"tags": "story,author_whoishiring",
                                          "hitsPerPage": 12}, timeout=20)
        r.raise_for_status()
        for h in r.json().get("hits", []):
            title = (h.get("title") or "").lower()
            if "who is hiring" in title:
                return h
    except Exception as e:
        log.warning(f"HN: could not list threads: {e}")
    return None


def _plain(text_html: str) -> str:
    soup = BeautifulSoup(html.unescape(text_html or ""), "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def _pick_role(text: str) -> str | None:
    """Return the first realistic job title in the comment, or None."""
    m = _TITLE_RE.search(text)
    if not m:
        return None
    title = re.sub(r"\s+", " ", m.group(1)).strip(" ,-|/")
    # Prefer a slightly wider window if the match is immediately followed by a
    # qualifier like ", Platform" that makes the title more informative
    tail = text[m.end():m.end() + 34]
    q = re.match(r"\s*,\s*([A-Z][A-Za-z /&-]{2,28})", tail)
    if q:
        title = f"{title}, {q.group(1).strip()}"
    return title.title() if title.islower() else title


def _company_of(text, raw_html):
    """
    Company name from a freeform HN comment. Segment 1 is usually the company,
    but many comments inline the URL or run straight into prose
    ("Sumble is the newco..."), so trim aggressively and sanity-check.
    """
    def from_domain():
        m = re.search(r"https?://(?:www\.)?([a-z0-9][a-z0-9-]{1,30})\.", raw_html or "", re.I)
        if not m or m.group(1).lower() in _HOST_BLOCKLIST:
            return None
        return m.group(1).replace("-", " ").title()

    first = text.split("|")[0]
    first = re.sub(r"https?://\S+", " ", first)          # inline URLs
    first = re.sub(r"\(.*?\)", " ", first)               # parentheticals
    # cut where the name stops and prose begins
    first = re.split(r"\s+(?:is|are|was|builds?|makes?|helps?|provides?|the|a|an)\s+",
                     first, maxsplit=1, flags=re.I)[0]
    first = re.split(r"[.,;:–—]", first)[0]
    first = first.strip(" -|:–—")
    words = first.split()

    # A sentence opener is prose, not a company ("We are hiring...")
    lead_is_prose = bool(words) and words[0].lower() in _NOT_A_NAME
    plausible = (first and len(words) <= 4 and len(first) <= 34
                 and not lead_is_prose
                 and not _TITLE_RE.search(first))
    return (first if plausible else None) or from_domain() or "Unknown"


def _location_of(text: str) -> str:
    """Pick a plausible location segment. Never return the job title."""
    if _REMOTE.search(text):
        return "Remote"
    for seg in text.split("|")[1:5]:
        seg = seg.strip(" .,-")
        if not seg or len(seg) > 44:
            continue
        if _TITLE_RE.search(seg):          # that segment is the role, not a place
            continue
        if re.search(r"full[- ]?time|part[- ]?time|contract|intern", seg, re.I):
            continue
        if re.search(r"[A-Z]{2}(?![A-Za-z])|,\s*[A-Z][a-z]+|(onsite|on-site|hybrid)",
                     seg, re.I):
            return seg
    return "Unspecified"


def fetch_hackernews_jobs(cutoff: datetime) -> list[dict]:
    """Parse the current month's Who-is-hiring thread into job dicts."""
    thread = _newest_thread()
    if not thread:
        return []
    tid = thread["objectID"]
    log.info(f"HN: reading thread {tid} - {thread.get('title')}")

    try:
        r = _SESSION.get(_ITEM.format(tid), timeout=45)
        r.raise_for_status()
        children = r.json().get("children") or []
    except Exception as e:
        log.warning(f"HN: could not fetch thread {tid}: {e}")
        return []

    results: list[dict] = []
    for c in children:
        raw = c.get("text") or ""
        if not raw:
            continue
        text = _plain(raw)
        if not text:
            continue

        role = _pick_role(text)
        if not role:
            continue
        if _SENIOR.search(role):
            continue

        # Prefer an explicit apply/careers link, else the first link, else HN
        links = _URL.findall(raw)
        url = next((u for u in links
                    if re.search(r"jobs|careers|apply|greenhouse|lever|ashby", u, re.I)),
                   links[0] if links else
                   f"https://news.ycombinator.com/item?id={c.get('id')}")

        posted = ""
        if c.get("created_at"):
            try:
                posted = datetime.fromisoformat(
                    c["created_at"].replace("Z", "+00:00")).isoformat()
            except Exception:
                pass

        results.append({
            "id":        f"hn_{c.get('id')}",
            "source":    "hackernews",
            "company":   _company_of(text, raw),
            "title":     role,
            "location":  _location_of(text),
            "url":       html.unescape(url),
            "posted_at": posted,
        })

    log.info(f"HN: {len(results)} relevant postings from {len(children)} comments")
    return results


if __name__ == "__main__":
    from datetime import timedelta
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    jobs = fetch_hackernews_jobs(datetime.now(timezone.utc) - timedelta(days=40))
    print(f"\n{len(jobs)} jobs\n")
    for j in jobs[:18]:
        print(f"  {j['title'][:44]:<44} | {j['company'][:22]:<22} | {j['location'][:16]:<16}")
        print(f"     {j['url'][:96]}")
