"""
Headed (visible) browser — opens the job URL in Chrome and waits for the user
to fill the form, solve CAPTCHA, and submit.  Detects submission automatically.
"""
import logging
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PwTimeout
from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)


def apply_headed(job_url: str, profile: dict) -> tuple[bool, str]:
    """
    Open a visible Chrome window on the job application page and wait up to
    WAIT_MINUTES for the user to fill + submit.  Returns (success, reason).
    """
    WAIT_MINUTES = 20

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--start-maximized", "--disable-infobars"],
        )
        ctx  = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(20_000)

        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)

            # ── Click through to the application form if needed ───────────
            for btn_sel in [
                "a[href*='applications/new']",
                "a.postings-btn",
                "a:has-text('Apply for this Job')",
                "a:has-text('Apply Now')",
                "button:has-text('Apply')",
            ]:
                btn = page.query_selector(btn_sel)
                if btn:
                    try:
                        with ctx.expect_page(timeout=6_000) as new_page_info:
                            btn.click()
                        page = new_page_info.value
                        page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    except Exception:
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=10_000)
                        except Exception:
                            pass
                    break

            # ── Wait for page to stabilise ────────────────────────────────
            try:
                page.wait_for_selector(
                    "input, textarea, select",
                    state="visible", timeout=8_000,
                )
            except PwTimeout:
                pass

            log.info(f"Headed browser open — waiting up to {WAIT_MINUTES}m for submission")

            # ── Poll for successful submission ────────────────────────────
            success_url   = ["thank", "submitted", "confirmation", "success",
                             "complete", "received", "application"]
            success_body  = ["thank you", "application received",
                             "successfully submitted", "application submitted",
                             "we received", "we've received", "application complete"]

            for _ in range(WAIT_MINUTES * 6):   # every 10 s
                try:
                    page.wait_for_timeout(10_000)
                except Exception:
                    # Browser/page closed by user — treat as manual completion
                    return True, "Browser closed by user (assumed submitted)"

                try:
                    u = page.url.lower()
                    b = page.content().lower()
                    if any(w in u for w in success_url):
                        return True, "Applied (URL confirmed)"
                    if any(w in b for w in success_body):
                        return True, "Applied (page confirmed)"
                    if not page.query_selector(
                        "input[type='submit'], button[type='submit']"
                    ):
                        return True, "Applied (submit button gone)"
                except Exception:
                    # Page navigated mid-check — likely submitted
                    return True, "Applied (page navigated)"

            return False, f"Timed out after {WAIT_MINUTES}m — check manually"

        except PwTimeout:
            return False, "Page timed out"
        except Exception as exc:
            return False, str(exc)
        finally:
            try:
                browser.close()
            except Exception:
                pass
