"""
Auto-apply to Greenhouse jobs via Playwright.
Greenhouse public application forms need no login — just fill and submit.

Returns (success: bool, reason: str)
"""
import logging
import os

from playwright.sync_api import TimeoutError as PwTimeout
from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)


def _react_set_value(el, value: str):
    """Set value on a React-controlled input/textarea via the native setter trick.
    Called on an ElementHandle — el.evaluate() passes 'el' as the first JS arg."""
    el.evaluate(
        """(node, val) => {
            var proto = (node.tagName === 'TEXTAREA')
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            setter.call(node, val);
            node.dispatchEvent(new Event('input',  { bubbles: true }));
            node.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        value,
    )


def _try_fill(page, selectors: list, value: str) -> bool:
    """Fill the first element matching any selector using the React native setter."""
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if not el:
                continue
            try:
                el.scroll_into_view_if_needed(timeout=2_000)
            except Exception:
                pass
            _react_set_value(el, value)
            return True
        except Exception:
            continue
    return False


def _fill_by_label(page, keywords: list, value: str) -> bool:
    """Find an input/textarea whose label contains any keyword, then fill it."""
    labels = page.query_selector_all("label")
    for lbl in labels:
        try:
            text = lbl.inner_text().lower()
            if not any(kw in text for kw in keywords):
                continue
            for_id = lbl.get_attribute("for")
            if for_id:
                el = _safe_query(page, for_id)
                if el:
                    tag = el.evaluate("e => e.tagName.toLowerCase()")
                    if tag in ("input", "textarea"):
                        try:
                            el.scroll_into_view_if_needed(timeout=2_000)
                        except Exception:
                            pass
                        _react_set_value(el, value)
                        return True
        except Exception:
            continue
    return False


def _handle_select(page, keywords: list, value: str) -> bool:
    """Set a <select> whose label/id contains any keyword."""
    selects = page.query_selector_all("select")
    for sel in selects:
        try:
            sel_id = (sel.get_attribute("id") or "").lower()
            label_text = ""
            if sel_id:
                lbl = page.query_selector(f"label[for='{sel_id}']")
                if lbl:
                    label_text = lbl.inner_text().lower()
            if not any(kw in sel_id or kw in label_text for kw in keywords):
                continue
            options = sel.query_selector_all("option")
            for opt in options:
                text = opt.inner_text().strip().lower()
                if value.lower() in text or text.startswith(value.lower()):
                    sel.select_option(value=opt.get_attribute("value"))
                    return True
        except Exception:
            continue
    return False


def _handle_select_by_partial(page, name_or_id: str, partial_option: str) -> bool:
    """Select an option in a named <select> by partial option text."""
    # Use attribute selector for IDs that start with a digit (invalid CSS ID syntax)
    sel = page.query_selector(f"select[name='{name_or_id}'], select[id='{name_or_id}']")
    if not sel:
        return False
    try:
        options = sel.query_selector_all("option")
        for opt in options:
            if partial_option.lower() in opt.inner_text().strip().lower():
                sel.select_option(value=opt.get_attribute("value"))
                return True
    except Exception:
        pass
    return False


def _safe_query(page, element_id: str):
    """Query by id using attribute selector — safe for IDs with [], spaces, or leading digits."""
    try:
        return page.query_selector(f"[id='{element_id}']")
    except Exception:
        return None


def _check_checkbox(page, label_keyword: str) -> bool:
    """Check a checkbox whose label contains the keyword (if not already checked)."""
    labels = page.query_selector_all("label")
    for lbl in labels:
        try:
            if label_keyword.lower() not in lbl.inner_text().lower():
                continue
            for_id = lbl.get_attribute("for")
            cb = _safe_query(page, for_id) if for_id else lbl.query_selector("input[type='checkbox']")
            if cb and not cb.is_checked():
                cb.check()
            return True
        except Exception:
            continue
    return False


def _check_all_acknowledge(page):
    """Check every checkbox whose label contains 'acknowledge', 'consent', 'agree', or 'certify'."""
    labels = page.query_selector_all("label")
    for lbl in labels:
        try:
            text = lbl.inner_text().lower()
            if not any(k in text for k in ("acknowledge", "consent", "agree", "certify")):
                continue
            for_id = lbl.get_attribute("for")
            cb = _safe_query(page, for_id) if for_id else lbl.query_selector("input[type='checkbox']")
            if cb and not cb.is_checked():
                cb.check()
        except Exception:
            continue


def _has_captcha(page) -> bool:
    """Return True if the page has a reCAPTCHA or hCaptcha frame."""
    for frame in page.frames:
        if "recaptcha" in frame.url or "hcaptcha" in frame.url:
            return True
    el = page.query_selector(
        ".g-recaptcha, .h-captcha, "
        "iframe[src*='recaptcha'], iframe[src*='hcaptcha']"
    )
    return el is not None


def _fill_country(page, country_text: str = "United States"):
    """Fill the country field — handles both plain text inputs and GH's custom pickers."""
    # Plain text input named 'country'
    el = page.query_selector("input[name='country']")
    if el and el.is_visible():
        tag = el.get_attribute("type") or "text"
        if tag not in ("hidden",):
            el.triple_click()
            el.fill(country_text)
            # If there's a dropdown suggestion, pick first matching option
            page.wait_for_timeout(600)
            try:
                option = page.query_selector(f"li:has-text('{country_text}')")
                if option:
                    option.click()
            except Exception:
                pass
            return True
    return False


def apply_greenhouse(job_url: str, profile: dict) -> tuple[bool, str]:
    resume = profile.get("resume_path", "")
    if not os.path.exists(resume):
        return False, f"Resume not found at {resume}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(20_000)

        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)

            # Click through to the application form if needed
            for btn_sel in [
                "a[href*='applications/new']",
                "a:has-text('Apply for this Job')",
                "a:has-text('Apply Now')",
                "button:has-text('Apply')",
            ]:
                btn = page.query_selector(btn_sel)
                if btn:
                    btn.click()
                    page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    break

            # Wait for the form's first field to be interactive
            try:
                page.wait_for_selector(
                    "input[name='first_name'], #first_name, input[type='email']",
                    state="visible", timeout=10_000
                )
            except PwTimeout:
                pass  # form might be on a different URL already
            page.wait_for_timeout(800)  # let lazy scripts (reCAPTCHA, React) finish

            # ── Bail early if CAPTCHA detected after form renders ─────────
            if _has_captcha(page):
                return False, "CAPTCHA detected — needs manual application"

            # ── Standard identity fields ──────────────────────────────────
            _try_fill(page, ["#first_name", "input[name='first_name']"], profile["first_name"])
            _try_fill(page, ["#last_name",  "input[name='last_name']"],  profile["last_name"])

            # Preferred / middle name
            _try_fill(page, ["#preferred_name", "input[name='preferred_name']"],
                      profile.get("preferred_name", profile["first_name"]))

            _try_fill(page, ["#email", "input[name='email']", "input[type='email']"], profile["email"])
            _try_fill(page, ["#phone", "input[name='phone']", "input[type='tel']"],   profile["phone"])

            # Country
            _fill_country(page, "United States")

            # City / location
            _try_fill(page,
                      ["#candidate-location", "input[name='candidate-location']",
                       "input[id*='location']", "input[placeholder*='city' i]",
                       "input[placeholder*='location' i]"],
                      profile.get("location", "Boston, MA"))

            # ── Resume upload ─────────────────────────────────────────────
            uploaded = False
            for sel in ["input#resume", "input[type='file'][name='resume']", "input[type='file']"]:
                el = page.query_selector(sel)
                if el:
                    el.set_input_files(resume)
                    uploaded = True
                    break
            if not uploaded:
                return False, "Could not find resume upload field"

            page.wait_for_timeout(1500)

            # ── Optional profile links ────────────────────────────────────
            for kws in [("linkedin",), ("github",), ("website", "portfolio")]:
                key = kws[0]
                val = profile.get(key, "")
                if val:
                    selectors = [f"input[id*='{k}']" for k in kws] + \
                                [f"input[name*='{k}']" for k in kws] + \
                                [f"input[placeholder*='{k}' i]" for k in kws]
                    _try_fill(page, selectors, val)
                    if not _try_fill(page, selectors, val):
                        _fill_by_label(page, list(kws), val)

            # ── Work authorization (select or text) ───────────────────────
            auth_val = profile.get("work_authorized_us", "Yes")
            _handle_select(page, ["authorized", "legally", "eligible", "authorization"], auth_val)
            _fill_by_label(page, ["legally authorized", "authorized to work"], auth_val)

            # Source of right to work (visa type)
            visa_val = profile.get("visa_type", "F-1 OPT")
            _fill_by_label(page, ["source of", "right to work", "visa type", "work visa"], visa_val)

            # Sponsorship
            sponsor_val = profile.get("requires_sponsorship", "Yes")
            _handle_select(page, ["sponsor", "visa", "h1b", "h-1b"], sponsor_val)
            _fill_by_label(page, ["require.*sponsor", "sponsor.*visa", "sponsorship"], sponsor_val)

            # ── "How did you hear" — check LinkedIn ───────────────────────
            _check_checkbox(page, "linkedin")

            # ── Gender self-identification — "Prefer not to say" ─────────
            _handle_select(page, ["gender", "self-identif"], "Prefer not to say")
            _handle_select_by_partial(page, "353", "Prefer not to say")

            # ── Acknowledge / consent / GDPR checkboxes ───────────────────
            _check_all_acknowledge(page)

            # ── Cover letter (textarea, if present and non-empty) ─────────
            cl = profile.get("cover_letter", "")
            if cl:
                for sel in ["textarea[name*='cover']", "textarea[id*='cover']",
                            "#cover_letter", "textarea"]:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.fill(cl)
                        break

            # ── Submit ────────────────────────────────────────────────────
            submit = page.query_selector(
                "input[type='submit'], button[type='submit'], "
                "button:has-text('Submit Application'), button:has-text('Submit application')"
            )
            if not submit:
                return False, "No submit button found — form may have required custom fields"

            submit.click()
            page.wait_for_timeout(5000)

            # ── Verify success ─────────────────────────────────────────────
            url_lower  = page.url.lower()
            body_lower = page.content().lower()
            success_url_words  = ["thank", "submitted", "confirmation", "success", "complete", "received"]
            success_body_words = ["thank you", "application received", "successfully submitted",
                                  "application submitted", "we received", "we've received",
                                  "application complete", "your application has been"]

            if any(w in url_lower for w in success_url_words):
                return True, "Applied (URL confirmed)"
            if any(w in body_lower for w in success_body_words):
                return True, "Applied (page confirmed)"

            # Check if we're still on the form (validation error)
            if "applications" in url_lower or page.query_selector("input[type='submit']"):
                # Look for visible error messages
                err = page.query_selector(".error, .alert-danger, [class*='error'], [class*='invalid']")
                if err:
                    return False, f"Validation error: {err.inner_text()[:120]}"
                return False, "Submitted but could not confirm — check email for confirmation"

            return True, "Applied (no error detected)"

        except PwTimeout:
            return False, "Page timed out"
        except Exception as e:
            return False, str(e)
        finally:
            browser.close()
