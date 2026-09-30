"""
Job type, workplace and pay, normalised across sources.

Each source reports these differently ("FullTime", "Full time", "full-time",
"Contractor", "hybrid", "Work from home"), and many say nothing, so a
source's own value is used when it has one and the title and location are
read otherwise.

    job_type   Full-time | Part-time | Contract | Internship | Temporary | ""
    workplace  Remote | Hybrid | On-site | ""
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_TYPE_WORDS = [
    ("Internship", r"\b(?:intern|internship|co-?op)\b"),
    ("Contract",   r"\b(?:contract\w*|contractor|freelance|1099|c2c|corp[\s-]to[\s-]corp|w-?2)\b"),
    ("Temporary",  r"\b(?:temp|temporary|seasonal)\b"),
    ("Part-time",  r"\bpart[\s-]?time\b"),
    ("Full-time",  r"\bfull[\s-]?time\b|\bpermanent\b|\bregular\b"),
]
_PLACE_WORDS = [
    ("Hybrid",  r"\bhybrid\b"),
    ("Remote",  r"\bremote\b|\bwork\s+from\s+home\b|\bwfh\b|\btelecommut\w*|\banywhere\b"),
    ("On-site", r"\bon[\s-]?site\b|\bin[\s-]?office\b|\bin[\s-]?person\b"),
]


def _first(patterns, *texts) -> str:
    blob = " ".join(t for t in texts if t)
    for label, pat in patterns:
        if re.search(pat, blob, re.IGNORECASE):
            return label
    return ""


def job_type(raw: str = "", title: str = "") -> str:
    """A source's own type if it has one ("FullTime", "Contractor"), else the title's."""
    return _first(_TYPE_WORDS, re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw or "")) or _first(_TYPE_WORDS, title)


def workplace(raw: str = "", title: str = "", location: str = "") -> str:
    """A source's own workplace if it has one ("Hybrid", "remote"), else the title's and location's."""
    return _first(_PLACE_WORDS, raw) or _first(_PLACE_WORDS, title, location)


_MONEY = re.compile(
    r"(?:[$€£₹]\s?\d[\d,.]*\s?[kK]?(?:\s?(?:-|–|to)\s?[$€£₹]?\s?\d[\d,.]*\s?[kK]?)?"
    r"(?:\s*(?:/|per|an?|each)\s*(?:yr|year|hour|hr|month|annum))?)", re.IGNORECASE)


def pay_from_text(text: str) -> str:
    """The first salary-looking figure in free text ("$120k-$150k", "$45/hr"), or ""."""
    m = _MONEY.search(text or "")
    return m.group(0).strip() if m else ""


_AGE = re.compile(r"(\d+)\s*\+?\s*(minute|min|hour|hr|day|week|month)", re.IGNORECASE)


def age_to_datetime(text: str) -> datetime | None:
    """ "5 hours ago" / "2 days ago" / "Just now" -> an approximate UTC time, or None."""
    t = (text or "").lower()
    now = datetime.now(timezone.utc)
    if "just" in t or "moment" in t or "today" in t:
        return now
    if "yesterday" in t:
        return now - timedelta(days=1)
    m = _AGE.search(t)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    step = {"min": timedelta(minutes=1), "minute": timedelta(minutes=1), "hour": timedelta(hours=1),
            "hr": timedelta(hours=1), "day": timedelta(days=1), "week": timedelta(weeks=1),
            "month": timedelta(days=30)}[unit]
    return now - n * step


# Labelled lines only ("Employment type: Contract", "Workplace type: Remote").
# Free text is not read: "contract negotiations" is not a contract role.
_TYPE_LABEL = re.compile(r"(?:employment|job|position|work)\s*type\s*[:\-]\s*([A-Za-z][A-Za-z \-]{2,30})", re.I)
_PLACE_LABEL = re.compile(r"(?:workplace|work\s*(?:arrangement|model|location)|location)\s*type\s*[:\-]\s*"
                          r"([A-Za-z][A-Za-z \-]{2,20})", re.I)


def labels_from_text(text: str) -> tuple[str, str]:
    """(job_type, workplace) from labelled lines in a description, "" when absent."""
    t = _TYPE_LABEL.search(text or "")
    w = _PLACE_LABEL.search(text or "")
    return (job_type(t.group(1)) if t else "", workplace(w.group(1)) if w else "")
