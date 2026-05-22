"""
Agent-OS Form Filler
Automates job applications and complex multi-step forms.
"""
import asyncio
import logging
import random
from typing import Dict, List, Optional

logger = logging.getLogger("agent-os.form-filler")


class FormFiller:
    """Automated form filling with human-like behavior."""

    # Common field name patterns and their semantic meaning
    FIELD_PATTERNS = {
        "email": ["email", "e-mail", "mail", "user_email"],
        "username": ["username", "user_name", "user", "userid", "user_id", "login", "login_id"],
        "password": ["password", "passwd", "pass", "pwd", "user_password", "user_pass"],
        "first_name": ["first_name", "firstname", "fname", "first-name", "given_name"],
        "last_name": ["last_name", "lastname", "lname", "last-name", "family_name"],
        "full_name": ["full_name", "fullname", "name", "your_name", "candidate_name"],
        "phone": ["phone", "telephone", "mobile", "cell", "phone_number"],
        "address": ["address", "street", "street_address", "address1"],
        "city": ["city", "town"],
        "state": ["state", "province", "region"],
        "zip": ["zip", "zipcode", "zip_code", "postal", "postcode"],
        "country": ["country", "nation"],
        "linkedin": ["linkedin", "linkedin_url", "linkedin_profile"],
        "website": ["website", "portfolio", "url", "personal_website"],
        "cover_letter": ["cover_letter", "coverletter", "cover-letter", "message"],
        "salary": ["salary", "compensation", "expected_salary", "salary_expectation"],
        "experience": ["experience", "years_experience", "years_of_experience"],
        "resume": ["resume", "cv", "file", "upload"],
    }

    # Cross-field mappings: when looking for 'username', also check 'email' fields
    # This handles sites like Instagram that use name="email" for username input
    CROSS_FIELD_MAP = {
        "username": ["email"],
        "email": ["username"],
    }

    def __init__(self, browser):
        self.browser = browser

    async def _type_with_delay(self, selector: str, value: str) -> bool:
        """Type text into a field with human-like delays between keystrokes.

        Uses a multi-strategy approach:
        1. Try browser.fill_form for the single field (leverages the browser's
           production-grade multi-strategy filling with focus, clear, and verify)
        2. Try clicking the element first, then using browser.type_text
        3. Try Playwright keyboard.type via the browser's internal page object
        4. Final fallback: evaluate_js to set value and dispatch events

        Args:
            selector: CSS selector for the target element
            value: Text value to type

        Returns:
            True if the field was filled successfully, False otherwise
        """
        # Strategy 1: Use browser.fill_form for a single field — this uses the
        # production-grade multi-strategy finder, focus, clear, type, verify flow
        try:
            fill_result = await self.browser.fill_form({selector: value})
            if isinstance(fill_result, dict):
                if fill_result.get("status") == "success":
                    return True
                # Check if field was filled even if status isn't "success"
                filled = fill_result.get("filled", [])
                if filled and len(filled) > 0:
                    return True
        except Exception as e:
            logger.debug(f"fill_form strategy failed for {selector}: {e}")

        # Strategy 2: Click the element, then type into it
        try:
            click_result = await self.browser.click(selector)
            if isinstance(click_result, dict) and click_result.get("status") == "success":
                # Small delay after clicking to let focus settle
                await asyncio.sleep(random.uniform(0.15, 0.35))
                type_result = await self.browser.type_text(value)
                if isinstance(type_result, dict) and type_result.get("status") == "success":
                    return True
        except Exception as e:
            logger.debug(f"click+type_text strategy failed for {selector}: {e}")

        # Strategy 3: Try Playwright's keyboard.type via the browser's internal page
        try:
            if hasattr(self.browser, '_pages') and self.browser._pages:
                page = self.browser._pages.get("main", self.browser.page)
                if page:
                    # Focus the element via JS
                    try:
                        await self.browser.evaluate_js(
                            f"document.querySelector('{selector}')?.focus()"
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(random.uniform(0.1, 0.2))
                    await page.keyboard.type(value, delay=random.randint(30, 120))
                    return True
            elif hasattr(self.browser, 'page') and self.browser.page:
                try:
                    await self.browser.evaluate_js(
                        f"document.querySelector('{selector}')?.focus()"
                    )
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(0.1, 0.2))
                await self.browser.page.keyboard.type(value, delay=random.randint(30, 120))
                return True
        except Exception as e:
            logger.debug(f"keyboard.type strategy failed for {selector}: {e}")

        # Strategy 4: Final fallback — use evaluate_js to set value and dispatch events
        try:
            escaped_value = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            js_result = await self.browser.evaluate_js(f"""
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.focus();
                    el.value = '{escaped_value}';
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return true;
                }}
                return false;
            """)
            if isinstance(js_result, dict) and js_result.get("result"):
                return True
        except Exception as e:
            logger.warning(f"All typing strategies failed for {selector}: {e}")

        return False

    async def fill_job_application(self, url: str, profile: Dict[str, str]) -> Dict:
        """
        Fill a job application form automatically.

        profile should contain:
        - email, first_name, last_name, phone, address, city, state, zip
        - cover_letter (optional), salary (optional), linkedin (optional)
        """
        logger.info(f"Filling job application at {url}")

        # Navigate to the job page
        try:
            nav_result = await self.browser.navigate(url)
            # browser.navigate() may return a dict or a string (URL)
            if isinstance(nav_result, dict):
                if nav_result.get("status") != "success":
                    return nav_result
            elif isinstance(nav_result, str):
                # navigate() returned a URL string — navigation succeeded
                pass
            # If nav_result is None or unexpected, continue anyway
        except Exception as e:
            logger.error(f"Navigation failed for {url}: {e}")
            return {"status": "error", "error": f"Navigation failed: {e}"}

        # Detect all form fields
        try:
            result = await self.browser.evaluate_js("""() => {
                const fields = [];
                document.querySelectorAll('input, textarea, select').forEach(el => {
                    if (el.type === 'hidden' || el.type === 'submit') return;
                    fields.push({
                        tag: el.tagName.toLowerCase(),
                        type: el.type || 'text',
                        name: el.name || '',
                        id: el.id || '',
                        placeholder: el.placeholder || '',
                        label: el.labels?.[0]?.textContent?.trim() || '',
                        aria_label: el.getAttribute('aria-label') || '',
                        title: el.title || '',
                        data_testid: el.getAttribute('data-testid') || '',
                        required: el.required,
                        options: el.tagName === 'SELECT'
                            ? Array.from(el.options).map(o => ({value: o.value, text: o.text}))
                            : []
                    });
                });
                return fields;
            }""")
            # evaluate_js now returns {"status": ..., "result": ...} — unwrap
            if isinstance(result, dict) and result.get("status") == "success":
                fields = result.get("result", [])
            elif isinstance(result, list):
                fields = result  # backward compat
            else:
                fields = []
                
        except Exception as e:
            logger.error(f"Field detection failed: {e}")
            return {"status": "error", "error": f"Field detection failed: {e}"}

        if not fields:
            return {"status": "error", "error": "No form fields found on page"}

        # Map detected fields to profile data
        fill_map = {}
        for field in fields:
            matched_value = self._match_field(field, profile)
            if matched_value:
                selector = self._build_selector(field)
                fill_map[selector] = matched_value

        if not fill_map:
            return {"status": "error", "error": "No matching fields found for profile data"}

        # Fill the form with human-like timing — field by field with inter-field delays
        filled_fields = []
        failed_fields = []

        for selector, value in fill_map.items():
            try:
                # Human-like delay between fields (800ms-2500ms)
                await asyncio.sleep(random.uniform(0.8, 2.5))

                # Clear existing value first using JS
                try:
                    await self.browser.evaluate_js(f"""
                        const el = document.querySelector('{selector}');
                        if (el) {{ el.value = ''; el.dispatchEvent(new Event('input', {{bubbles: true}})); }}
                    """)
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                except Exception:
                    pass

                # Type with human-like keystroke delay
                success = await self._type_with_delay(selector, value)

                if success:
                    filled_fields.append(selector)
                else:
                    failed_fields.append(selector)
            except Exception as e:
                logger.warning(f"Failed to fill field '{selector}': {e}")
                failed_fields.append(selector)

        return {
            "status": "success",
            "fields_detected": len(fields),
            "fields_filled": len(filled_fields),
            "fields_failed": len(failed_fields),
            "filled_selectors": filled_fields,
            "failed_selectors": failed_fields,
            "fill_map": fill_map,
            "note": "Review before submitting — form filled but NOT submitted automatically"
        }

    async def fill_multi_page_form(
        self,
        url: str,
        profile: Dict[str, str],
        max_pages: int = 5,
        next_button_selectors: Optional[List[str]] = None,
    ) -> Dict:
        """Fill a multi-page form (e.g., job application with multiple steps).

        Fills the current page, then clicks 'Next'/'Continue' to proceed
        to the next page and fills that too. Repeats until no more
        next buttons are found or max_pages is reached.

        Args:
            url: Starting URL of the form
            profile: User profile data
            max_pages: Maximum number of pages to fill (safety limit)
            next_button_selectors: Custom selectors for the next/continue button

        Returns:
            Summary of all pages filled
        """
        NEXT_SELECTORS = next_button_selectors or [
            'button[type="submit"]',
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button:has-text("Proceed")',
            'button:has-text("Save and Continue")',
            'button:has-text("Save & Next")',
            'a:has-text("Next")',
            'a:has-text("Continue")',
            'input[type="submit"]',
            '.next-btn',
            '.continue-btn',
            '[data-testid="next-button"]',
            '[data-testid="continue-button"]',
        ]

        # Navigate to the form
        try:
            nav_result = await self.browser.navigate(url)
            if isinstance(nav_result, dict) and nav_result.get("status") == "error":
                return nav_result
        except Exception as e:
            return {"status": "error", "error": f"Navigation failed: {e}"}

        all_results = []
        total_fields = 0
        total_filled = 0

        for page_num in range(1, max_pages + 1):
            # Wait for page to be ready
            await asyncio.sleep(1.5)

            # Fill current page
            try:
                # Detect fields on current page
                result = await self.browser.evaluate_js("""() => {
                    const fields = [];
                    document.querySelectorAll('input, textarea, select').forEach(el => {
                        if (el.type === 'hidden' || el.type === 'submit') return;
                        fields.push({
                            tag: el.tagName.toLowerCase(),
                            type: el.type || 'text',
                            name: el.name || '',
                            id: el.id || '',
                            placeholder: el.placeholder || '',
                            label: el.labels?.[0]?.textContent?.trim() || '',
                            aria_label: el.getAttribute('aria-label') || '',
                            title: el.title || '',
                            data_testid: el.getAttribute('data-testid') || '',
                            required: el.required,
                            options: el.tagName === 'SELECT'
                                ? Array.from(el.options).map(o => ({value: o.value, text: o.text}))
                                : []
                        });
                    });
                    return fields;
                }""")

                if isinstance(result, dict) and result.get("status") == "success":
                    fields = result.get("result", [])
                elif isinstance(result, list):
                    fields = result
                else:
                    fields = []

                if not fields:
                    # No fields found — might be a review/confirmation page
                    all_results.append({
                        "page": page_num,
                        "status": "no_fields",
                        "message": "No form fields found on this page (possibly a review/confirmation page)"
                    })
                    # Still try to click next
                else:
                    # Map and fill fields
                    fill_map = {}
                    for field in fields:
                        matched_value = self._match_field(field, profile)
                        if matched_value:
                            selector = self._build_selector(field)
                            fill_map[selector] = matched_value

                    page_filled = 0
                    page_failed = 0
                    for selector, value in fill_map.items():
                        await asyncio.sleep(random.uniform(0.8, 2.5))
                        success = await self._type_with_delay(selector, value)
                        if success:
                            page_filled += 1
                        else:
                            page_failed += 1

                    total_fields += len(fields)
                    total_filled += page_filled

                    all_results.append({
                        "page": page_num,
                        "fields_detected": len(fields),
                        "fields_filled": page_filled,
                        "fields_failed": page_failed,
                    })
            except Exception as e:
                all_results.append({"page": page_num, "status": "error", "error": str(e)})

            # Try to find and click the next/continue button
            next_clicked = False
            for selector in NEXT_SELECTORS:
                try:
                    click_result = await self.browser.click(selector)
                    if isinstance(click_result, dict) and click_result.get("status") == "success":
                        next_clicked = True
                        # Wait for page transition
                        await asyncio.sleep(2.0)
                        break
                except Exception:
                    continue

            if not next_clicked:
                # No next button found — form is complete or single-page
                break

        return {
            "status": "success",
            "pages_processed": len(all_results),
            "total_fields_detected": total_fields,
            "total_fields_filled": total_filled,
            "page_details": all_results,
            "note": "Multi-page form filling complete — review before final submission"
        }

    async def auto_submit(self) -> Dict:
        """Click submit button (use with caution)."""
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit")',
            'button:has-text("Apply")',
            'button:has-text("Send")',
            'button:has-text("Continue")',
            '[data-testid="submit-button"]',
            '.submit-btn',
            '#submit',
        ]

        submitted = False
        submitted_via = None

        for selector in submit_selectors:
            try:
                result = await self.browser.click(selector)
                if result.get("status") == "success":
                    submitted = True
                    submitted_via = selector
                    break  # Stop after first successful submit to prevent double submission
            except Exception as e:
                logger.warning(f"Failed to click submit selector '{selector}': {e}")
                continue

        if submitted:
            return {"status": "success", "submitted_via": submitted_via}

        # Final fallback: submit form via JavaScript
        try:
            js_result = await self.browser.evaluate_js("""
                const form = document.querySelector('form');
                if (form) { form.submit(); return true; }
                return false;
            """)
            if isinstance(js_result, dict) and js_result.get("result"):
                return {"status": "success", "submitted_via": "js_form_submit"}
        except Exception:
            pass

        return {"status": "error", "error": "Could not find submit button"}

    # Common misspellings mapped to correct field type names
    MISSPELLING_MAP = {
        "emial": "email",
        "e-mail": "email",
        "fisrtname": "first_name",
        "firtsname": "first_name",
        "frist_name": "first_name",
        "fisrt_name": "first_name",
        "lastnme": "last_name",
        "lasname": "last_name",
        "passowrd": "password",
        "passwrod": "password",
        "phonenumber": "phone",
        "phon": "phone",
        "adddress": "address",
        "adress": "address",
        "zipocde": "zip",
        "zipcoce": "zip",
        "contry": "country",
        "conutry": "country",
    }

    def _match_field(self, field: Dict, profile: Dict) -> Optional[str]:
        """Match a form field to profile data.

        Multi-strategy matching:
        1. Check name, id, placeholder, label attributes
        2. Also check aria-label, title, data-testid attributes
        3. Fuzzy matching for common misspellings (e.g., "emial" → "email")
        4. Cross-field mappings (e.g., username field can match email profile data)
        """
        name = (field.get("name") or "").lower()
        id_ = (field.get("id") or "").lower()
        placeholder = (field.get("placeholder") or "").lower()
        label = (field.get("label") or "").lower()
        aria_label = (field.get("aria_label") or "").lower()
        title = (field.get("title") or "").lower()
        data_testid = (field.get("data_testid") or "").lower()
        combined = f"{name} {id_} {placeholder} {label} {aria_label} {title} {data_testid}"

        # Apply misspelling corrections to combined text
        corrected = combined
        for misspelling, correction in self.MISSPELLING_MAP.items():
            if misspelling in corrected:
                corrected = corrected.replace(misspelling, correction)

        # Try matching with both original and corrected text
        for text in (combined, corrected):
            for field_type, patterns in self.FIELD_PATTERNS.items():
                if any(p in text for p in patterns):
                    value = profile.get(field_type)
                    if value:
                        return value
                    # Try cross-field mapping (e.g., username field → email profile data)
                    cross_fields = self.CROSS_FIELD_MAP.get(field_type, [])
                    for cross_field in cross_fields:
                        cross_value = profile.get(cross_field)
                        if cross_value:
                            logger.debug(f"Cross-field match: {field_type} → {cross_field} for field '{name}'")
                            return cross_value

        return None

    def _build_selector(self, field: Dict) -> str:
        """Build a CSS selector for a form field with multi-strategy fallbacks."""
        tag = field.get("tag", "input")
        if field.get("id"):
            return f'#{field["id"]}'
        if field.get("name"):
            return f'{tag}[name="{field["name"]}"]'
        if field.get("placeholder"):
            return f'{tag}[placeholder="{field["placeholder"]}"]'
        # Try aria-label selector
        if field.get("aria_label"):
            return f'{tag}[aria-label="{field["aria_label"]}"]'
        # Try data-testid selector
        if field.get("data_testid"):
            return f'{tag}[data-testid="{field["data_testid"]}"]'
        # Try CSS :has-text pseudo-selector as fallback (for label text)
        label = field.get("label", "").strip()
        if label:
            return f'{tag}:has-text("{label}")'
        return tag


class ProfileBuilder:
    """Builds a user profile for form filling."""

    @staticmethod
    def from_dict(data: Dict[str, str]) -> Dict[str, str]:
        """Create profile from dictionary."""
        return {
            "email": data.get("email", ""),
            "first_name": data.get("first_name", data.get("firstName", "")),
            "last_name": data.get("last_name", data.get("lastName", "")),
            "full_name": data.get("full_name", data.get("fullName", "")),
            "phone": data.get("phone", data.get("phoneNumber", "")),
            "address": data.get("address", data.get("streetAddress", "")),
            "city": data.get("city", ""),
            "state": data.get("state", data.get("province", "")),
            "zip": data.get("zip", data.get("zipCode", data.get("postalCode", ""))),
            "country": data.get("country", ""),
            "linkedin": data.get("linkedin", data.get("linkedinUrl", "")),
            "website": data.get("website", data.get("portfolio", "")),
            "cover_letter": data.get("cover_letter", data.get("coverLetter", "")),
            "salary": data.get("salary", data.get("expectedSalary", "")),
            "experience": data.get("experience", data.get("yearsExperience", "")),
        }
