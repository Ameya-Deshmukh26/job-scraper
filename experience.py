"""
How many years of experience a job description requires.

The rule is simple: find every number next to "years" and take it as a
requirement. The work is in not being fooled, so each mention is kept or
set aside for a stated reason:

  counted       "5+ years", "five (5) years", "minimum of 4 years",
                "at least 4 yrs", "4 or more years", "3+ years in analytics"
  a range       "2-5 years", "3 to 5 years": the lower bound is what is
                required, so it is the number used
  a choice      "Bachelor's and 5 years, or Master's and 3 years": the
                cheapest path is what is required, so the lowest number
  ignored       preferred / nice to have / bonus / ideally / a plus, and
                anything under a "Preferred qualifications" heading;
                ceilings ("up to 3 years", "less than 5 years");
                not experience ("4-year degree", "founded 25 years ago",
                "vests over 4 years", "over the past 10 years")

The job's requirement is the highest counted number across its sentences.
"""
from __future__ import annotations

import html as _html
import re

_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "twenty": 20,
}
_NUM = r"(?:\d{1,2}|" + "|".join(_WORDS) + r")"

# "5+ years", "five (5)+ years", "3-5 years", "3 to 5 yrs", "4 or more years"
_MENTION = re.compile(
    r"(?<![\w.$])(?P<lo>" + _NUM + r")(?:\s*\(\s*\d{1,2}\s*\))?\s*(?:\+|plus)?"
    r"(?:\s*(?:-|–|—|to)\s*(?P<hi>" + _NUM + r")(?:\s*\(\s*\d{1,2}\s*\))?\s*\+?)?"
    r"\s*(?:or\s+more\s+|or\s+greater\s+)?(?:years?|yrs?)\b",
    re.IGNORECASE,
)

# The mention is followed by something that is not work experience
_NOT_EXPERIENCE_AFTER = re.compile(
    r"^\W*(?:old|ago|of\s+age|degree|college|university|bachelor|program|course|"
    r"warranty|vesting|anniversary|in\s+business|of\s+(?:history|growth|operation|service\s+to))\b",
    re.IGNORECASE,
)
# ...or preceded by something that says it is history, a ceiling, or a plan
_NOT_REQUIREMENT_BEFORE = re.compile(
    r"(?:founded|established|history|celebrat\w*|anniversary|vest\w*|over\s+the\s+(?:past|last|next)|"
    r"for\s+(?:over|more\s+than|nearly|almost|about|close\s+to)|"
    r"for\s+(?:the\s+)?(?:past|last)|in\s+the\s+(?:next|coming|last|past)|within|every|"
    r"up\s+to|less\s+than|under|no\s+more\s+than|fewer\s+than|maximum\s+of|max\.?)"
    r"\W*(?:\w+\W+){0,2}$",
    re.IGNORECASE,
)
_PREFERRED = re.compile(r"\b(?:prefer\w*|nice[\s-]to[\s-]have|bonus|a\s+plus|ideally|desired|desirable|optional)\b",
                        re.IGNORECASE)
_REQUIRED_HEADING = re.compile(r"\b(?:require\w*|minimum|basic|must|qualifications|what\s+you|you\s+have|"
                               r"about\s+you|who\s+you\s+are|responsibilities)\b", re.IGNORECASE)
# Degree words, by level, for sentences that offer a path per degree
_DEGREE_LEVELS = [
    (3, r"ph\.?\s?d\.?|doctora\w*"),
    (2, r"master\w*|m\.s\.?|m\.a\.?|ms|ma|mba|m\.?eng"),
    (1, r"bachelor\w*|b\.s\.?|b\.a\.?|bs|ba|b\.?tech|undergraduate"),
]
_DEGREE = re.compile(r"(?<![a-z])(?:" + "|".join(p for _, p in _DEGREE_LEVELS) + r")(?![a-z])", re.IGNORECASE)
LEVELS = {"bachelors": 1, "masters": 2, "phd": 3}
_MAX_REAL_YEARS = 15     # "20+ years" or "for 30 years" is never an entry requirement


def _degree_level(word: str) -> int:
    for level, pat in _DEGREE_LEVELS:
        if re.fullmatch(pat, word, re.IGNORECASE):
            return level
    return 0


def _split_degrees(seg: str) -> tuple[list[int], list[int], list[int]]:
    """Degree levels before the first years mention, after the last one, and the counted years."""
    mentions = [m for m in _MENTION.finditer(seg)]
    counted = _counted(seg)
    if not counted:
        return [_degree_level(m.group(0)) for m in _DEGREE.finditer(seg)], [], []
    first, last = mentions[0].start(), mentions[-1].end()
    pre = [_degree_level(m.group(0)) for m in _DEGREE.finditer(seg) if m.start() < first]
    post = [_degree_level(m.group(0)) for m in _DEGREE.finditer(seg) if m.start() >= last]
    return pre, post, counted


