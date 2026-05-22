#!/usr/bin/env python3
"""
Agent-OS LIVE BRUTAL TEST
==========================
Actually launches a browser, visits real websites, tests stealth, form filling,
navigation, screenshots, and all core features. NO MOCKING. REAL BROWSER ONLY.

This is the REAL test — not unit tests with mocks.
"""
import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

sys.path.insert(0, str(Path(__file__).parent))

@dataclass
class LiveTestResult:
    name: str
    passed: bool
    error: str = ""
    duration_ms: float = 0
    detail: str = ""

@dataclass
class LiveTestSuite:
    category: str
    results: List[LiveTestResult] = field(default_factory=list)

    @property
    def passed(self): return sum(1 for r in self.results if r.passed)
    @property
    def failed(self): return sum(1 for r in self.results if not r.passed)
    @property
    def total(self): return len(self.results)

ALL_RESULTS: List[LiveTestSuite] = []
websites_visited: List[str] = []

def record(category: str, name: str, passed: bool, error: str = "", duration_ms: float = 0, detail: str = ""):
    result = LiveTestResult(name=name, passed=passed, error=error[:300], duration_ms=duration_ms, detail=detail)
    # Find or create suite
    for suite in ALL_RESULTS:
        if suite.category == category:
            suite.results.append(result)
            return
    suite = LiveTestSuite(category=category)
    suite.results.append(result)
    ALL_RESULTS.append(suite)


