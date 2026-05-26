"""
Auto-apply to Lever jobs via Playwright.
Lever public forms need no login — fill and submit.
"""
import logging
import os

from playwright.sync_api import TimeoutError as PwTimeout
from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)


def _fill(page, selector: str, value: str) -> bool:
    try:
        el = page.query_selector(selector)
        if el and el.is_visible():
            el.triple_click()
            el.fill(value)
            return True
    except Exception:
        pass
    return False


def apply_lever(job_url: str, profile: dict) -> tuple[bool, str]:
    resume = profile.get("resume_path", "")
    if not os.path.exists(resume):
        return False, f"Resume not found at {resume}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(20_000)

        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)

            # Lever posts show job first; click Apply to get the form
            apply_btn = page.query_selector(
                "a.postings-btn, a:has-text('Apply for this job'), "
                "a:has-text('Apply Now'), button:has-text('Apply')"
            )
            if apply_btn:
                apply_btn.click()
                page.wait_for_load_state("domcontentloaded", timeout=15_000)

            # ── Standard Lever fields ─────────────────────────────────────
            full_name = f"{profile['first_name']} {profile['last_name']}"
            _fill(page, "input[name='name']",  full_name)
            _fill(page, "input[name='email']", profile["email"])
            _fill(page, "input[name='phone']", profile["phone"])
            _fill(page, "input[name='org']",   profile.get("current_company", ""))

            # ── Resume upload ─────────────────────────────────────────────
            resume_el = page.query_selector("input[type='file']")
            if not resume_el:
                return False, "No file upload field found"
            resume_el.set_input_files(resume)
            page.wait_for_timeout(1500)

            # ── Profile links (Lever uses urls[LinkedIn] naming) ──────────
            _fill(page, "input[name='urls[LinkedIn]']",  profile.get("linkedin", ""))
            _fill(page, "input[name='urls[GitHub]']",    profile.get("github",   ""))
            _fill(page, "input[name='urls[Portfolio]']", profile.get("website",  ""))

            # ── Cover letter ──────────────────────────────────────────────
            cl = profile.get("cover_letter", "")
            if cl:
                _fill(page, "textarea[name='comments']", cl)
                _fill(page, "textarea[name='body']", cl)

            # ── Submit ────────────────────────────────────────────────────
            submit = page.query_selector(
                "button[type='submit'], input[type='submit'], "
                "button:has-text('Submit Application'), button:has-text('Submit')"
            )
            if not submit:
                return False, "No submit button — form may have required custom questions"

            submit.click()
            page.wait_for_timeout(4000)

            # ── Verify success ────────────────────────────────────────────
            url_ok  = any(w in page.url.lower()     for w in ["thank", "submitted", "confirmation"])
            body_ok = any(w in page.content().lower() for w in
                          ["thank you", "application received", "successfully submitted"])
            if url_ok or body_ok:
                return True, "Applied"

            return False, "Submitted but could not confirm — check manually"

        except PwTimeout:
            return False, "Page timed out"
        except Exception as e:
            return False, str(e)
        finally:
            browser.close()