def _path_years(sentence: str, my_level: int) -> int | None:
    """
    For a sentence offering one path per degree, the lowest years among the
    paths this candidate's degree qualifies for. None if the sentence is not
    that kind of sentence (fewer than two degree levels, or no "or").

      "Bachelors + 8 years or Masters + 6 years or PhD + 3 years"   -> 6 for a Master's
      "Master's degree, or Bachelor's degree and 5+ years"         -> 0 for a Master's
      "PhD with 1-3 years, MS or MA with 2-6 years, or BS with 4-8" -> 2 for a Master's
      "5 years with a BS, or 2 years with an MS"                    -> 2 for a Master's

    The sentence is split at each "or". A degree that trails a segment's
    years belongs to the next path when that path names its own degree
    before its years ("..., MS or MA with 2-6 years"), and to this one
    otherwise ("5 years with a BS, or ...").
    """
    levels = {_degree_level(m.group(0)) for m in _DEGREE.finditer(sentence)}
    if len(levels) < 2 or not re.search(r"\bor\b", sentence, re.I):
        return None
    texts = re.split(r"\bor\b", sentence, flags=re.I)
    segs = [_split_degrees(t) for t in texts]
    paths: list[tuple[int, int]] = []
    carry: list[int] = []
    for i, (pre, post, years) in enumerate(segs):
        if years:
            need = max(years)
            nxt = segs[i + 1] if i + 1 < len(segs) else None
            post_goes_forward = bool(post) and nxt is not None and bool(nxt[0])
            owners = carry + pre + ([] if post_goes_forward else post)
            paths += [(lvl, need) for lvl in owners] or [(0, need)]
            carry = post if post_goes_forward else []
        elif pre:
            if len(texts[i].split()) <= 3:
                carry += pre                 # "MS" in "MS or MA with 2-6 years": waits for its years
            else:
                paths += [(lvl, 0) for lvl in carry + pre]   # "Master's degree in a quantitative field,"
                carry = []
    # degrees never given years are a path of their own: no years needed
    paths += [(lvl, 0) for lvl in carry]
    eligible = [n for lvl, n in paths if lvl <= my_level]
    return min(eligible) if eligible else None

def html_to_text(raw: str) -> str:
    """HTML (or HTML-escaped HTML, as Greenhouse sends it) to plain text with line breaks."""
    s = _html.unescape(raw or "")
    s = re.sub(r"(?i)<\s*(?:br|/p|/div|/li|/h\d|/tr|li|p|h\d)\b[^>]*>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"[ \t\xa0]+", " ", s).strip()


def _value(token: str) -> int:
    t = token.lower()
    return _WORDS[t] if t in _WORDS else int(t)


def _is_heading(line: str) -> bool:
    """
    "Preferred Qualifications", "Nice to have", "Requirements:". Deliberately
    narrow: a bullet such as "Bonus if you know Go" must not switch every
    line after it into the preferred section.
    """
    if len(line) > 60 or _MENTION.search(line):
        return False
    words = line.rstrip(":").split()
    return (line.endswith(":") or len(words) <= 4
            or all(w[:1].isupper() or not w[:1].isalpha() for w in words))


def _sentences(text: str):
    """(sentence, under_preferred_heading) pairs, tracking section headings line by line."""
    preferred_section = False
    for line in re.split(r"\n+", text or ""):
        line = line.strip(" \t•·*-–—")
        if not line:
            continue
        if _is_heading(line):
            if _PREFERRED.search(line):
                preferred_section = True
            elif _REQUIRED_HEADING.search(line):
                preferred_section = False
            continue
        for sentence in re.split(r"(?<=[.;!?])\s+(?=[A-Z(])", line):
            yield sentence, preferred_section


def _counted(sentence: str) -> list[int]:
    """Numbers in one sentence that are real requirements."""
    out = []
    for m in _MENTION.finditer(sentence):
        before, after = sentence[:m.start()], sentence[m.end():]
        if _NOT_EXPERIENCE_AFTER.search(after) or _NOT_REQUIREMENT_BEFORE.search(before):
            continue
        n = _value(m.group("lo"))
        if n <= _MAX_REAL_YEARS:
            out.append(n)
    return out


def _my_level(degree: str | None) -> int:
    if degree is None:
        try:
            from config import HIGHEST_DEGREE as degree
        except Exception:
            degree = "bachelors"
    return LEVELS.get((degree or "bachelors").lower(), 1)


def required_years(text: str, degree: str | None = None) -> tuple[int | None, str]:
    """
    (years required, the sentence it came from), or (None, "") when the text
    states no requirement. `degree` is the candidate's highest degree
    ("bachelors" / "masters" / "phd"), which picks the path in sentences that
    offer one per degree; it defaults to HIGHEST_DEGREE in search_profile.py.
    """
    my_level = _my_level(degree)
    best, evidence = None, ""
    for sentence, preferred_section in _sentences(text):
        if preferred_section or _PREFERRED.search(sentence):
            continue
        nums = _counted(sentence)
        if not nums:
            continue
        # "Bachelor's + 8 years or Master's + 6 years": the path this degree gets
        path = _path_years(sentence, my_level)
        need = path if path is not None else max(nums)
        if best is None or need > best:
            best, evidence = need, re.sub(r"\s+", " ", sentence).strip()[:160]
    return best, evidence


def too_senior(text: str, max_years: int, degree: str | None = None) -> str | None:
    """The evidence sentence when the job requires max_years or more, else None."""
    need, evidence = required_years(text, degree)
    return evidence if need is not None and need >= max_years else None
