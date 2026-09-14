"""
Startup ATS discovery — stop guessing slugs, probe them.

The problem: hand-picked Greenhouse/Lever slugs rot badly. An audit of this
repo's config found 85 of 162 Greenhouse and 32 of 36 Lever slugs were dead
404s, because the slugs had been guessed from company names.

The fix: take a real startup universe (Y Combinator's public company API,
~6,200 companies), generate slug candidates, and probe Greenhouse / Lever /
Ashby to see which actually answer. Results are cached, so each run only
probes companies it has never seen before.

Usage
-----
  python discover_boards.py --fetch-yc       # refresh the YC company cache
  python discover_boards.py --probe 200      # probe 200 unchecked companies
  python discover_boards.py --report         # everything found so far
  python discover_boards.py --write-config   # append new live boards to config.py
"""
import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)
YC_CACHE = DATA / "yc_companies.json"
PROBE_CACHE = DATA / "board_probe.json"

_S = requests.Session()
_S.headers.update({"User-Agent": "Mozilla/5.0 (compatible; JobScraper/1.0)"})
_S.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=32))

MIN_TEAM = 10          # below this a company rarely has a hosted ATS board


def _safe(text):
    """Console-safe string. YC company names contain emoji and the Windows
    cp1252 console raises UnicodeEncodeError on them, which previously killed
    a 1500-company run before its results were saved."""
    return str(text or "").encode("ascii", "replace").decode("ascii")


def is_collision(jobs, team):
    """
    Generic one-word slugs collide with unrelated companies: probing YC's
    22-person "Pulse" returned a Greenhouse board with 2,661 open roles, and
    11-person "Distro" returned 220 on Lever. A startup cannot have far more
    openings than employees, so treat wild disproportion as a wrong match.
    """
    team = team or 0
    return jobs > max(30, team * 3)


# -- YC company universe ---------------------------------------------------

def fetch_yc():
    out, url, page = [], "https://api.ycombinator.com/v0.1/companies", 0
    while url:
        r = _S.get(url, timeout=30)
        r.raise_for_status()
        d = r.json()
        out.extend(d.get("companies", []))
        url = d.get("nextPage")
        page += 1
        if page % 25 == 0:
            print(f"  page {page}/{d.get('totalPages')} - {len(out)} companies")
        time.sleep(0.05)
    YC_CACHE.write_text(json.dumps(out), encoding="utf-8")
    print(f"cached {len(out)} YC companies -> {YC_CACHE.name}")
    return out


def load_yc():
    if not YC_CACHE.exists():
        sys.exit("No YC cache. Run: python discover_boards.py --fetch-yc")
    return json.loads(YC_CACHE.read_text(encoding="utf-8"))


# -- slug candidates -------------------------------------------------------

def candidates(co):
    """Plausible ATS slugs for a company, most likely first."""
    name = (co.get("name") or "").strip()
    slug = (co.get("slug") or "").strip().lower()
    flat = re.sub(r"[^a-z0-9]", "", name.lower())
    out = []
    for c in (slug, flat, slug.replace("-", "")):
        if c and c not in out and 2 < len(c) <= 40:
            out.append(c)
    return out[:3]


# -- ATS probes ------------------------------------------------------------

def probe_greenhouse(slug):
    try:
        r = _S.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=12)
        if r.status_code == 200:
            return len(r.json().get("jobs", []))
    except Exception:
        pass
    return None


def probe_lever(slug):
    try:
        r = _S.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"}, timeout=12)
        if r.status_code == 200:
            d = r.json()
            if isinstance(d, list):
                return len(d)
    except Exception:
        pass
    return None


ASHBY_Q = ("query($org: String!) { jobBoardWithTeams("
           "organizationHostedJobsPageName: $org) { jobPostings { id } } }")


def probe_ashby(slug):
    try:
        r = _S.post("https://jobs.ashbyhq.com/api/non-user-graphql",
                    json={"query": ASHBY_Q, "variables": {"org": slug}},
                    headers={"Referer": f"https://jobs.ashbyhq.com/{slug}"},
                    timeout=12)
        board = (r.json().get("data") or {}).get("jobBoardWithTeams")
        if board is not None:
            return len(board.get("jobPostings") or [])
    except Exception:
        pass
    return None


PROBES = {"greenhouse": probe_greenhouse, "lever": probe_lever, "ashby": probe_ashby}


