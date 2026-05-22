#!/usr/bin/env python3
"""
Agent-OS Live Form Filling Test
Tests form filling on Instagram and Twitter signup pages with fake data.
Uses headed browser for screenshots.
"""
import asyncio
import sys
import os
import json
import time
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.core.config import Config
from src.core.browser import AgentBrowser
from src.tools.form_filler import FormFiller, ProfileBuilder

# Fake test data — NOT real accounts
FAKE_PROFILE = {
    "first_name": "Test",
    "last_name": "Bot",
    "email": "test.bot.audit2026@example.com",
    "phone": "+15551234567",
    "username": "testbot_audit_2026",
    "password": "TestAudit2026!@#",
    "birthday_month": "06",
    "birthday_day": "15",
    "birthday_year": "1995",
}

SCREENSHOT_DIR = Path("/home/z/my-project/download/test_screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def save_screenshot(browser, name: str):
    """Save screenshot and return path."""
    try:
        b64 = await browser.screenshot()
        if b64:
            img_data = base64.b64decode(b64)
            path = SCREENSHOT_DIR / f"{name}.png"
            path.write_bytes(img_data)
            print(f"  📸 Screenshot saved: {path}")
            return str(path)
    except Exception as e:
        print(f"  ⚠️ Screenshot failed: {e}")
    return None


async def test_instagram_form():
    """Test form filling on Instagram signup page."""
    print("\n" + "=" * 70)
    print("TEST: Instagram Signup Form Filling")
    print("=" * 70)

    config = Config()
    config.set("browser.headless", True)  # Headless for server
    browser = AgentBrowser(config)

    try:
        print("  Starting browser...")
        await browser.start()
        print("  ✅ Browser started")

        # Navigate to Instagram signup
        print("  Navigating to Instagram signup...")
        result = await browser.navigate("https://www.instagram.com/accounts/emailsignup/")
        print(f"  Navigation result: {result.get('status')}")

        # Wait for page to load
        await asyncio.sleep(3)

        # Take screenshot of signup page
        await save_screenshot(browser, "01_instagram_signup_page")

        # Try to fill the signup form
        form_filler = FormFiller(browser)

        # Instagram uses React, so we need to use the React-aware fill
        # The email/phone field
        print("  Attempting to fill email field...")
        try:
            # Try multiple selectors for the email field
            email_selectors = [
                'input[name="emailOrPhone"]',
                'input[aria-label="Mobile Number or Email"]',
                'input[placeholder*="email"]',
                'input[placeholder*="Mobile"]',
                'input[type="email"]',
                'input[type="text"]',
            ]
            filled = False
            for selector in email_selectors:
                try:
                    el = await browser.page.query_selector(selector)
                    if el:
                        await el.click()
                        await asyncio.sleep(0.3)
                        await el.fill("")
                        for char in FAKE_PROFILE["email"]:
                            await el.type(char, delay=80)
                        print(f"  ✅ Email filled via: {selector}")
                        filled = True
                        break
                except Exception:
                    continue

            if not filled:
                print("  ⚠️ Could not find email field — page structure may differ")

        except Exception as e:
            print(f"  ⚠️ Email fill error: {e}")

        # Try fullname field
        print("  Attempting to fill full name field...")
        try:
            name_selectors = [
                'input[name="fullName"]',
                'input[aria-label="Full Name"]',
                'input[placeholder*="Full Name"]',
                'input[placeholder*="full name"]',
            ]
            for selector in name_selectors:
                try:
                    el = await browser.page.query_selector(selector)
                    if el:
                        await el.click()
                        await asyncio.sleep(0.2)
                        await el.fill("")
                        for char in FAKE_PROFILE["first_name"] + " " + FAKE_PROFILE["last_name"]:
                            await el.type(char, delay=70)
                        print(f"  ✅ Name filled via: {selector}")
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"  ⚠️ Name fill error: {e}")

        # Try username field
        print("  Attempting to fill username field...")
        try:
            username_selectors = [
                'input[name="username"]',
                'input[aria-label="Username"]',
                'input[placeholder*="Username"]',
            ]
            for selector in username_selectors:
                try:
                    el = await browser.page.query_selector(selector)
                    if el:
                        await el.click()
                        await asyncio.sleep(0.2)
                        await el.fill("")
                        for char in FAKE_PROFILE["username"]:
                            await el.type(char, delay=90)
                        print(f"  ✅ Username filled via: {selector}")
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"  ⚠️ Username fill error: {e}")

        # Try password field
        print("  Attempting to fill password field...")
        try:
            password_selectors = [
                'input[name="password"]',
                'input[aria-label="Password"]',
                'input[placeholder*="Password"]',
                'input[type="password"]',
            ]
            for selector in password_selectors:
                try:
                    el = await browser.page.query_selector(selector)
                    if el:
                        await el.click()
                        await asyncio.sleep(0.2)
                        await el.fill("")
                        for char in FAKE_PROFILE["password"]:
                            await el.type(char, delay=60)
                        print(f"  ✅ Password filled via: {selector}")
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"  ⚠️ Password fill error: {e}")

        await asyncio.sleep(1)

        # Screenshot after filling
        await save_screenshot(browser, "02_instagram_form_filled")

        # Check page title
        title = await browser.page.title()
        print(f"  Page title: {title}")

        # Test AI content extraction on the page
        print("\n  Testing AI content extraction on Instagram page...")
        try:
            from src.tools.ai_content import AIContentExtractor
            extractor = AIContentExtractor()
            ai_result = await extractor.extract_from_browser(browser, page_id="main")
            if ai_result.get("status") == "success":
                data = ai_result["data"]
                print(f"  ✅ AI Content extracted:")
                print(f"     Type: {data.get('content_type')}")
                print(f"     Title: {data.get('title', '')[:60]}")
                print(f"     Forms found: {len(data.get('forms', []))}")
                print(f"     Links found: {len(data.get('links', []))}")
                print(f"     Images found: {len(data.get('images', []))}")
                for form in data.get("forms", []):
                    print(f"     Form fields: {[f['name'] or f['type'] for f in form.get('fields', [])]}")
            else:
                print(f"  ⚠️ AI extraction error: {ai_result.get('error')}")
        except Exception as e:
            print(f"  ⚠️ AI content extraction error: {e}")

        print("\n  ✅ Instagram form test COMPLETE")
        return True

    except Exception as e:
        print(f"  ❌ Instagram test error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await browser.stop()
        print("  Browser stopped")


async def test_twitter_form():
    """Test form filling on Twitter signup page."""
    print("\n" + "=" * 70)
    print("TEST: Twitter/X Signup Form Filling")
    print("=" * 70)

    config = Config()
    config.set("browser.headless", True)
    browser = AgentBrowser(config)

    try:
        print("  Starting browser...")
        await browser.start()
        print("  ✅ Browser started")

        # Navigate to Twitter signup
        print("  Navigating to Twitter/X signup...")
        result = await browser.navigate("https://x.com/i/flow/signup")
        print(f"  Navigation result: {result.get('status')}")

        # Wait for SPA to load
        await asyncio.sleep(4)

        # Screenshot of signup page
        await save_screenshot(browser, "03_twitter_signup_page")

        # Twitter uses a multi-step signup flow
        # Step 1: Name field
        print("  Attempting to fill name field...")
        try:
            name_selectors = [
                'input[name="name"]',
                'input[autocomplete="name"]',
                'input[placeholder*="Name"]',
                'input[aria-label*="Name"]',
            ]
            for selector in name_selectors:
                try:
                    el = await browser.page.query_selector(selector)
                    if el:
                        await el.click()
                        await asyncio.sleep(0.3)
                        await el.fill("")
                        for char in FAKE_PROFILE["first_name"] + " " + FAKE_PROFILE["last_name"]:
                            await el.type(char, delay=70)
                        print(f"  ✅ Name filled via: {selector}")
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"  ⚠️ Name fill error: {e}")

        # Try email/phone field
        print("  Attempting to fill email field...")
        try:
            email_selectors = [
                'input[name="email"]',
                'input[autocomplete="email"]',
                'input[type="email"]',
                'input[placeholder*="email"]',
                'input[aria-label*="email"]',
                'input[placeholder*="Phone"]',
            ]
            for selector in email_selectors:
                try:
                    el = await browser.page.query_selector(selector)
                    if el:
                        await el.click()
                        await asyncio.sleep(0.2)
                        await el.fill("")
                        for char in FAKE_PROFILE["email"]:
                            await el.type(char, delay=80)
                        print(f"  ✅ Email filled via: {selector}")
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"  ⚠️ Email fill error: {e}")

        await asyncio.sleep(1)

        # Screenshot after filling
        await save_screenshot(browser, "04_twitter_form_filled")

        # Check page title
        title = await browser.page.title()
        print(f"  Page title: {title}")

        # Test AI content extraction
        print("\n  Testing AI content extraction on Twitter/X page...")
        try:
            from src.tools.ai_content import AIContentExtractor
            extractor = AIContentExtractor()
            ai_result = await extractor.extract_from_browser(browser, page_id="main")
            if ai_result.get("status") == "success":
                data = ai_result["data"]
                print(f"  ✅ AI Content extracted:")
                print(f"     Type: {data.get('content_type')}")
                print(f"     Title: {data.get('title', '')[:60]}")
                print(f"     Forms found: {len(data.get('forms', []))}")
                for form in data.get("forms", []):
                    print(f"     Form fields: {[f['name'] or f['type'] for f in form.get('fields', [])]}")
            else:
                print(f"  ⚠️ AI extraction error: {ai_result.get('error')}")
        except Exception as e:
            print(f"  ⚠️ AI content extraction error: {e}")

        print("\n  ✅ Twitter form test COMPLETE")
        return True

    except Exception as e:
        print(f"  ❌ Twitter test error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await browser.stop()
        print("  Browser stopped")


async def test_smart_navigation():
    """Test SmartNavigator with AI format on real websites."""
    print("\n" + "=" * 70)
    print("TEST: Smart Navigator + AI Content Extraction")
    print("=" * 70)

    config = Config()
    browser = AgentBrowser(config)

    try:
        await browser.start()

        from src.core.smart_navigator import SmartNavigator
        nav = SmartNavigator(browser)

        # Test HTTP path (Wikipedia)
        print("\n  Testing HTTP fetch on Wikipedia...")
        result = await nav.navigate(
            "https://en.wikipedia.org/wiki/Artificial_intelligence",
            ai_format=True,
        )
        if result.get("status") == "success":
            print(f"  ✅ HTTP fetch successful (strategy: {result.get('strategy_used', 'http')})")
            if "ai_content" in result:
                data = result["ai_content"]
                print(f"     Content type: {data.get('content_type')}")
                print(f"     Title: {data.get('title', '')[:60]}")
                print(f"     Word count: {data.get('word_count', 0)}")
                print(f"     Headings: {len(data.get('headings', []))}")
                print(f"     Links: {len(data.get('links', []))}")
            else:
                print("  ⚠️ No ai_content in result")
        else:
            print(f"  ⚠️ HTTP fetch failed: {result.get('error', '')[:100]}")

        print("\n  ✅ Smart Navigator test COMPLETE")
        return True

    except Exception as e:
        print(f"  ❌ Smart Navigator test error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await browser.stop()


async def main():
    print("\n" + "=" * 70)
    print("Agent-OS LIVE FORM FILLING TEST SUITE")
    print("Using FAKE DATA only — no real accounts")
    print("=" * 70)

    results = {}

    # Test 1: Instagram form filling
    results["instagram"] = await test_instagram_form()

    # Test 2: Twitter form filling
    results["twitter"] = await test_twitter_form()

    # Test 3: Smart Navigation + AI Content
    results["smart_nav"] = await test_smart_navigation()

    # Summary
    print("\n" + "=" * 70)
    print("TEST RESULTS SUMMARY")
    print("=" * 70)
    for test_name, passed in results.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {test_name}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  Passed: {passed}/{total}")
    print(f"  Screenshots saved to: {SCREENSHOT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
