"""
Startup registry — decides whether a tracked job is at a startup, and
attaches the evidence (YC batch, team size) rather than guessing.

Two signals, both factual:
  1. the company matches a Y Combinator company whose ATS board we probed
     and confirmed live (data/board_probe.json, written by discover_boards.py)
  2. the job came from a startup-first source (HN Who-is-hiring, RemoteOK)

Company names arrive in two shapes: ATS sources store the board slug
("nox-metals"), while LinkedIn/HiringCafe store a display name ("Nox Metals"),
so everything is compared on a normalised key.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

PROBE_CACHE = Path(__file__).parent / "data" / "board_probe.json"

# Sources whose entire inventory is startup / small-company by nature
STARTUP_SOURCES = {"hackernews", "remoteok"}

# YC alumni never stop being YC companies, but Stripe (7,000 staff), Checkr
# (800) and Benchling (750) are not startups. Cap by headcount so the badge
# means "small company", which is what it is actually useful for.
MAX_TEAM = 250

_LEGAL = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|labs?|"
                    r"technologies|technology|ai|io)\b")


def _key(name: str) -> str:
    """Normalise a company name or slug to a comparable key."""
    s = re.sub(r"[^a-z0-9]+", " ", (name or "").lower())
    s = _LEGAL.sub(" ", s)
    return re.sub(r"\s+", "", s)


_REGISTRY: dict[str, dict] | None = None


def registry() -> dict[str, dict]:
    """key -> {name, batch, team, ats, slug} for confirmed-live YC boards."""
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY

    reg: dict[str, dict] = {}
    if PROBE_CACHE.exists():
        try:
            probe = json.loads(PROBE_CACHE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"startups: could not read probe cache: {e}")
            probe = {}
        for res in probe.values():
            for ats, info in (res.get("found") or {}).items():
                # skip empty boards and flagged slug collisions
                if info.get("jobs", 0) <= 0 or info.get("suspect"):
                    continue
                meta = {"name": res.get("name") or info["slug"],
                        "batch": res.get("batch"), "team": res.get("team"),
                        "ats": ats, "slug": info["slug"]}
                for k in (_key(info["slug"]), _key(res.get("name"))):
                    if k:
                        reg.setdefault(k, meta)
    _REGISTRY = reg
    log.info(f"startups: registry has {len(reg)} keys")
    return _REGISTRY


def annotate(job: dict) -> dict:
    """
    Add startup fields to a job dict in place:
      is_startup  bool
      yc_batch    str | None   (e.g. "W25")
      team_size   int | None
    """
    src = (job.get("source") or "").lower()
    meta = registry().get(_key(job.get("company", "")))

    team = meta.get("team") if meta else None
    small_enough = meta is not None and (team is None or team <= MAX_TEAM)
    job["is_startup"] = small_enough or src in STARTUP_SOURCES
    job["yc_batch"] = meta.get("batch") if meta else None
    job["team_size"] = meta.get("team") if meta else None
    return job


def reload_registry():
    """Drop the cache so a fresh discover_boards run is picked up."""
    global _REGISTRY
    _REGISTRY = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    reg = registry()
    print(f"{len(reg)} registry keys\n")
    for job in [
        {"company": "Nox Metals", "source": "hiringcafe"},
        {"company": "nox-metals", "source": "ashby"},
        {"company": "Deepgram", "source": "linkedin"},
        {"company": "JPMorgan Chase", "source": "oracle_hcm"},
        {"company": "Whoever", "source": "hackernews"},
    ]:
        a = annotate(dict(job))
        print(f"  {job['company'][:20]:<20} startup={str(a['is_startup']):<5} "
              f"batch={a['yc_batch']} team={a['team_size']}")
