"""
Standalone resume tailor CLI.

Usage:
    python apply.py <job_url>
    python apply.py <job_url> --company "Stripe"

Fetches the JD, tailors Ameya's resume via Claude API, saves .tex to Downloads.
Prints JSON result so the skill can parse it.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# Make sure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from tailoring.jd_fetcher import fetch_jd
from tailoring.tailor import tailor_resume
from tailoring.compiler import save_and_compile


def _company_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    # greenhouse: boards.greenhouse.io/company/...
    if "greenhouse.io" in host:
        m = re.search(r"greenhouse\.io/([^/]+)", url)
        if m:
            return m.group(1).replace("-", " ").title()
    # lever: jobs.lever.co/company/...
    if "lever.co" in host:
        m = re.search(r"lever\.co/([^/]+)", url)
        if m:
            return m.group(1).replace("-", " ").title()
    # linkedin: linkedin.com/jobs/view/title-at-company-...
    if "linkedin.com" in host:
        m = re.search(r"-at-([a-z0-9-]+)-\d+", url.lower())
        if m:
            return m.group(1).replace("-", " ").title()
    # fallback: second-level domain
    parts = host.replace("www.", "").split(".")
    return parts[0].title() if parts else "Company"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Job posting URL")
    parser.add_argument("--company", default="", help="Company name override")
    args = parser.parse_args()

    company = args.company or _company_from_url(args.url)

    # 1. Fetch JD
    jd = fetch_jd(args.url)
    if jd.startswith("[Could not fetch"):
        print(json.dumps({"error": jd, "company": company}))
        sys.exit(1)

    # 2. Tailor via Claude API
    try:
        latex, score = tailor_resume(jd, company)
    except Exception as exc:
        print(json.dumps({"error": str(exc), "company": company}))
        sys.exit(1)

    # 3. Save / compile
    result = save_and_compile(latex, company)
    result["score"] = score
    result["company"] = company
    result["jd_snippet"] = jd[:300]

    print(json.dumps(result))


if __name__ == "__main__":
    main()
