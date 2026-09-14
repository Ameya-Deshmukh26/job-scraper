"""
HiringCafe URL tests.

Measured Aug 2026: HiringCafe moved from hiring.cafe to hiringcafe.com and
changed the job route. Every stored /job/<id> link was returning 404.

  /job/<id>   -> 404
  /jobs/<id>  -> 200 but only the SPA shell, no posting content
  ?job=<id>   -> 200 and renders the posting  <-- the correct one
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sources.hiringcafe as hc  # noqa: E402


def test_job_base_uses_query_param_route():
    assert hc._JOB_BASE == "https://hiringcafe.com/?job="


def test_job_base_is_not_the_dead_path_route():
    """/job/<id> and /jobs/<id> must not come back."""
    assert not hc._JOB_BASE.rstrip("/").endswith("/job")
    assert not hc._JOB_BASE.rstrip("/").endswith("/jobs")


def test_job_base_uses_current_domain():
    assert "hiringcafe.com" in hc._JOB_BASE
    assert "hiring.cafe" not in hc._JOB_BASE


def test_constructed_url_shape():
    url = f"{hc._JOB_BASE}is2p9k4b0emsg4e6"
    assert url == "https://hiringcafe.com/?job=is2p9k4b0emsg4e6"


def test_id_regex_matches_new_query_form():
    m = hc._JOB_ID_RE.search("https://hiringcafe.com/?job=is2p9k4b0emsg4e6")
    assert m and m.group(1) == "is2p9k4b0emsg4e6"


def test_id_regex_still_matches_legacy_path_forms():
    """Cards in the DOM may still use path links; keep parsing them."""
    for href in ("/job/tf3x5twwb4yv2sar", "/jobs/tf3x5twwb4yv2sar"):
        m = hc._JOB_ID_RE.search(href)
        assert m and m.group(1) == "tf3x5twwb4yv2sar", href


def test_id_regex_ignores_short_noise():
    assert hc._JOB_ID_RE.search("/job/abc") is None


def test_base_url_is_current_domain():
    assert "hiringcafe.com" in hc._BASE_URL
