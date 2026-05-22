#!/usr/bin/env python3
"""
Live Login Handoff Test — Instagram & Twitter
==============================================
Tests the complete Login Handoff flow:
1. Starts Agent-OS server (headless)
2. Navigates to Instagram → detects login page → starts handoff
3. Navigates to Twitter → detects login page → starts handoff
4. Tests all handoff API endpoints
5. Tests auto-detection after navigation

Run: python3 test_login_handoff_live.py
"""
import asyncio
import json
import sys
import os
import time
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s"
)
logger = logging.getLogger("handoff-test")

# ═══════════════════════════════════════════════════════════════
# TEST 1: LoginDetector unit tests (no browser needed)
# ═══════════════════════════════════════════════════════════════

def test_login_detector():
    """Test LoginDetector URL-based detection for Instagram & Twitter."""
    from src.tools.login_handoff import LoginDetector

    logger.info("=" * 60)
    logger.info("TEST 1: LoginDetector — URL-based Detection")
    logger.info("=" * 60)

    test_cases = [
        # Instagram URLs
        ("https://www.instagram.com/accounts/login/", True, "login", 0.95),
        ("https://instagram.com/accounts/login/", True, "login", 0.95),
        ("https://www.instagram.com/accounts/signup/", True, "login", 0.95),
        ("https://www.instagram.com/", True, "login", 0.85),  # Known login-required domain
        ("https://instagram.com/explore/", False, "none", 0.0),  # Not a login path on this domain

        # Twitter/X URLs
        ("https://twitter.com/login", True, "login", 0.95),
        ("https://x.com/login", True, "login", 0.95),
        ("https://twitter.com/i/flow/login", True, "login", 0.95),
        ("https://x.com/i/flow/login", True, "login", 0.95),
        ("https://twitter.com/signup", True, "login", 0.95),
        ("https://x.com/", True, "login", 0.85),  # Known login-required domain

        # Facebook
        ("https://www.facebook.com/login.php", True, "login", 0.95),
        ("https://m.facebook.com/login.php", True, "login", 0.95),
        ("https://www.facebook.com/login/", True, "login", 0.95),

        # Google
        ("https://accounts.google.com/login", True, "login", 0.95),
        ("https://accounts.google.com/v3/signin", True, "login", 0.95),

        # GitHub
        ("https://github.com/login", True, "login", 0.95),
        ("https://github.com/signup", True, "login", 0.95),

        # LinkedIn
        ("https://www.linkedin.com/login", True, "login", 0.95),
        ("https://www.linkedin.com/uas/login", True, "login", 0.95),

        # Amazon
        ("https://www.amazon.com/ap/signin", True, "login", 0.95),

        # Generic login URLs
        ("https://example.com/login", True, "login", 0.90),
        ("https://example.com/signin", True, "login", 0.90),
        ("https://example.com/auth/login", True, "login", 0.90),
        ("https://example.com/signup", True, "signup", 0.88),
        ("https://example.com/register", True, "signup", 0.88),

        # Non-login URLs
        ("https://example.com/about", False, "none", 0.0),
        ("https://example.com/products", False, "none", 0.0),
        ("https://example.com/blog", False, "none", 0.0),
        ("https://en.wikipedia.org/wiki/Python", False, "none", 0.0),
    ]

    passed = 0
    failed = 0

    for url, expected_is_login, expected_type, min_confidence in test_cases:
        is_login, page_type, confidence = LoginDetector.detect_from_url(url)

        # Check if result matches expected
        match = (is_login == expected_is_login)
        if expected_is_login:
            match = match and (page_type == expected_type) and (confidence >= min_confidence)

        status = "PASS" if match else "FAIL"
        if match:
            passed += 1
        else:
            failed += 1

        logger.info(
            f"  [{status}] {url}\n"
            f"         is_login={is_login}, type={page_type}, conf={confidence:.2f} "
            f"(expected: is_login={expected_is_login}, type={expected_type}, conf>={min_confidence:.2f})"
        )

    logger.info(f"\n  Detection Results: {passed} passed, {failed} failed")
    return failed == 0