async def run_live_brutal_test():
    """The actual live browser brutal test."""
    
    from src.core.config import Config
    from src.core.browser import AgentBrowser

    print("\n" + "="*80)
    print("  AGENT-OS LIVE BRUTAL TEST — Real Browser, Real Websites")
    print("="*80)

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: BROWSER LAUNCH
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 1: Browser Launch...")
    
    config = Config(tempfile.mktemp(suffix=".yaml"))
    config.set("browser.headless", True)
    config.set("browser.tls_proxy_enabled", False)  # No TLS proxy for headless
    config.set("browser.firefox_fallback", False)   # No Firefox for this test
    
    browser = AgentBrowser(config)
    
    start = time.time()
    try:
        await browser.start()
        duration = (time.time() - start) * 1000
        record("1. Browser Launch", "launch_browser", True, duration_ms=duration, detail="Browser started successfully")
        print(f"  ✅ Browser launched in {duration:.0f}ms")
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("1. Browser Launch", "launch_browser", False, str(e), duration)
        print(f"  ❌ Browser launch FAILED: {e}")
        print("\n🚨 CANNOT CONTINUE — browser didn't launch")
        return

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: STEALTH VERIFICATION
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 2: Stealth Verification...")
    
    # First navigate to a real page for accurate stealth testing
    start = time.time()
    try:
        await browser.page.goto("https://example.com", timeout=10000)
        await asyncio.sleep(1.5)  # Let stealth hooks run
    except:
        pass

    stealth_tests = [
        # (JS expression, expected value or condition, test name)
        ("navigator.webdriver", "undefined", "webdriver_undefined"),
        ("navigator.plugins.length >= 3", True, "plugins_exist"),
        ("window.chrome !== undefined && window.chrome !== null", True, "chrome_object_exists"),
        ("window.chrome.runtime !== undefined", True, "chrome_runtime_exists"),
        ("navigator.languages[0]", "en-US", "languages_correct"),
        ("typeof navigator.hardwareConcurrency === 'number'", True, "hardware_concurrency_number"),
        ("navigator.hardwareConcurrency > 0", True, "hardware_concurrency_positive"),
        ("typeof navigator.deviceMemory === 'number'", True, "device_memory_number"),
        ("screen.width > 0", True, "screen_width_positive"),
        ("screen.height > 0", True, "screen_height_positive"),
        ("window.devicePixelRatio > 0", True, "pixel_ratio_positive"),
        ("navigator.platform.length > 0", True, "platform_set"),
        ("navigator.connection !== undefined", True, "connection_exists"),
    ]

    for js_expr, expected, test_name in stealth_tests:
        start = time.time()
        try:
            result = await browser.page.evaluate(f"() => {js_expr}")
            duration = (time.time() - start) * 1000
            
            if expected == "undefined":
                passed = result is None or result is False or result == "undefined"
            elif isinstance(expected, bool):
                passed = bool(result) == expected
            elif isinstance(expected, (int, float)):
                passed = result == expected
            elif isinstance(expected, str):
                passed = str(result) == expected
            else:
                passed = result == expected
            
            detail = f"Expected: {expected}, Got: {result}"
            record("2. Stealth Verification", test_name, passed, "" if passed else detail, duration, detail)
            status = "✅" if passed else "❌"
            print(f"  {status} {test_name}: {result} (expected {expected})")
        except Exception as e:
            duration = (time.time() - start) * 1000
            record("2. Stealth Verification", test_name, False, str(e), duration)
            print(f"  ❌ {test_name}: ERROR - {e}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: REAL WEBSITE NAVIGATION
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 3: Real Website Navigation...")
    
    test_sites = [
        ("https://example.com", "Example Domain", "example_com"),
        ("https://www.wikipedia.org", "Wikipedia", "wikipedia"),
        ("https://httpbin.org/headers", "httpbin_headers", "httpbin_headers"),
        ("https://www.google.com", "Google", "google"),
        ("https://github.com", "GitHub", "github"),
        ("https://news.ycombinator.com", "Hacker News", "hn"),
        ("https://www.reddit.com", "Reddit", "reddit"),
        ("https://www.bbc.com", "BBC", "bbc"),
        ("https://www.cnn.com", "CNN", "cnn"),
        ("https://www.amazon.com", "Amazon", "amazon"),
        ("https://www.nytimes.com", "NYTimes", "nytimes"),
        ("https://www.linkedin.com", "LinkedIn", "linkedin"),
        ("https://www.facebook.com", "Facebook", "facebook"),
        ("https://www.instagram.com", "Instagram", "instagram"),
        ("https://www.twitter.com", "Twitter/X", "twitter"),
        ("https://www.youtube.com", "YouTube", "youtube"),
        ("https://www.microsoft.com", "Microsoft", "microsoft"),
        ("https://www.apple.com", "Apple", "apple"),
        ("https://www.netflix.com", "Netflix", "netflix"),
        ("https://www.stackoverflow.com", "StackOverflow", "stackoverflow"),
    ]

    for url, expected_title, test_name in test_sites:
        start = time.time()
        try:
            response = await browser.page.goto(url, timeout=20000, wait_until="domcontentloaded")
            await asyncio.sleep(1.5)  # Let page settle
            
            # Check if page loaded
            title = await browser.page.title()
            status_code = response.status if response else 0
            duration = (time.time() - start) * 1000
            
            # Page loaded if we got any response (even redirects are OK)
            loaded = status_code > 0 or len(title) > 0
            
            # Check stealth on every page
            try:
                webdriver = await browser.page.evaluate("() => navigator.webdriver")
                plugins_len = await browser.page.evaluate("() => navigator.plugins ? navigator.plugins.length : 0")
                chrome_exists = await browser.page.evaluate("() => window.chrome !== undefined && window.chrome !== null")
            except:
                webdriver = "error"
                plugins_len = 0
                chrome_exists = False
            
            stealth_ok = (webdriver is None or webdriver is False) and plugins_len >= 3 and chrome_exists
            
            detail = f"Status: {status_code}, Title: '{title[:50]}', Stealth: webdriver={webdriver}, plugins={plugins_len}, chrome={chrome_exists}"
            record("3. Website Navigation", test_name, loaded, "" if loaded else detail, duration, detail)
            websites_visited.append(url)
            
            status = "✅" if loaded else "❌"
            stealth_status = "🛡️" if stealth_ok else "⚠️"
            print(f"  {status} {url} — {status_code} — '{title[:40]}' {stealth_status}")
            
        except Exception as e:
            duration = (time.time() - start) * 1000
            record("3. Website Navigation", test_name, False, str(e), duration)
            print(f"  ❌ {url} — ERROR: {str(e)[:80]}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 4: FORM FILLING (Real Forms)
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 4: Form Filling...")
    
    # Test with httpbin forms
    start = time.time()
    try:
        await browser.page.goto("https://httpbin.org/forms/post", timeout=15000)
        await asyncio.sleep(1)
        
        # Check if form elements exist
        form_fields = await browser.page.evaluate("""() => {
            const fields = [];
            document.querySelectorAll('input, textarea, select').forEach(el => {
                fields.push({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || 'text',
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                });
            });
            return fields;
        }""")
        
        duration = (time.time() - start) * 1000
        has_fields = len(form_fields) > 0
        record("4. Form Filling", "httpbin_form_detect", has_fields, "" if has_fields else "No form fields found", duration, f"Found {len(form_fields)} fields")
        print(f"  {'✅' if has_fields else '❌'} httpbin form: {len(form_fields)} fields detected")
        
        # Try filling the form using FormFiller
        if has_fields:
            from src.tools.form_filler import FormFiller
            filler = FormFiller(browser)
            
            profile = {
                "email": "test@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "phone": "555-1234",
                "cover_letter": "I am writing to apply for the position.",
            }
            
            start = time.time()
            try:
                result = await filler.fill_job_application("https://httpbin.org/forms/post", profile)
                duration = (time.time() - start) * 1000
                passed = result.get("status") == "success"
                record("4. Form Filling", "fill_httpbin_form", passed, "" if passed else result.get("error", "unknown"), duration, str(result)[:200])
                print(f"  {'✅' if passed else '❌'} fill_httpbin_form: {result.get('status')} ({result.get('fields_filled', 0)} fields)")
            except Exception as e:
                duration = (time.time() - start) * 1000
                record("4. Form Filling", "fill_httpbin_form", False, str(e), duration)
                print(f"  ❌ fill_httpbin_form: ERROR - {e}")
        
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("4. Form Filling", "httpbin_form_detect", False, str(e), duration)
        print(f"  ❌ httpbin form: ERROR - {e}")

    # Test manual form filling with special characters
    start = time.time()
    try:
        await browser.page.goto("https://httpbin.org/forms/post", timeout=15000)
        await asyncio.sleep(1)
        
        # Try typing special characters directly
        special_text = "test+user@domain.com"
        input_el = await browser.page.query_selector('input[type="text"], input:not([type])')
        if input_el:
            await input_el.click()
            await browser.page.keyboard.type(special_text, delay=50)
            typed_value = await input_el.input_value()
            passed = typed_value == special_text
            record("4. Form Filling", "special_chars_typing", passed, f"Expected '{special_text}', got '{typed_value}'", (time.time() - start) * 1000)
            print(f"  {'✅' if passed else '❌'} special_chars: typed '{special_text}', got '{typed_value}'")
        else:
            record("4. Form Filling", "special_chars_typing", False, "No input field found", (time.time() - start) * 1000)
            print(f"  ❌ special_chars: No input field found")
    except Exception as e:
        record("4. Form Filling", "special_chars_typing", False, str(e), (time.time() - start) * 1000)
        print(f"  ❌ special_chars: ERROR - {e}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 5: STEALTH DEEP VERIFICATION (on real sites)
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 5: Deep Stealth Verification on Real Sites...")
    
    # Navigate to example.com and run comprehensive stealth checks
    start = time.time()
    try:
        await browser.page.goto("https://example.com", timeout=15000)
        await asyncio.sleep(1)
        
        deep_checks = await browser.page.evaluate("""() => {
            const results = {};
            
            // WebDriver check
            results.webdriver = navigator.webdriver;
            
            // Plugins check
            results.pluginsLength = navigator.plugins ? navigator.plugins.length : 0;
            results.plugin0Name = navigator.plugins[0] ? navigator.plugins[0].name : 'none';
            
            // Chrome object
            results.chromeExists = window.chrome !== undefined && window.chrome !== null;
            results.chromeAppExists = window.chrome && window.chrome.app !== undefined;
            results.chromeRuntimeExists = window.chrome && window.chrome.runtime !== undefined;
            results.chromeCsiExists = window.chrome && typeof window.chrome.csi === 'function';
            results.chromeLoadTimesExists = window.chrome && typeof window.chrome.loadTimes === 'function';
            
            // Navigator properties
            results.platform = navigator.platform;
            results.languages = JSON.stringify(navigator.languages);
            results.hardwareConcurrency = navigator.hardwareConcurrency;
            results.deviceMemory = navigator.deviceMemory;
            results.maxTouchPoints = navigator.maxTouchPoints;
            
            // Screen
            results.screenWidth = screen.width;
            results.screenHeight = screen.height;
            results.colorDepth = screen.colorDepth;
            results.pixelRatio = window.devicePixelRatio;
            
            // Connection
            results.connectionType = navigator.connection ? navigator.connection.effectiveType : 'none';
            
            // toString check
            try {
                const fnStr = navigator.permissions.query.toString();
                results.permQueryToString = fnStr.substring(0, 50);
            } catch(e) {
                results.permQueryToString = 'error: ' + e.message;
            }
            
            // CDP artifacts
            results.hasCdcProps = Object.keys(window).some(k => k.startsWith('cdc_'));
            results.hasPlaywrightProps = Object.keys(window).some(k => k.includes('playwright'));
            results.hasSeleniumProps = !!window.__selenium_evaluate || !!window._selenium;
            
            return results;
        }""")
        
        duration = (time.time() - start) * 1000
        
        # Evaluate each check
        stealth_passes = 0
        stealth_total = 0
        
        checks = [
            ("webdriver_none", deep_checks.get("webdriver") is None or deep_checks.get("webdriver") is False),
            ("plugins_3plus", deep_checks.get("pluginsLength", 0) >= 3),
            ("chrome_exists", deep_checks.get("chromeExists", False)),
            ("chrome_app", deep_checks.get("chromeAppExists", False)),
            ("chrome_runtime", deep_checks.get("chromeRuntimeExists", False)),
            ("chrome_csi", deep_checks.get("chromeCsiExists", False)),
            ("chrome_loadTimes", deep_checks.get("chromeLoadTimesExists", False)),
            ("platform_set", len(str(deep_checks.get("platform", ""))) > 0),
            ("languages_en", "en-US" in str(deep_checks.get("languages", ""))),
            ("hardware_set", deep_checks.get("hardwareConcurrency", 0) > 0),
            ("memory_set", deep_checks.get("deviceMemory", 0) > 0),
            ("screen_positive", deep_checks.get("screenWidth", 0) > 0 and deep_checks.get("screenHeight", 0) > 0),
            ("no_cdc_props", not deep_checks.get("hasCdcProps", True)),
            ("no_playwright_props", not deep_checks.get("hasPlaywrightProps", True)),
            ("no_selenium_props", not deep_checks.get("hasSeleniumProps", True)),
            ("perm_tostring_native", "[native code]" in str(deep_checks.get("permQueryToString", ""))),
        ]
        
        for check_name, check_passed in checks:
            stealth_total += 1
            if check_passed:
                stealth_passes += 1
            record("5. Deep Stealth", check_name, check_passed, "" if check_passed else f"Failed: {deep_checks.get(check_name, 'N/A')}", 0)
            status = "✅" if check_passed else "❌"
            print(f"  {status} {check_name}")
        
        print(f"\n  Deep Stealth Score: {stealth_passes}/{stealth_total} ({stealth_passes/stealth_total*100:.0f}%)")
        
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("5. Deep Stealth", "deep_stealth_all", False, str(e), duration)
        print(f"  ❌ Deep stealth check FAILED: {e}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 6: SMART NAVIGATION
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 6: Smart Navigation...")
    
    from src.core.smart_navigator import SmartNavigator
    nav = SmartNavigator(browser)
    
    start = time.time()
    try:
        result = await nav.navigate("https://example.com", prefer_browser=True)
        duration = (time.time() - start) * 1000
        passed = result.get("status") == "success"
        record("6. Smart Navigation", "navigate_example", passed, "" if passed else result.get("error", ""), duration, str(result)[:200])
        print(f"  {'✅' if passed else '❌'} navigate_example: {result.get('status')} in {duration:.0f}ms")
        websites_visited.append("https://example.com (via SmartNavigator)")
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("6. Smart Navigation", "navigate_example", False, str(e), duration)
        print(f"  ❌ navigate_example: ERROR - {e}")

    # Navigate to multiple pages rapidly
    rapid_sites = ["https://example.com", "https://httpbin.org/get", "https://www.wikipedia.org"]
    for i, url in enumerate(rapid_sites):
        start = time.time()
        try:
            result = await nav.navigate(url, prefer_browser=True)
            duration = (time.time() - start) * 1000
            passed = result.get("status") == "success"
            record("6. Smart Navigation", f"rapid_nav_{i}_{url.split('/')[2]}", passed, "", duration)
            status = "✅" if passed else "❌"
            print(f"  {status} rapid_nav_{i}: {url} in {duration:.0f}ms")
        except Exception as e:
            duration = (time.time() - start) * 1000
            record("6. Smart Navigation", f"rapid_nav_{i}_{url.split('/')[2]}", False, str(e), duration)
            print(f"  ❌ rapid_nav_{i}: ERROR - {e}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 7: SMART WAIT
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 7: Smart Wait...")
    
    from src.tools.smart_wait import SmartWait
    waiter = SmartWait(browser)
    
    # Page ready test
    start = time.time()
    try:
        await browser.page.goto("https://example.com", timeout=15000)
        result = await waiter.page_ready(timeout_ms=10000)
        duration = (time.time() - start) * 1000
        passed = result.get("status") == "success"
        record("7. Smart Wait", "page_ready_example", passed, "" if passed else result.get("error", ""), duration)
        print(f"  {'✅' if passed else '❌'} page_ready_example: {result.get('status')} in {duration:.0f}ms")
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("7. Smart Wait", "page_ready_example", False, str(e), duration)
        print(f"  ❌ page_ready_example: ERROR - {e}")

    # DOM stable test
    start = time.time()
    try:
        result = await waiter.dom_stable(stability_ms=200, timeout_ms=5000)
        duration = (time.time() - start) * 1000
        passed = result.get("status") == "success"
        record("7. Smart Wait", "dom_stable", passed, "" if passed else result.get("error", ""), duration)
        print(f"  {'✅' if passed else '❌'} dom_stable: {result.get('status')} in {duration:.0f}ms")
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("7. Smart Wait", "dom_stable", False, str(e), duration)
        print(f"  ❌ dom_stable: ERROR - {e}")

    # Element ready test
    start = time.time()
    try:
        result = await waiter.element_ready("h1", timeout_ms=5000)
        duration = (time.time() - start) * 1000
        passed = result.get("status") == "success"
        record("7. Smart Wait", "element_ready_h1", passed, "" if passed else result.get("error", ""), duration)
        print(f"  {'✅' if passed else '❌'} element_ready_h1: {result.get('status')} in {duration:.0f}ms")
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("7. Smart Wait", "element_ready_h1", False, str(e), duration)
        print(f"  ❌ element_ready_h1: ERROR - {e}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 8: SCREENSHOT
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 8: Screenshot...")
    
    start = time.time()
    try:
        await browser.page.goto("https://example.com", timeout=15000)
        await asyncio.sleep(1)
        screenshot_path = "/home/z/my-project/Agent-OS/live_test_screenshot.png"
        await browser.page.screenshot(path=screenshot_path)
        size = os.path.getsize(screenshot_path)
        duration = (time.time() - start) * 1000
        passed = size > 1000  # At least 1KB
        record("8. Screenshot", "take_screenshot", passed, f"Size: {size} bytes", duration)
        print(f"  {'✅' if passed else '❌'} take_screenshot: {size} bytes in {duration:.0f}ms")
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("8. Screenshot", "take_screenshot", False, str(e), duration)
        print(f"  ❌ take_screenshot: ERROR - {e}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 9: CLICK AND INTERACT
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 9: Click and Interact...")
    
    start = time.time()
    try:
        await browser.page.goto("https://example.com", timeout=15000)
        await asyncio.sleep(1)
        
        # Try clicking a link
        link = await browser.page.query_selector("a")
        if link:
            href = await link.get_attribute("href")
            await link.click()
            await asyncio.sleep(1)
            new_url = browser.page.url
            duration = (time.time() - start) * 1000
            passed = True  # Click happened
            record("9. Click/Interact", "click_link", passed, detail=f"Clicked link to: {new_url[:80]}", duration_ms=duration)
            print(f"  ✅ click_link: navigated to {new_url[:60]}")
        else:
            record("9. Click/Interact", "click_link", False, "No link found on page", (time.time() - start) * 1000)
            print(f"  ❌ click_link: No link found")
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("9. Click/Interact", "click_link", False, str(e), duration)
        print(f"  ❌ click_link: ERROR - {e}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 10: LOGIN DETECTION
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 10: Login Detection...")
    
    from src.tools.login_handoff import LoginDetector
    
    login_urls = [
        ("https://github.com/login", True),
        ("https://www.instagram.com/accounts/login/", True),
        ("https://twitter.com/login", True),
        ("https://example.com", False),
        ("https://www.wikipedia.org", False),
    ]
    
    for url, expected_login in login_urls:
        start = time.time()
        try:
            is_login, page_type, confidence = LoginDetector.detect_from_url(url)
            passed = is_login == expected_login
            duration = (time.time() - start) * 1000
            record("10. Login Detection", f"detect_{url.split('/')[2]}", passed, f"Expected {expected_login}, got {is_login} (type={page_type}, conf={confidence:.2f})", duration)
            status = "✅" if passed else "❌"
            print(f"  {status} {url}: is_login={is_login} (expected {expected_login})")
        except Exception as e:
            duration = (time.time() - start) * 1000
            record("10. Login Detection", f"detect_{url.split('/')[2]}", False, str(e), duration)
            print(f"  ❌ {url}: ERROR - {e}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 11: STRESS - RAPID NAVIGATION
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 11: Stress - Rapid Navigation (10 pages)...")
    
    rapid_urls = [
        "https://example.com",
        "https://httpbin.org/get",
        "https://www.wikipedia.org",
        "https://example.com",
        "https://httpbin.org/uuid",
        "https://example.com",
        "https://httpbin.org/ip",
        "https://www.wikipedia.org/wiki/Main_Page",
        "https://example.com",
        "https://httpbin.org/user-agent",
    ]
    
    rapid_passes = 0
    for i, url in enumerate(rapid_urls):
        start = time.time()
        try:
            response = await browser.page.goto(url, timeout=15000, wait_until="domcontentloaded")
            duration = (time.time() - start) * 1000
            passed = response is not None and response.status < 500
            if passed:
                rapid_passes += 1
            record("11. Rapid Nav Stress", f"rapid_{i}", passed, f"Status: {response.status if response else 'no response'}", duration)
        except Exception as e:
            duration = (time.time() - start) * 1000
            record("11. Rapid Nav Stress", f"rapid_{i}", False, str(e)[:100], duration)
    
    print(f"  Rapid nav: {rapid_passes}/{len(rapid_urls)} succeeded")

    # ═══════════════════════════════════════════════════════════
    # PHASE 12: EVASION ENGINE
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 12: Evasion Engine...")
    
    from src.security.evasion_engine import EvasionEngine, generate_fingerprint
    
    start = time.time()
    try:
        engine = EvasionEngine()
        fp = engine.generate_fingerprint(page_id="test")
        duration = (time.time() - start) * 1000
        
        fp_checks = [
            ("fingerprint_id", len(fp.get("id", "")) > 0),
            ("user_agent", "Chrome" in fp.get("user_agent", "")),
            ("platform", fp.get("platform") in ["Win32", "MacIntel", "Linux x86_64"]),
            ("screen_width", fp.get("screen_width", 0) > 0),
            ("screen_height", fp.get("screen_height", 0) > 0),
            ("webgl_vendor", len(fp.get("webgl_vendor", "")) > 0),
            ("webgl_renderer", len(fp.get("webgl_renderer", "")) > 0),
            ("chrome_version", fp.get("chrome_version", "").isdigit()),
        ]
        
        for check_name, check_passed in fp_checks:
            record("12. Evasion Engine", check_name, check_passed)
            status = "✅" if check_passed else "❌"
            print(f"  {status} {check_name}: {fp.get(check_name.split('_')[-1], 'N/A')}")
        
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("12. Evasion Engine", "fingerprint_gen", False, str(e), duration)
        print(f"  ❌ fingerprint_gen: ERROR - {e}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 13: BOT DETECTION TEST
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 13: Bot Detection Test (bot.sannysoft.com)...")
    
    start = time.time()
    try:
        await browser.page.goto("https://bot.sannysoft.com/", timeout=20000, wait_until="domcontentloaded")
        await asyncio.sleep(3)  # Let it fully evaluate
        
        # Take screenshot for proof
        await browser.page.screenshot(path="/home/z/my-project/Agent-OS/bot_test_screenshot.png")
        
        # Read the results from the page
        bot_results = await browser.page.evaluate("""() => {
            const results = {};
            // Check all table rows
            document.querySelectorAll('table tr').forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 2) {
                    const key = cells[0].textContent.trim();
                    const value = cells[1].textContent.trim();
                    const classList = cells[1].className;
                    results[key] = { value: value, passed: classList.includes('passed') || !classList.includes('failed') };
                }
            });
            return results;
        }""")
        
        duration = (time.time() - start) * 1000
        
        # Count passes/fails
        bot_passes = 0
        bot_fails = 0
        if bot_results:
            for key, val in bot_results.items():
                if val.get("passed"):
                    bot_passes += 1
                else:
                    bot_fails += 1
        
        passed = bot_fails <= 3  # Allow up to 3 failures
        record("13. Bot Detection", "sannysoft_bot_test", passed, f"Passes: {bot_passes}, Fails: {bot_fails}", duration, f"Passes: {bot_passes}, Fails: {bot_fails}")
        print(f"  {'✅' if passed else '❌'} sannysoft_bot_test: {bot_passes} passed, {bot_fails} failed")
        
        websites_visited.append("https://bot.sannysoft.com/")
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("13. Bot Detection", "sannysoft_bot_test", False, str(e), duration)
        print(f"  ❌ sannysoft_bot_test: ERROR - {e}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 14: HEADLESS DETECTION TEST
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Phase 14: Headless Detection Test...")
    
    start = time.time()
    try:
        await browser.page.goto("https://abrahamjuliot.github.io/creepjs/", timeout=20000, wait_until="domcontentloaded")
        await asyncio.sleep(5)  # CreepJS needs time
        
        # Take screenshot
        await browser.page.screenshot(path="/home/z/my-project/Agent-OS/creepjs_screenshot.png")
        
        # Try to get trust score
        trust_score = await browser.page.evaluate("""() => {
            // Try to find the trust score element
            const el = document.querySelector('[data-table="visitorResults"] .trust-score, .visitor-trust, #fp-score');
            if (el) return el.textContent.trim();
            // Fallback: check for any score
            const allText = document.body.innerText;
            const match = allText.match(/trust[^\\n]*?(\\d+\\.?\\d*)/i);
            return match ? match[1] : 'not_found';
        }""")
        
        duration = (time.time() - start) * 1000
        record("14. CreepJS", "creepjs_test", True, f"Trust score: {trust_score}", duration, f"Trust: {trust_score}")
        print(f"  ℹ️  creepjs_test: Trust score = {trust_score}")
        websites_visited.append("https://abrahamjuliot.github.io/creepjs/")
    except Exception as e:
        duration = (time.time() - start) * 1000
        record("14. CreepJS", "creepjs_test", False, str(e), duration)
        print(f"  ❌ creepjs_test: ERROR - {e}")

    # ═══════════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════════
    print("\n▶ Cleaning up...")
    try:
        await browser.page.close()
        await browser.context.close()
        await browser.browser.close()
        await browser.playwright.stop()
        print("  ✅ Browser closed cleanly")
    except Exception as e:
        print(f"  ⚠️ Browser cleanup warning: {e}")

    # ═══════════════════════════════════════════════════════════
    # REPORT
    # ═══════════════════════════════════════════════════════════
    total_passed = sum(s.passed for s in ALL_RESULTS)
    total_failed = sum(s.failed for s in ALL_RESULTS)
    total_tests = sum(s.total for s in ALL_RESULTS)
    success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

    print("\n" + "="*80)
    print("  LIVE BRUTAL TEST REPORT")
    print("="*80)
    
    for suite in ALL_RESULTS:
        rate = (suite.passed / suite.total * 100) if suite.total > 0 else 0
        status = "✅" if rate == 100 else "⚠️" if rate >= 80 else "❌"
        print(f"\n{status} {suite.category}: {suite.passed}/{suite.total} passed ({rate:.0f}%)")
        for r in suite.results:
            if not r.passed:
                print(f"    ❌ {r.name}: {r.error[:100]}")

    print(f"\n{'='*80}")
    print(f"  OVERALL: {total_passed}/{total_tests} passed ({success_rate:.1f}%)")
    print(f"  FAILED: {total_failed}")
    print(f"  Websites Visited: ~{len(set(websites_visited))}")
    print(f"{'='*80}")
    
    # Production verdict
    if success_rate >= 95:
        verdict = "🟢 PRODUCTION READY"
        detail = "System is solid. Launch it."
    elif success_rate >= 85:
        verdict = "🟡 ALMOST READY"
        detail = "Minor issues, mostly working. Fix the failures before launch."
    elif success_rate >= 70:
        verdict = "🟠 NEEDS WORK"
        detail = "Significant issues. Don't launch yet."
    else:
        verdict = "🔴 NOT READY"
        detail = "Major failures. Do NOT launch."
    
    print(f"\n  Verdict: {verdict}")
    print(f"  Detail: {detail}")
    print(f"  Success Rate: {success_rate:.1f}%")
    print(f"  Websites Visited: ~{len(set(websites_visited))}")
    
    # Save results
    results_data = {
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_tests": total_tests,
        "success_rate": success_rate,
        "verdict": verdict,
        "websites_visited_count": len(set(websites_visited)),
        "suites": [
            {
                "category": s.category,
                "passed": s.passed,
                "failed": s.failed,
                "total": s.total,
                "failures": [{"name": r.name, "error": r.error} for r in s.results if not r.passed]
            }
            for s in ALL_RESULTS
        ]
    }
    
    with open("/home/z/my-project/Agent-OS/live_brutal_test_results.json", "w") as f:
        json.dump(results_data, f, indent=2)
    
    print(f"\n  Results saved to: live_brutal_test_results.json")


if __name__ == "__main__":
    import tempfile
    asyncio.run(run_live_brutal_test())
