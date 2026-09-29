"""
Workday pagination tests — no network (_fetch_page is stubbed).

Workday was 790s of a ~1400s portal scan. The loop fetched all 3 pages for
each of 6 keywords across 30 boards (540 requests) even when page 1 was
already entirely older than the cutoff, which on a short lookback is the
normal case. These guard the early exit and, just as importantly, that it
does not cut a page which still holds wanted jobs.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sources.workday as wd  # noqa: E402

COMPANY = [("acme.wd1", "Acme_Careers", "Acme")]


def _posting(n: int, posted_on: str) -> dict:
    return {
        "title": f"Data Engineer {n}",
        "externalPath": f"/job/NY/Data-Engineer_R{n}",
        "locationsText": "New York, NY",
        "postedOn": posted_on,
        "bulletFields": [f"R{n}"],
    }


def _page(posted_on: str, count: int | None = None, offset: int = 0) -> dict:
    # IDs are offset-based so each page holds distinct postings, as real pages
    # do. Reusing ids across pages would make page 2 all dedup hits, which
    # skip the age check entirely and so can never look "all old".
    count = wd._PAGE_SIZE if count is None else count
    return {"total": 999,
            "jobPostings": [_posting(offset + i, posted_on) for i in range(count)]}


def _run(monkeypatch, page_factory, hours=2):
    """Run a fetch with stubbed pages; returns (jobs, offsets_requested)."""
    calls: list[int] = []

    def fake_fetch(url, keyword, offset):
        calls.append(offset)
        return page_factory(offset)

    monkeypatch.setattr(wd, "_fetch_page", fake_fetch)
    monkeypatch.setattr(wd.time, "sleep", lambda *_: None)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    jobs = wd.fetch_workday_jobs(COMPANY, cutoff)
    return jobs, calls


def test_stops_paging_when_a_whole_page_predates_the_cutoff(monkeypatch):
    """A full page of old jobs means later pages are older still."""
    jobs, calls = _run(monkeypatch, lambda offset: _page("Posted 30+ Days Ago"))

    assert jobs == []
    # One request per keyword and no more: it must not walk to offset 20 or 40.
    assert calls == [0] * len(wd._SEARCH_TERMS)


def test_keeps_paging_while_a_page_still_holds_fresh_jobs(monkeypatch):
    """The early exit must not truncate a keyword that is still producing."""
    def factory(offset):
        if offset == 0:
            return _page("Posted Today", offset=offset)
        return _page("Posted 30+ Days Ago", offset=offset)

    jobs, calls = _run(monkeypatch, factory)

    assert jobs, "fresh page-1 jobs were dropped"
    # Page 1 was fresh, so page 2 is fetched; page 2 is all old, so it stops.
    per_keyword = [c for c in calls if c == 0]
    assert len(per_keyword) == len(wd._SEARCH_TERMS)
    assert wd._PAGE_SIZE in calls, "did not page past a fresh first page"
    assert wd._PAGE_SIZE * 2 not in calls, "did not stop after an all-old page"


def test_undated_jobs_are_kept_and_do_not_trigger_the_exit(monkeypatch):
    """
    An unparseable postedOn is included rather than dropped, so a page of them
    is not 'entirely old' and must not stop pagination.
    """
    jobs, calls = _run(monkeypatch, lambda offset: _page("Posted sometime", offset=offset))

    assert len(jobs) > 0
    assert wd._PAGE_SIZE in calls, "a page of undated jobs wrongly stopped paging"


def test_short_page_still_ends_pagination(monkeypatch):
    """The pre-existing partial-page exit must survive the new one."""
    jobs, calls = _run(monkeypatch, lambda offset: _page("Posted Today", count=3))

    assert len(jobs) == 3          # deduped by external id across keywords
    assert calls == [0] * len(wd._SEARCH_TERMS)
