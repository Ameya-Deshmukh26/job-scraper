"""
Fetch and print a job description to stdout.
Used by the /apply skill so Claude can read the JD without a separate API call.

Usage:
    python fetch_jd.py <url>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tailoring.jd_fetcher import fetch_jd

if len(sys.argv) < 2:
    print("Usage: python fetch_jd.py <url>", file=sys.stderr)
    sys.exit(1)

print(fetch_jd(sys.argv[1]))
