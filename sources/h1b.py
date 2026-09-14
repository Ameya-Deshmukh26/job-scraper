"""
H-1B sponsorship lookup from USCIS Employer Data Hub (public CSV).

Downloads FY2021–2023 data on first use, caches to data/h1b_cache.pkl.
Provides is_h1b_sponsor(company) → bool using fuzzy name normalization.

Data source: https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub
"""
import logging
import os
import pickle
import re
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).parent.parent / "data" / "h1b_cache.pkl"
_YEARS      = [2023, 2022, 2021]   # last 3 fiscal years
_BASE_URL   = "https://www.uscis.gov/sites/default/files/document/data/h1b_datahubexport-{year}.csv"

# Legal suffixes to strip during normalization
_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|"
    r"group|holdings|holding|technologies|technology|tech|services|service|"
    r"solutions|solution|systems|system|global|international|associates|"
    r"consulting|consultants|enterprises|enterprise|labs|laboratory|"
    r"software|networks|network|digital|innovations|innovation|partners|"
    r"partnership|ventures|venture|capital|management|resources|staffing|"
    r"professionals|professional|dba|lp|llp|na|usa|us)\b"
)
_PUNCT = re.compile(r"[^a-z0-9\s]")
_SPACE = re.compile(r"\s+")


def _normalize(name: str) -> str:
    n = name.lower()
    n = _PUNCT.sub(" ", n)
    n = _SUFFIXES.sub(" ", n)
    n = _SPACE.sub(" ", n).strip()
    return n


def _download_year(year: int) -> set:
    url = _BASE_URL.format(year=year)
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.warning(f"H-1B: could not download {year} data: {e}")
        return set()

    sponsors = set()
    lines = r.text.splitlines()
    for line in lines[1:]:   # skip header
        parts = line.split(",")
        if len(parts) < 3:
            continue
        # CSV fields: FiscalYear, Employer, InitialApproval, InitialDenial, ...
        employer = parts[1].strip().strip('"')
        try:
            initial_approvals = int(parts[2].strip().strip('"'))
        except ValueError:
            continue
        if initial_approvals > 0 and employer:
            n = _normalize(employer)
            if len(n) >= 4:   # skip garbage / single-word fragments
                sponsors.add(n)
    return sponsors


def _load_sponsors() -> set:
    """Load from cache or download fresh."""
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Use cache if it exists and is less than 30 days old
    if _CACHE_PATH.exists():
        age_days = (time.time() - _CACHE_PATH.stat().st_mtime) / 86400
        if age_days < 30:
            with open(_CACHE_PATH, "rb") as f:
                sponsors = pickle.load(f)
            log.info(f"H-1B: loaded {len(sponsors):,} sponsors from cache")
            return sponsors

    log.info("H-1B: downloading sponsorship data...")
    sponsors: set = set()
    for year in _YEARS:
        year_set = _download_year(year)
        sponsors |= year_set
        log.info(f"H-1B: {year} → {len(year_set):,} sponsors (+{len(sponsors):,} total)")
        time.sleep(0.5)

    with open(_CACHE_PATH, "wb") as f:
        pickle.dump(sponsors, f)
    log.info(f"H-1B: cached {len(sponsors):,} unique sponsors")
    return sponsors


# Module-level caches — loaded once per process
_SPONSORS: set | None = None
# Precomputed set of all 5-char prefixes from sponsor names (for O(1) prefix lookup)
_PREFIXES: set | None = None


def _build_indexes(sponsors: set) -> set:
    """Build prefix index: all 5-char+ leading substrings of every sponsor name."""
    prefixes = set()
    for name in sponsors:
        if len(name) >= 5:
            # Store all prefix lengths from 5 up to full length
            for end in range(5, len(name) + 1):
                prefixes.add(name[:end])
    return prefixes


def get_sponsors() -> tuple:
    global _SPONSORS, _PREFIXES
    if _SPONSORS is None:
        _SPONSORS = _load_sponsors()
        _PREFIXES = _build_indexes(_SPONSORS)
        log.debug(f"H-1B: prefix index has {len(_PREFIXES):,} entries")
    return _SPONSORS, _PREFIXES


def is_h1b_sponsor(company: str) -> bool:
    """
    Return True if the company has approved H-1B petitions in the last 3 years.
    O(1) lookup via precomputed prefix index.
    """
    if not company:
        return False
    sponsors, prefixes = get_sponsors()
    normalized = _normalize(company)
    if not normalized:
        return False

    # Exact match (handles "google llc" → "google" after normalization)
    if normalized in sponsors:
        return True

    # Prefix match: check if normalized IS a prefix of any sponsor name
    # e.g. "amazon" matches "amazon com" because "amazon" is in prefix index
    if len(normalized) >= 5 and normalized in prefixes:
        return True

    # Reverse prefix: check if any sponsor name is a prefix of normalized
    # e.g. "amazon com services" matches sponsor "amazon com"
    if len(normalized) >= 5:
        for end in range(5, len(normalized) + 1):
            if normalized[:end] in sponsors:
                return True

    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    test = ["Google", "Amazon", "McKinsey", "TCS", "Wipro", "Stripe",
            "Anthropic", "OpenAI", "Capital One", "JPMorgan Chase",
            "Rivago Infotech", "Some Random Startup XYZ"]
    for co in test:
        print(f"  {'YES' if is_h1b_sponsor(co) else 'NO ':3s}  {co}")
