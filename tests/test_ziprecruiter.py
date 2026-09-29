"""
ZipRecruiter via Firecrawl raw HTML. No network: the scrape is stubbed.

The page embeds a schema.org ItemList with each job's own URL. Firecrawl's
JSON extraction cost 6x as much and returned company pages instead of jobs,
so these guard the parsing that replaces it, and the credit ceiling.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sources.ziprecruiter as zr  # noqa: E402


def _page(*items) -> str:
    listing = {"@context": "https://schema.org", "@type": "ItemList", "numberOfItems": len(items),
               "itemListElement": [{"@type": "ListItem", "position": str(i + 1), "name": n, "url": u}
                                   for i, (n, u) in enumerate(items)]}
    return ('<html><section><script type="application/ld+json">' + json.dumps(listing, separators=(",", ":"))
            + "</script></section></html>")


GOPUFF = ("Data Scientist - Consumer",
          "https://www.ziprecruiter.com/c/Gopuff/Job/Data-Scientist-Consumer/-in-Charleston,WV?jid=daa8cdc10f964f8f")
UMB = ("AI Cloud Data Scientist",
       "https://www.ziprecruiter.com/c/UMB-Bank/Job/AI-Cloud-Data-Scientist/-in-Remote,US?jid=0a1b2c3d4e5f6071")


def test_jobs_come_from_the_embedded_item_list():
    jobs = zr._parse(_page(GOPUFF, UMB))
    assert [j["id"] for j in jobs] == ["ziprecruiter_daa8cdc10f964f8f", "ziprecruiter_0a1b2c3d4e5f6071"]
    assert jobs[0]["company"] == "Gopuff"
    assert jobs[1]["company"] == "UMB Bank"
    assert jobs[0]["location"] == "Charleston, WV"
    assert jobs[0]["url"] == GOPUFF[1]           # the job itself, not /co/<Company>/Jobs


def test_company_pages_are_not_mistaken_for_jobs():
    jobs = zr._parse(_page(("Gopuff jobs", "https://www.ziprecruiter.com/co/Gopuff/Jobs?uuid=X")))
    assert jobs == []


def test_a_page_without_the_list_yields_nothing():
    assert zr._parse("<html>Cloudflare says no</html>") == []
    assert zr._parse("") == []


@pytest.mark.parametrize("hours, days", [(2, 1), (24, 1), (48, 5), (200, 10), (500, 30)])
def test_lookback_maps_to_ziprecruiters_posted_within_filter(hours, days):
    assert zr._days(datetime.now(timezone.utc) - timedelta(hours=hours)) == days


def test_remote_is_not_searched_twice(monkeypatch):
    """Nationwide results already include remote jobs."""
    monkeypatch.setattr(zr, "SEARCH_CITIES", ["United States", "Remote"])
    assert zr._locations() == ["United States"]


def test_run_stays_under_the_credit_ceiling(monkeypatch):
    urls = []
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test")
    monkeypatch.setattr(zr, "IN_US", True)
    monkeypatch.setattr(zr, "_QUERIES", [f"title {i}" for i in range(20)])
    monkeypatch.setattr(zr, "_scrape", lambda key, url: urls.append(url) or _page(GOPUFF))
    jobs = zr.fetch_ziprecruiter_jobs(datetime.now(timezone.utc) - timedelta(hours=2))
    assert len(urls) == zr._MAX_PAGES
    assert all("days=1" in u for u in urls)
    assert len(jobs) == 1                        # same job on every page, kept once


def test_no_key_means_no_scrapes(monkeypatch):
    calls = []
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr(zr, "IN_US", True)
    monkeypatch.setattr(zr, "_scrape", lambda *a: calls.append(a) or "")
    assert zr.fetch_ziprecruiter_jobs(datetime.now(timezone.utc)) == []
    assert calls == []


def test_outside_the_us_it_does_nothing(monkeypatch):
    calls = []
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test")
    monkeypatch.setattr(zr, "IN_US", False)
    monkeypatch.setattr(zr, "_scrape", lambda *a: calls.append(a) or "")
    assert zr.fetch_ziprecruiter_jobs(datetime.now(timezone.utc)) == []
    assert calls == []