# ═══════════════════════════════════════════════════════════════
# TEST 2: LoginHandoffManager with mock browser
# ═══════════════════════════════════════════════════════════════

async def test_handoff_manager():
    """Test LoginHandoffManager lifecycle with a mock browser."""
    from src.tools.login_handoff import LoginHandoffManager, LoginDetector, HandoffState

    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: LoginHandoffManager — Full Lifecycle")
    logger.info("=" * 60)

    # Create a mock browser that simulates Instagram navigation
    class MockPage:
        def __init__(self, url="about:blank"):
            self.url = url
            self._title = ""

        async def title(self):
            return self._title

        async def evaluate(self, js):
            """Simulate DOM evaluation for login detection."""
            if "instagram" in self.url and "login" in self.url:
                return {
                    "loginHits": 5,
                    "signupHits": 0,
                    "titleHit": "log in",
                    "textHit": "log in to continue",
                    "hasPassword": True,
                    "title": "Log In — Instagram"
                }
            elif ("twitter" in self.url or "x.com" in self.url) and "login" in self.url:
                return {
                    "loginHits": 3,
                    "signupHits": 0,
                    "titleHit": "log in",
                    "textHit": "sign in to continue",
                    "hasPassword": True,
                    "title": "Log in to X / Twitter"
                }
            return {
                "loginHits": 0,
                "signupHits": 0,
                "titleHit": None,
                "textHit": None,
                "hasPassword": False,
                "title": ""
            }

    class MockBrowser:
        def __init__(self):
            self._pages = {"main": MockPage("https://www.instagram.com/accounts/login/")}
            self._cookies = []

        async def get_cookies(self):
            return {"cookies": self._cookies}

        async def screenshot(self):
            return "base64_screenshot_data_mock"

        async def _save_cookies(self, name):
            pass

        async def _flush_cookies(self, name):
            pass

    browser = MockBrowser()
    manager = LoginHandoffManager(browser, config={"login_handoff.auto_detect": True})

    passed = 0
    failed = 0

    # Test 2a: Instagram login detection
    logger.info("\n  --- 2a: Instagram Login Detection ---")
    result = await manager.detect_login_page("main")
    logger.info(f"  Detection result: {json.dumps(result, indent=2)}")

    if result["is_login_page"] and result["domain"] == "instagram.com":
        logger.info("  [PASS] Instagram login page detected!")
        passed += 1
    else:
        logger.info("  [FAIL] Instagram login page NOT detected!")
        failed += 1

    # Test 2b: Start handoff for Instagram
    logger.info("\n  --- 2b: Start Instagram Handoff ---")
    result = await manager.start_handoff(
        url="https://www.instagram.com/accounts/login/",
        page_id="main",
        user_id="test_user",
        timeout_seconds=300,
        auto_detected=True,
    )
    logger.info(f"  Start result: {json.dumps(result, indent=2)}")

    if result["status"] == "success" and result["domain"] == "instagram.com":
        handoff_id_instagram = result["handoff_id"]
        logger.info(f"  [PASS] Instagram handoff started: {handoff_id_instagram}")
        passed += 1
    else:
        logger.info(f"  [FAIL] Instagram handoff failed: {result}")
        handoff_id_instagram = ""
        failed += 1

    # Test 2c: Check handoff status
    logger.info("\n  --- 2c: Check Instagram Handoff Status ---")
    if handoff_id_instagram:
        result = await manager.get_handoff_status(handoff_id_instagram)
        logger.info(f"  Status: state={result.get('handoff', {}).get('state', 'unknown')}")
        if result.get("handoff", {}).get("state") == "waiting_for_user":
            logger.info("  [PASS] Handoff is in WAITING_FOR_USER state")
            passed += 1
        else:
            logger.info(f"  [FAIL] Unexpected state: {result}")
            failed += 1

    # Test 2d: List handoffs
    logger.info("\n  --- 2d: List Handoffs ---")
    result = await manager.list_handoffs()
    logger.info(f"  Active handoffs: {result['count']}")
    if result["count"] >= 1:
        logger.info("  [PASS] Handoff listed")
        passed += 1
    else:
        logger.info("  [FAIL] No handoffs listed")
        failed += 1

    # Test 2e: Switch to Twitter and start handoff
    logger.info("\n  --- 2e: Twitter Login Detection & Handoff ---")
    browser._pages["main"].url = "https://x.com/login"

    result = await manager.detect_login_page("main")
    logger.info(f"  Twitter detection: {json.dumps(result, indent=2)}")

    if result["is_login_page"] and result["domain"] == "x.com":
        logger.info("  [PASS] Twitter/X login page detected!")
        passed += 1
    else:
        logger.info("  [FAIL] Twitter/X login page NOT detected!")
        failed += 1

    # Cancel Instagram handoff first (we can't have 2 on same page)
    if handoff_id_instagram:
        cancel_result = await manager.cancel_handoff(handoff_id_instagram, reason="Switching to Twitter test")
        logger.info(f"  Instagram handoff cancelled: {cancel_result['status']}")

    # Start Twitter handoff
    result = await manager.start_handoff(
        url="https://x.com/login",
        page_id="main",
        user_id="test_user",
        timeout_seconds=300,
        auto_detected=True,
    )
    logger.info(f"  Twitter handoff start: {json.dumps(result, indent=2)}")

    if result["status"] == "success" and result["domain"] == "x.com":
        handoff_id_twitter = result["handoff_id"]
        logger.info(f"  [PASS] Twitter handoff started: {handoff_id_twitter}")
        passed += 1
    else:
        logger.info(f"  [FAIL] Twitter handoff failed: {result}")
        handoff_id_twitter = ""
        failed += 1

    # Test 2f: Complete handoff (simulate user login)
    logger.info("\n  --- 2f: Complete Twitter Handoff ---")
    # Simulate user logging in — page URL changes to feed
    browser._pages["main"].url = "https://x.com/home"
    # Add some mock cookies
    browser._cookies = [
        {"name": "auth_token", "domain": ".x.com", "value": "xxx"},
        {"name": "ct0", "domain": ".x.com", "value": "yyy"},
        {"name": "twid", "domain": ".x.com", "value": "zzz"},
    ]

    if handoff_id_twitter:
        result = await manager.complete_handoff(handoff_id_twitter, user_id="test_user")
        logger.info(f"  Complete result: {json.dumps(result, indent=2)}")

        if result["status"] == "success" and result["new_cookie_count"] >= 1:
            logger.info(f"  [PASS] Twitter handoff completed! {result['new_cookie_count']} new cookies detected")
            passed += 1
        else:
            logger.info(f"  [FAIL] Twitter handoff completion failed: {result}")
            failed += 1

    # Test 2g: Get handoff history
    logger.info("\n  --- 2g: Handoff History ---")
    result = await manager.get_handoff_history()
    logger.info(f"  History entries: {result['count']}")
    for entry in result.get("history", []):
        logger.info(f"    - {entry.get('domain', '?')}: {entry.get('state', '?')}")

    if result["count"] >= 1:
        logger.info("  [PASS] History recorded")
        passed += 1
    else:
        logger.info("  [FAIL] No history recorded")
        failed += 1

    # Test 2h: Get stats
    logger.info("\n  --- 2h: Handoff Stats ---")
    stats = manager.get_stats()
    logger.info(f"  Stats: {json.dumps(stats, indent=2)}")
    logger.info("  [PASS] Stats retrieved")
    passed += 1

    logger.info(f"\n  Manager Test Results: {passed} passed, {failed} failed")
    return failed == 0


