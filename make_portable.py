"""
Build a clean, shareable copy of the app: dist/JobScout/ and JobScout.zip.

    python make_portable.py            # zip lands next to this repo (Downloads)
    python make_portable.py --out D:\\  # somewhere else

What goes in: only files git tracks, so the local database, logs, .env,
.mcp.json, profile.json and caches are never candidates. Then the personal
parts are swapped for the blank versions in portable/:

    portable/search_profile.py    -> search_profile.py  (starter MBA search, India)
    portable/env.template         -> .env               (empty key slots)
    portable/CLAUDE.template.md   -> CLAUDE.md          (setup guide for Claude)
    portable/START_HERE.md        -> START_HERE.md
    portable/claude/...           -> .claude/...
    portable/start.bat            -> start.bat

The guide is stored as CLAUDE.template.md here because Claude Code loads any
CLAUDE.md it finds in a subfolder it works in, and this one tells Claude to
start first-time setup.

The build refuses to produce a zip if any file contains one of this machine's
real key values, a credential-shaped string, or personal details. It reports
which file and which key name matched, never the value.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORTABLE = ROOT / "portable"
BUILD = ROOT / "dist" / "JobScout"
NAME = "JobScout"

# Not useful to someone running the app, or tied to this machine
EXCLUDE_PREFIXES = (
    "tests/",               # reads this machine's resume file
    ".github/",
    "portable/",
    "make_portable.py",
    "README.md",            # developer notes; START_HERE.md replaces it
    "agent/README.md",      # worked examples drawn from a real resume
    "run.bat",              # replaced by start.bat
    "search_profile.py",    # replaced by the blank one
)

OVERLAY = {
    "search_profile.py":         "search_profile.py",
    "env.template":              ".env",
    "CLAUDE.template.md":        "CLAUDE.md",
    "START_HERE.md":             "START_HERE.md",
    "start.bat":                 "start.bat",
    "claude/commands/setup.md":  ".claude/commands/setup.md",
    "claude/launch.json":        ".claude/launch.json",
}

# Files that must never ship, whatever git says
FORBIDDEN_NAMES = {".mcp.json", "profile.json", "seen_jobs.db"}
FORBIDDEN_SUFFIXES = {".db", ".log", ".pkl", ".sqlite"}

KEY_NAMES = ("SERPAPI_API_KEY", "FIRECRAWL_API_KEY", "OPIK_API_KEY",
             "ANTHROPIC_API_KEY", "APIFY_TOKEN", "APIFY_API_TOKEN")

# Credential shapes, for keys this machine does not have set
SECRET_PATTERNS = {
    "Firecrawl key":  re.compile(r"\bfc-[0-9a-f]{32}\b"),
    "Anthropic key":  re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "Apify token":    re.compile(r"\bapify_api_[A-Za-z0-9]{20,}"),
    "GitHub token":   re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS key":        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "OpenAI key":     re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}"),
    "Discord hook":   re.compile(r"discord(?:app)?\.com/api/webhooks/\d+/"),
}

# Personal details. LICENSE keeps its copyright line; nothing else may match.
PERSONAL = re.compile(
    r"ameya|deshmukh|northeastern|boehringer|humanitarians|"
    r"C:[/\\]+Users[/\\]+",
    re.IGNORECASE,
)
PERSONAL_ALLOWED = {"LICENSE": re.compile(r"^Copyright \(c\) \d{4} .+$")}


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [f for f in out.splitlines() if f]


def real_key_values() -> dict[str, str]:
    """Key values on this machine: environment, Windows user env, and .env."""
    values: dict[str, str] = {}
    for name in KEY_NAMES:
        if os.environ.get(name):
            values[name] = os.environ[name]
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                for name in KEY_NAMES:
                    try:
                        v = str(winreg.QueryValueEx(k, name)[0])
                        if v:
                            values.setdefault(name, v)
                    except OSError:
                        pass
        except OSError:
            pass
    try:
        from dotenv import dotenv_values
        for name, v in dotenv_values(ROOT / ".env").items():
            if v and v.strip():
                values.setdefault(name, v.strip())
    except ImportError:
        pass
    # Too-short values would match by accident and prove nothing
    return {k: v for k, v in values.items() if len(v) >= 12}


def build() -> list[str]:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    copied = []
    for rel in tracked_files():
        if rel.startswith(EXCLUDE_PREFIXES) or rel in EXCLUDE_PREFIXES:
            continue
        src = ROOT / rel
        if not src.is_file():           # tracked but deleted locally
            continue
        dst = BUILD / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)

    for src_rel, dst_rel in OVERLAY.items():
        dst = BUILD / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PORTABLE / src_rel, dst)
        copied.append(dst_rel)
    return sorted(set(copied))


def verify(files: list[str]) -> list[str]:
    problems = []
    secrets = real_key_values()

    for rel in files:
        path = BUILD / rel
        name = path.name
        if name in FORBIDDEN_NAMES or path.suffix in FORBIDDEN_SUFFIXES:
            problems.append(f"{rel}: this kind of file must not ship")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue                    # binary: nothing readable to leak

        for key, value in secrets.items():
            if value in text:
                problems.append(f"{rel}: contains this machine's {key}")
        for label, pat in SECRET_PATTERNS.items():
            if pat.search(text):
                problems.append(f"{rel}: contains something shaped like a {label}")

        allowed = PERSONAL_ALLOWED.get(rel)
        for n, line in enumerate(text.splitlines(), 1):
            if PERSONAL.search(line) and not (allowed and allowed.match(line)):
                problems.append(f"{rel}:{n}: personal detail: {line.strip()[:70]}")

    # The shipped .env must be empty slots only
    try:
        from dotenv import dotenv_values
        filled = [k for k, v in dotenv_values(BUILD / ".env").items() if v]
        if filled:
            problems.append(f".env: has values for {filled}")
    except ImportError:
        pass

    # The shipped profile must search something out of the box, offer the
    # guided setup, and never submit applications on its own
    profile: dict = {}
    exec((BUILD / "search_profile.py").read_text(encoding="utf-8"), profile)
    if profile.get("SETUP_DONE") is not False:
        problems.append("search_profile.py: SETUP_DONE is not False")
    for name in ("SEARCH_TITLES", "KEYWORDS", "LOCATION_FILTER"):
        if not profile.get(name):
            problems.append(f"search_profile.py: {name} is empty, so nothing would be found")
    if profile.get("ENABLE_AUTO_APPLY"):
        problems.append("search_profile.py: auto-apply is on")
    if "manager" in [x.strip() for x in profile.get("EXCLUDE_LEVELS", [])]:
        problems.append("search_profile.py: a bare 'manager' exclusion drops MBA roles")
    return problems


def make_zip(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / f"{NAME}.zip"
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(BUILD.rglob("*")):
            if f.is_file():
                z.write(f, Path(NAME) / f.relative_to(BUILD))
    return zpath


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT.parent,
                    help="folder for JobScout.zip (default: next to this repo)")
    args = ap.parse_args()

    files = build()
    problems = verify(files)
    if problems:
        print(f"NOT zipped: {len(problems)} problem(s) in dist/{NAME}:")
        for p in problems:
            print("  -", p)
        return 1

    zpath = make_zip(args.out)
    size_kb = zpath.stat().st_size // 1024
    print(f"{len(files)} files checked: no keys, no personal details, starter MBA profile.")
    print(f"Folder: {BUILD}")
    print(f"Zip:    {zpath}  ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
