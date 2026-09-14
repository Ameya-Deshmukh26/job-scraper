"""
CV corpus — the base resume parsed into typed, addressable items.

Every tailored bullet the agent produces must trace back to one of these
items. Nothing is generated from thin air, so fabrication becomes a
checkable property rather than a hope (see validator.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

BASE_TEX = Path(r"C:\Users\ameya\Downloads\Ameya_Deshmukh_BASE_v3.tex")

# \resumeItem{...} — brace-balanced so nested \textbf{} survives
_ITEM_CMD = r"\resumeItem{"
_SECTION = re.compile(r"\\section\{([^}]+)\}")
_SUBHEAD = re.compile(
    r"\\resumeSubheading\s*\{([^}]*)\}\{([^}]*)\}\s*\{([^}]*)\}\{([^}]*)\}", re.S
)
_PROJHEAD = re.compile(r"\\resumeProjectHeading\s*\{(.+?)\}\{(\d{4})\}", re.S)

# Numeric claims: 500+, 60%, 2M+, 768-dim, 0.21, 910K+, 3.75/4.0, 35%
_NUMBER = re.compile(r"\d+(?:\.\d+)?\s*(?:%|\+|[KMB]\b\+?|-dim)?", re.I)

_TEX_NOISE = re.compile(r"\\(?:textbf|underline|textnormal|href)\b|[{}$]|\\\\|\\&")


def strip_tex(s: str) -> str:
    """Render LaTeX fragment to plain text for comparison."""
    s = re.sub(r"\\href\{[^}]*\}", " ", s)
    s = _TEX_NOISE.sub(" ", s)
    s = s.replace(r"\%", "%").replace("~", " ")
    return re.sub(r"\s+", " ", s).strip()


def numbers_in(text: str) -> set[str]:
    """Normalized numeric claims in a string — the metric-lock fingerprint."""
    out = set()
    for m in _NUMBER.finditer(text or ""):
        tok = re.sub(r"\s+", "", m.group(0)).upper().rstrip(".")
        if tok and any(c.isdigit() for c in tok):
            out.add(tok)
    return out


@dataclass
class CorpusItem:
    """One addressable, factual unit of Ameya's history."""
    id: str
    section: str          # WORK EXPERIENCE | PROJECTS
    org: str              # employer or project name
    role: str             # job title, or project tech stack
    period: str
    text: str             # plain-text bullet
    numbers: set[str] = field(default_factory=set)

    def __post_init__(self):
        if not self.numbers:
            self.numbers = numbers_in(self.text)


def _balanced_items(body: str) -> list[str]:
    """Extract \resumeItem{...} payloads, respecting nested braces."""
    items, i = [], 0
    while True:
        start = body.find(_ITEM_CMD, i)
        if start == -1:
            return items
        j = start + len(_ITEM_CMD)
        depth, buf = 1, []
        while j < len(body) and depth:
            c = body[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            buf.append(c)
            j += 1
        items.append("".join(buf))
        i = j + 1


def load_corpus(tex_path: Path | str = BASE_TEX) -> list[CorpusItem]:
    """Parse the base resume into typed corpus items."""
    raw = Path(tex_path).read_text(encoding="utf-8", errors="replace")
    # Drop the preamble (macro definitions contain \resumeItem too)
    body = raw.split(r"\begin{document}", 1)[-1]

    # Index section boundaries
    marks = [(m.start(), m.group(1).strip()) for m in _SECTION.finditer(body)]

    def section_at(pos: int) -> str:
        cur = "UNKNOWN"
        for start, name in marks:
            if start <= pos:
                cur = name
            else:
                break
        return cur

    # Blocks are delimited by whichever heading precedes them
    heads: list[tuple[int, str, str, str]] = []
    for m in _SUBHEAD.finditer(body):
        heads.append((m.start(), m.group(3).strip(), m.group(1).strip(), m.group(2).strip()))
    for m in _PROJHEAD.finditer(body):
        title = strip_tex(m.group(1))
        name = title.split("|")[0].strip()
        stack = " | ".join(p.strip() for p in title.split("|")[1:] if "Link" not in p)
        heads.append((m.start(), name, stack, m.group(2).strip()))
    heads.sort(key=lambda h: h[0])

    items: list[CorpusItem] = []
    for idx, (pos, org, role, period) in enumerate(heads):
        end = heads[idx + 1][0] if idx + 1 < len(heads) else len(body)
        for k, payload in enumerate(_balanced_items(body[pos:end])):
            text = strip_tex(payload)
            if not text:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", org.lower()).strip("-")[:28]
            items.append(CorpusItem(
                id=f"{slug}-{k}",
                section=section_at(pos),
                org=org, role=role, period=period, text=text,
            ))
    return items


def corpus_numbers(items: list[CorpusItem]) -> set[str]:
    """Every numeric claim Ameya can legitimately make."""
    out: set[str] = set()
    for it in items:
        out |= it.numbers
    return out


if __name__ == "__main__":
    items = load_corpus()
    print(f"{len(items)} corpus items\n")
    for it in items:
        print(f"[{it.id:32s}] {it.section[:12]:12s} {it.org[:24]:24s} ({it.period})")
        print(f"   {it.text[:100]}")
        if it.numbers:
            print(f"   numbers: {sorted(it.numbers)}")
    print(f"\nAll legitimate numbers: {sorted(corpus_numbers(items))}")