def probe_company(co):
    """Try each ATS; the first candidate slug that answers wins for that ATS."""
    found = {}
    for ats, fn in PROBES.items():
        for cand in candidates(co):
            n = fn(cand)
            if n is not None:
                found[ats] = {"slug": cand, "jobs": n,
                              "suspect": is_collision(n, co.get("teamSize"))}
                break
    return {"name": co.get("name"), "yc_slug": co.get("slug"),
            "batch": co.get("batch"), "team": co.get("teamSize"), "found": found}


# -- driver ----------------------------------------------------------------

def load_probes():
    if PROBE_CACHE.exists():
        return json.loads(PROBE_CACHE.read_text(encoding="utf-8"))
    return {}


def run_probe(limit):
    companies = load_yc()
    done = load_probes()
    todo = [c for c in companies
            if c.get("slug") and c["slug"] not in done
            and (c.get("teamSize") or 0) >= MIN_TEAM
            and str(c.get("status") or "").lower() in ("active", "")]
    todo = todo[:limit]
    if not todo:
        print("nothing new to probe (raise --probe, or run --fetch-yc)")
        return

    print(f"probing {len(todo)} companies ({len(done)} already cached)...")
    hits = 0
    try:
        with ThreadPoolExecutor(max_workers=12) as ex:
            for co, res in zip(todo, ex.map(probe_company, todo)):
                done[co["slug"]] = res
                if res["found"]:
                    hits += 1
                    for ats, info in res["found"].items():
                        flag = "  ?collision" if info.get("suspect") else ""
                        print(f"  FOUND {ats:<11} {info['slug']:<26} "
                              f"{info['jobs']:>4} jobs   ({_safe(res['name'])[:24]}, "
                              f"{res['batch']}, team {res['team']}){flag}")
    finally:
        # Always checkpoint: a crash must not discard the whole run
        PROBE_CACHE.write_text(json.dumps(done, indent=1), encoding="utf-8")
    print("")
    print(f"{hits}/{len(todo)} companies have a live board. "
          f"cache now {len(done)} companies")


def report():
    done = load_probes()
    live = {"greenhouse": [], "lever": [], "ashby": []}
    suspects = []
    for res in done.values():
        for ats, info in (res.get("found") or {}).items():
            if info.get("jobs", 0) <= 0:
                continue
            if info.get("suspect") or is_collision(info["jobs"], res.get("team")):
                suspects.append((ats, info["slug"], info["jobs"],
                                 res.get("name"), res.get("team")))
                continue
            live[ats].append((info["slug"], info["jobs"], res.get("name")))
    print(f"probed {len(done)} companies\n")
    for ats, rows in live.items():
        rows.sort(key=lambda r: -r[1])
        print(f"{ats}: {len(rows)} live boards with open roles")
        for slug, n, name in rows[:20]:
            print(f"    {slug:<28} {n:>4} jobs   {_safe(name)}")
        print()
    if suspects:
        print(f"excluded {len(suspects)} likely slug collisions "
              f"(job count out of proportion to team size):")
        for ats, slug, n, name, team in suspects[:12]:
            print(f"    {ats:<11} {slug:<24} {n:>5} jobs vs team {team}   ({_safe(name)})")
        print()
    return live


def write_config():
    live = report()
    cfg = Path(__file__).parent / "config.py"
    text = cfg.read_text(encoding="utf-8")
    added = {}
    for ats, key in (("greenhouse", "GREENHOUSE_COMPANIES"),
                     ("lever", "LEVER_COMPANIES"),
                     ("ashby", "ASHBY_COMPANIES")):
        new = sorted({s for s, n, _ in live[ats] if f'"{s}"' not in text})
        if not new:
            continue
        marker = key + " = ["
        i = text.index(marker) + len(marker)
        block = ("\n    # --- auto-discovered from YC via discover_boards.py ---\n    "
                 + ", ".join('"' + s + '"' for s in new) + ",")
        text = text[:i] + block + text[i:]
        added[key] = new
    if not added:
        print("no new slugs to add")
        return
    cfg.write_text(text, encoding="utf-8")
    for k, v in added.items():
        tail = "..." if len(v) > 12 else ""
        print(f"added {len(v)} to {k}: {', '.join(v[:12])}{tail}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch-yc", action="store_true")
    ap.add_argument("--probe", type=int, metavar="N")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--write-config", action="store_true")
    a = ap.parse_args()
    if a.fetch_yc:
        fetch_yc()
    if a.probe:
        run_probe(a.probe)
    if a.report:
        report()
    if a.write_config:
        write_config()
    if not any([a.fetch_yc, a.probe, a.report, a.write_config]):
        ap.print_help()