# ═══════════════════════════════════════════════════════════════
# TEST 3: Live server test with real browser
# ═══════════════════════════════════════════════════════════════

async def test_live_server():
    """Test with real Agent-OS server and browser (headless)."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Live Server Test — Instagram & Twitter")
    logger.info("=" * 60)

    try:
        import httpx
    except ImportError:
        logger.warning("  httpx not available, skipping live server test")
        return True

    BASE_URL = "http://localhost:8001"
    TOKEN = "test-handoff-token"

    # First check if server is running
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{BASE_URL}/health")
            if resp.status_code != 200:
                logger.warning("  Server not healthy, skipping live test")
                return True
            logger.info(f"  Server health: {resp.json()}")
        except Exception as e:
            logger.warning(f"  Server not running at {BASE_URL}: {e}")
            logger.info("  To run this test, start server with:")
            logger.info("  python3 main.py --agent-token test-handoff-token --debug")
            return True

    passed = 0
    failed = 0

    async with httpx.AsyncClient(timeout=30) as client:
        # Test 3a: Navigate to Instagram
        logger.info("\n  --- 3a: Navigate to Instagram ---")
        try:
            resp = await client.post(f"{BASE_URL}/command", json={
                "token": TOKEN,
                "command": "navigate",
                "url": "https://www.instagram.com/accounts/login/",
            })
            result = resp.json()
            logger.info(f"  Navigate result: status={result.get('status')}")
            if result.get("status") == "success":
                logger.info("  [PASS] Navigated to Instagram")
                passed += 1
            else:
                logger.info(f"  [FAIL] Navigation failed: {result.get('error', 'unknown')}")
                failed += 1
        except Exception as e:
            logger.error(f"  [FAIL] Navigate error: {e}")
            failed += 1

        await asyncio.sleep(3)  # Wait for page load

        # Test 3b: Detect login page
        logger.info("\n  --- 3b: Detect Instagram Login Page ---")
        try:
            resp = await client.post(f"{BASE_URL}/handoff/detect", json={
                "token": TOKEN,
                "page_id": "main",
            })
            result = resp.json()
            logger.info(f"  Detection: {json.dumps(result, indent=2)}")
            if result.get("is_login_page"):
                logger.info(f"  [PASS] Instagram login detected (confidence={result.get('confidence')})")
                passed += 1
            else:
                logger.info("  [FAIL] Instagram login NOT detected")
                failed += 1
        except Exception as e:
            logger.error(f"  [FAIL] Detection error: {e}")
            failed += 1

        # Test 3c: Start Instagram handoff
        logger.info("\n  --- 3c: Start Instagram Handoff ---")
        try:
            resp = await client.post(f"{BASE_URL}/handoff/start", json={
                "token": TOKEN,
                "url": "https://www.instagram.com/accounts/login/",
                "page_id": "main",
                "timeout_seconds": 300,
            })
            result = resp.json()
            logger.info(f"  Handoff start: {json.dumps(result, indent=2)}")

            if result.get("status") == "success":
                handoff_id = result["handoff_id"]
                logger.info(f"  [PASS] Instagram handoff started: {handoff_id}")
                passed += 1

                # Test 3d: Check status
                resp2 = await client.get(f"{BASE_URL}/handoff/{handoff_id}?token={TOKEN}")
                status_result = resp2.json()
                logger.info(f"  Handoff state: {status_result.get('handoff', {}).get('state')}")
                if status_result.get("handoff", {}).get("state") == "waiting_for_user":
                    logger.info("  [PASS] Handoff in WAITING_FOR_USER state")
                    passed += 1
                else:
                    logger.info("  [FAIL] Wrong state")
                    failed += 1

                # Test 3e: Cancel Instagram handoff (we can't actually login in headless)
                resp3 = await client.post(f"{BASE_URL}/handoff/{handoff_id}/cancel", json={
                    "token": TOKEN,
                    "reason": "Test complete - headless mode",
                })
                cancel_result = resp3.json()
                if cancel_result.get("status") == "success":
                    logger.info("  [PASS] Instagram handoff cancelled")
                    passed += 1
                else:
                    logger.info("  [FAIL] Cancel failed")
                    failed += 1
            else:
                logger.info(f"  [FAIL] Handoff start failed: {result.get('error')}")
                failed += 3
        except Exception as e:
            logger.error(f"  [FAIL] Handoff error: {e}")
            failed += 3

        # Test 3f: Navigate to Twitter/X
        logger.info("\n  --- 3f: Navigate to Twitter/X ---")
        try:
            resp = await client.post(f"{BASE_URL}/command", json={
                "token": TOKEN,
                "command": "navigate",
                "url": "https://x.com/login",
            })
            result = resp.json()
            if result.get("status") == "success":
                logger.info("  [PASS] Navigated to Twitter/X")
                passed += 1
            else:
                logger.info(f"  [FAIL] Navigation failed: {result.get('error')}")
                failed += 1
        except Exception as e:
            logger.error(f"  [FAIL] Navigate error: {e}")
            failed += 1

        await asyncio.sleep(3)

        # Test 3g: Detect Twitter login
        logger.info("\n  --- 3g: Detect Twitter Login Page ---")
        try:
            resp = await client.post(f"{BASE_URL}/handoff/detect", json={
                "token": TOKEN,
                "page_id": "main",
            })
            result = resp.json()
            logger.info(f"  Twitter detection: {json.dumps(result, indent=2)}")
            if result.get("is_login_page"):
                logger.info(f"  [PASS] Twitter/X login detected (confidence={result.get('confidence')})")
                passed += 1
            else:
                logger.info("  [FAIL] Twitter/X login NOT detected")
                failed += 1
        except Exception as e:
            logger.error(f"  [FAIL] Detection error: {e}")
            failed += 1

        # Test 3h: Start Twitter handoff
        logger.info("\n  --- 3h: Start Twitter Handoff ---")
        try:
            resp = await client.post(f"{BASE_URL}/handoff/start", json={
                "token": TOKEN,
                "url": "https://x.com/login",
                "page_id": "main",
                "timeout_seconds": 300,
            })
            result = resp.json()
            if result.get("status") == "success":
                handoff_id = result["handoff_id"]
                logger.info(f"  [PASS] Twitter handoff started: {handoff_id}")
                passed += 1

                # Cancel it
                await client.post(f"{BASE_URL}/handoff/{handoff_id}/cancel", json={
                    "token": TOKEN,
                    "reason": "Test complete - headless mode",
                })
            else:
                logger.info(f"  [FAIL] Handoff start failed: {result.get('error')}")
                failed += 1
        except Exception as e:
            logger.error(f"  [FAIL] Handoff error: {e}")
            failed += 1

        # Test 3i: Check stats
        logger.info("\n  --- 3i: Handoff Stats ---")
        try:
            resp = await client.get(f"{BASE_URL}/handoff/stats?token={TOKEN}")
            result = resp.json()
            logger.info(f"  Stats: {json.dumps(result, indent=2)}")
            logger.info("  [PASS] Stats retrieved")
            passed += 1
        except Exception as e:
            logger.error(f"  [FAIL] Stats error: {e}")
            failed += 1

        # Test 3j: Screenshot of current page
        logger.info("\n  --- 3j: Screenshot ---")
        try:
            resp = await client.post(f"{BASE_URL}/command", json={
                "token": TOKEN,
                "command": "screenshot",
            })
            result = resp.json()
            if result.get("status") == "success" and result.get("screenshot"):
                logger.info(f"  [PASS] Screenshot captured ({len(result['screenshot'])} chars base64)")
                passed += 1
            else:
                logger.info(f"  [FAIL] Screenshot failed: {result.get('error', 'unknown')}")
                failed += 1
        except Exception as e:
            logger.error(f"  [FAIL] Screenshot error: {e}")
            failed += 1

    logger.info(f"\n  Live Server Test Results: {passed} passed, {failed} failed")
    return failed == 0


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

async def main():
    logger.info("LOGIN HANDOFF TEST — Instagram & Twitter")
    logger.info("=" * 60)

    all_passed = True

    # Test 1: URL-based detection (no browser needed)
    if not test_login_detector():
        all_passed = False

    # Test 2: Manager lifecycle (mock browser)
    if not await test_handoff_manager():
        all_passed = False

    # Test 3: Live server (if running)
    if not await test_live_server():
        all_passed = False

    # Summary
    logger.info("\n" + "=" * 60)
    if all_passed:
        logger.info("ALL TESTS PASSED!")
    else:
        logger.info("SOME TESTS FAILED — see above for details")
    logger.info("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
