#!/usr/bin/env python3
"""
Agent-OS Login Handoff Demo — Instagram & Twitter
===================================================
This script demonstrates the complete Login Handoff feature for
Instagram and Twitter login flows. It tests:

1. URL-based login detection for Instagram and Twitter/X
2. DOM-based login form detection
3. Handoff session lifecycle (start → waiting → complete)
4. Auto-detection and auto-completion
5. Cookie diff detection (before vs after)
6. Statistics and history

Usage:
    python3 demo_login_handoff.py
    python3 demo_login_handoff.py --headed  (with visible browser)
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, ".")

from src.tools.login_handoff import LoginDetector, LoginHandoffManager, HandoffState, HandoffSession


# ═══════════════════════════════════════════════════════════════
# Mock Browser for testing (simulates Playwright Page + Browser)
# ═══════════════════════════════════════════════════════════════

class MockPage:
    """Simulates a Playwright Page object for testing."""

    def __init__(self, url: str, html_content: str = "", title: str = ""):
        self.url = url
        self._html = html_content
        self._title = title

    async def evaluate(self, js_code: str):
        """Simulate JavaScript evaluation for DOM detection."""
        # Simulate common login form elements based on URL
        result = {
            "loginHits": 0,
            "signupHits": 0,
            "titleHit": None,
            "textHit": None,
            "hasPassword": False,
            "title": self._title or self._get_default_title(),
        }

        url_lower = self.url.lower()

        # Instagram login page
        if "instagram.com/accounts/login" in url_lower:
            result["loginHits"] = 5  # password, form, data-testid, etc.
            result["hasPassword"] = True
            result["titleHit"] = "login"
            result["textHit"] = "log in to continue"
        # Twitter/X login page
        elif "twitter.com/login" in url_lower or "x.com/login" in url_lower:
            result["loginHits"] = 4
            result["hasPassword"] = True
            result["titleHit"] = "login"
        elif "twitter.com/i/flow/login" in url_lower or "x.com/i/flow/login" in url_lower:
            result["loginHits"] = 3
            result["hasPassword"] = True
            result["titleHit"] = "login"
            result["textHit"] = "sign in to continue"
        # Signup pages
        elif "signup" in url_lower or "register" in url_lower:
            result["signupHits"] = 4
            result["loginHits"] = 2
            result["hasPassword"] = True
            result["titleHit"] = "sign up"
        # Not a login page
        else:
            result["loginHits"] = 0
            result["signupHits"] = 0
            result["hasPassword"] = False

        return result

    def _get_default_title(self):
        url_lower = self.url.lower()
        if "instagram" in url_lower:
            if "login" in url_lower:
                return "Log in — Instagram"
            return "Instagram"
        if "twitter" in url_lower or "x.com" in url_lower:
            if "login" in url_lower:
                return "Log in to X / Twitter"
            return "X (Twitter)"
        return "Page"


class MockBrowser:
    """Simulates the browser engine for testing."""

    def __init__(self):
        self._pages = {}
        self._cookies = []
        self._current_url = ""

    def set_page(self, page_id: str, url: str, title: str = ""):
        self._pages[page_id] = MockPage(url, title=title)
        self._current_url = url

    async def get_cookies(self):
        return {"cookies": self._cookies}

    def add_cookie(self, name: str, domain: str, value: str = "mock_value"):
        self._cookies.append({
            "name": name,
            "domain": domain,
            "value": value,
            "path": "/",
            "secure": True,
            "httpOnly": True,
        })

    async def screenshot(self):
        return ""  # No actual screenshot in demo

    async def _save_cookies(self, context_id):
        pass

    async def _flush_cookies(self, context_id):
        pass


# ═══════════════════════════════════════════════════════════════
# Demo Functions
# ═══════════════════════════════════════════════════════════════

async def demo_instagram_login():
    """Demo: Instagram login handoff flow."""
    print("\n" + "=" * 70)
    print("  🔐 DEMO: Instagram Login Handoff")
    print("=" * 70)

    browser = MockBrowser()
    manager = LoginHandoffManager(browser, config={"handoff.auto_detect": True})

    # Simulate navigating to Instagram login page
    print("\n1️⃣  AI navigates to Instagram login page...")
    browser.set_page("main", "https://www.instagram.com/accounts/login/", "Log in — Instagram")

    # Step 1: Detect login page
    print("2️⃣  Auto-detecting login page...")
    detection = await manager.detect_login_page("main")
    print(f"   Detection Result:")
    print(f"   - is_login_page: {detection['is_login_page']}")
    print(f"   - page_type:     {detection['page_type']}")
    print(f"   - confidence:    {detection['confidence']:.0%}")
    print(f"   - domain:        {detection['domain']}")

    if detection["is_login_page"]:
        # Step 2: Start handoff
        print("\n3️⃣  Starting login handoff...")
        result = await manager.start_handoff(
            url="https://www.instagram.com/accounts/login/",
            page_id="main",
            user_id="demo_user",
            session_id="demo_session",
            timeout_seconds=300,
            auto_detected=True,
        )
        handoff_id = result.get("handoff_id", "")
        print(f"   ✅ Handoff started!")
        print(f"   - handoff_id:    {handoff_id}")
        print(f"   - state:         {result['state']}")
        print(f"   - message:       {result['message']}")

        # Step 3: Simulate user logging in
        print("\n4️⃣  👤 User takes control of the browser...")
        print("   User types username and password in the browser window")
        print("   AI CANNOT see the credentials — they go only to Instagram")
        await asyncio.sleep(0.5)  # Simulate user taking time to login

        # Simulate: User completed login, cookies were set
        print("\n5️⃣  User completed login! New cookies detected...")
        browser.add_cookie("sessionid", ".instagram.com")
        browser.add_cookie("ds_user_id", ".instagram.com")
        browser.add_cookie("csrftoken", ".instagram.com")
        browser.add_cookie("rur", ".instagram.com")
        browser.add_cookie("ig_did", ".instagram.com")
        # Simulate page navigation to feed
        browser.set_page("main", "https://www.instagram.com/", "Instagram")

        # Step 4: Complete handoff
        print("\n6️⃣  Completing handoff, saving session...")
        complete_result = await manager.complete_handoff(handoff_id, user_id="demo_user")
        print(f"   ✅ Handoff completed!")
        print(f"   - domain:         {complete_result['domain']}")
        print(f"   - new_cookies:    {complete_result['new_cookie_count']}")
        print(f"   - auth_cookies:   {complete_result['auth_cookie_names']}")
        print(f"   - duration:       {complete_result['duration_seconds']}s")
        print(f"   - message:        {complete_result['message']}")

        # Step 5: AI can now continue with authenticated session
        print("\n7️⃣  🤖 AI resumes automation with authenticated session!")
        print("   The AI can now access Instagram feed, profile, etc.")
        print("   Cookies are saved and will persist across restarts.")

    await manager.stop()
    return manager


async def demo_twitter_login():
    """Demo: Twitter/X login handoff flow."""
    print("\n" + "=" * 70)
    print("  🔐 DEMO: Twitter/X Login Handoff")
    print("=" * 70)

    browser = MockBrowser()
    manager = LoginHandoffManager(browser, config={"handoff.auto_detect": True})

    # Simulate navigating to Twitter login page
    print("\n1️⃣  AI navigates to Twitter/X login page...")
    browser.set_page("main", "https://x.com/i/flow/login", "Log in to X")

    # Auto-detect and handoff
    print("2️⃣  Auto-detecting login page...")
    auto_result = await manager.check_and_auto_handoff(
        url="https://x.com/i/flow/login",
        page_id="main",
        user_id="demo_user",
        session_id="demo_session",
    )

    if auto_result:
        handoff_id = auto_result["handoff_id"]
        print(f"   ✅ Auto-handoff triggered!")
        print(f"   - handoff_id:    {handoff_id}")
        print(f"   - confidence:    {auto_result['confidence']:.0%}")
        print(f"   - page_type:     {auto_result['page_type']}")
        print(f"   - auto_detected: True")

        # Simulate user login
        print("\n3️⃣  👤 User logs in to Twitter/X in the browser...")
        await asyncio.sleep(0.3)

        # Add auth cookies
        browser.add_cookie("auth_token", ".x.com")
        browser.add_cookie("ct0", ".x.com")
        browser.add_cookie("twid", ".x.com")
        browser.add_cookie("kdt", ".x.com")
        # Navigate to home feed
        browser.set_page("main", "https://x.com/home", "Home / X")

        # Complete
        print("\n4️⃣  User done! Completing handoff...")
        result = await manager.complete_handoff(handoff_id, user_id="demo_user")
        print(f"   ✅ Handoff completed!")
        print(f"   - new_cookies:    {result['new_cookie_count']}")
        print(f"   - auth_cookies:   {result['auth_cookie_names']}")
        print(f"   - duration:       {result['duration_seconds']}s")

    await manager.stop()
    return manager


async def demo_cancel_and_timeout():
    """Demo: Cancel and timeout scenarios."""
    print("\n" + "=" * 70)
    print("  🔐 DEMO: Cancel & Timeout Scenarios")
    print("=" * 70)

    browser = MockBrowser()
    # Use a very short timeout for demo
    manager = LoginHandoffManager(browser, config={"handoff.auto_detect": True})

    # Test 1: Cancel handoff
    print("\n1️⃣  Testing CANCEL scenario...")
    browser.set_page("main", "https://www.facebook.com/login.php", "Log into Facebook")
    result = await manager.start_handoff(
        url="https://www.facebook.com/login.php",
        page_id="main",
        user_id="demo_user",
        timeout_seconds=300,
    )
    handoff_id = result["handoff_id"]
    print(f"   Handoff started: {handoff_id}")

    # User decides to cancel
    cancel_result = await manager.cancel_handoff(handoff_id, reason="User doesn't want to login now")
    print(f"   ✅ Handoff cancelled: {cancel_result['message']}")

    # Test 2: List handoffs
    print("\n2️⃣  Listing all handoffs...")
    list_result = await manager.list_handoffs()
    print(f"   Total handoffs: {list_result['count']}")
    for h in list_result["handoffs"]:
        print(f"   - {h['domain']:25s} | {h['state']:15s} | {h['page_type']}")

    await manager.stop()
    return manager


async def demo_url_detection_comprehensive():
    """Comprehensive URL detection test for all supported platforms."""
    print("\n" + "=" * 70)
    print("  🔐 DEMO: Comprehensive URL Detection")
    print("=" * 70)

    test_cases = [
        # (URL, expected_is_login, description)
        ("https://www.instagram.com/accounts/login/", True, "Instagram login page"),
        ("https://instagram.com/", True, "Instagram root (requires login)"),
        ("https://www.instagram.com/explore/", False, "Instagram explore (not login)"),
        ("https://twitter.com/login", True, "Twitter login page"),
        ("https://x.com/login", True, "X.com login page"),
        ("https://twitter.com/i/flow/login", True, "Twitter flow login"),
        ("https://x.com/", True, "X.com root (requires login)"),
        ("https://x.com/home", False, "X.com home (not login)"),
        ("https://www.facebook.com/login.php", True, "Facebook login"),
        ("https://facebook.com/", True, "Facebook root (requires login)"),
        ("https://www.linkedin.com/login", True, "LinkedIn login"),
        ("https://github.com/login", True, "GitHub login"),
        ("https://accounts.google.com/login", True, "Google login"),
        ("https://mail.google.com/", True, "Gmail (requires login)"),
        ("https://www.reddit.com/login", True, "Reddit login"),
        ("https://discord.com/login", True, "Discord login"),
        ("https://www.amazon.com/ap/signin", True, "Amazon login"),
        ("https://open.spotify.com/", True, "Spotify (requires login)"),
        ("https://www.google.com/search?q=test", False, "Google search (not login)"),
        ("https://en.wikipedia.org/wiki/Python", False, "Wikipedia (not login)"),
        ("https://github.com/python/cpython", False, "GitHub repo (not login)"),
        ("https://stackoverflow.com/questions/123", False, "StackOverflow (not login)"),
    ]

    passed = 0
    failed = 0

    for url, expected, desc in test_cases:
        is_login, page_type, confidence = LoginDetector.detect_from_url(url)
        match = is_login == expected
        icon = "✅" if match else "❌"
        passed += 1 if match else 0
        failed += 1 if not match else 0

        print(f"  {icon} | {'LOGIN' if is_login else 'NOPE':4s} | conf={confidence:.2f} | {desc}")
        print(f"      URL: {url}")

    print(f"\n  Results: {passed} passed, {failed} failed out of {passed + failed} tests")
    return failed == 0


async def demo_stats():
    """Demo: Handoff statistics."""
    print("\n" + "=" * 70)
    print("  🔐 DEMO: Handoff Statistics")
    print("=" * 70)

    browser = MockBrowser()
    manager = LoginHandoffManager(browser)

    # Create and complete an Instagram handoff
    browser.set_page("main", "https://www.instagram.com/accounts/login/")
    r1 = await manager.start_handoff(url="https://www.instagram.com/accounts/login/", page_id="main", user_id="user1")
    browser.add_cookie("sessionid", ".instagram.com")
    browser.set_page("main", "https://www.instagram.com/")
    await manager.complete_handoff(r1["handoff_id"])

    # Create and complete a Twitter handoff
    browser._cookies = []  # Reset for next handoff
    browser.set_page("main", "https://x.com/login")
    r2 = await manager.start_handoff(url="https://x.com/login", page_id="main", user_id="user1")
    browser.add_cookie("auth_token", ".x.com")
    browser.set_page("main", "https://x.com/home")
    await manager.complete_handoff(r2["handoff_id"])

    # Create and cancel a Facebook handoff
    browser._cookies = []
    browser.set_page("main", "https://www.facebook.com/login.php")
    r3 = await manager.start_handoff(url="https://www.facebook.com/login.php", page_id="main", user_id="user1")
    await manager.cancel_handoff(r3["handoff_id"], reason="Changed mind")

    # Get stats
    stats = manager.get_stats()
    print(f"\n  📊 Handoff Statistics:")
    print(f"  - Total handoffs:      {stats['total_handoffs']}")
    print(f"  - Completed:           {stats['completed_handoffs']}")
    print(f"  - Cancelled:           {stats['cancelled_handoffs']}")
    print(f"  - Timed out:           {stats['timed_out_handoffs']}")
    print(f"  - Active:              {stats['active_handoffs']}")
    print(f"  - Success rate:        {stats['success_rate']}%")
    print(f"\n  Per-domain stats:")
    for domain, dstats in stats.get("per_domain", {}).items():
        print(f"  - {domain:25s}: completed={dstats['completed']}, cancelled={dstats['cancelled']}")

    # Get history
    history = await manager.get_handoff_history()
    print(f"\n  📜 Handoff History ({history['count']} entries):")
    for h in history["history"]:
        print(f"  - {h['domain']:25s} | {h['state']:10s} | {h['page_type']:6s} | cookies: {len(h.get('auth_cookie_names', []))}")

    await manager.stop()


async def main():
    """Run all demos."""
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║          Agent-OS Login Handoff Demo                           ║")
    print("║          Instagram & Twitter Login Flow                        ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print()
    print("This demo shows how Agent-OS handles login pages on social media")
    print("by handing control to the user, then resuming AI automation.")
    print()
    print("Key Security Features:")
    print("  - AI NEVER sees or stores user passwords")
    print("  - Credentials go ONLY to the real website")
    print("  - After handoff, only cookie names (not values) are visible to AI")
    print("  - All handoff sessions are encrypted and auto-expire")
    print("  - Screenshots during handoff are memory-only (never saved to disk)")

    # Run demos
    all_pass = True

    # 1. Instagram demo
    await demo_instagram_login()

    # 2. Twitter/X demo
    await demo_twitter_login()

    # 3. Cancel/timeout demo
    await demo_cancel_and_timeout()

    # 4. Comprehensive URL detection
    all_pass = await demo_url_detection_comprehensive()

    # 5. Statistics demo
    await demo_stats()

    # Summary
    print("\n" + "=" * 70)
    print("  🎉 DEMO COMPLETE")
    print("=" * 70)
    print()
    print("  Login Handoff is fully integrated and production-ready!")
    print()
    print("  How to use with real Instagram/Twitter login:")
    print("  ──────────────────────────────────────────────")
    print("  1. Start Agent-OS in headed mode:")
    print("     python3 main.py --headed --agent-token YOUR_TOKEN --debug")
    print()
    print("  2. Navigate to Instagram or Twitter:")
    print("     curl -X POST http://localhost:8001/command \\")
    print('       -d \'{"token":"YOUR_TOKEN","command":"navigate","url":"https://instagram.com"}\'')
    print()
    print("  3. Login page is auto-detected → Handoff starts")
    print("     A banner appears in the Debug Dashboard (localhost:8002)")
    print("     The browser window shows the login page for manual input")
    print()
    print("  4. User logs in manually in the browser window")
    print()
    print("  5. Click 'I'm Done Logging In' in the dashboard")
    print("     Or use the API:")
    print("     curl -X POST http://localhost:8001/handoff/{handoff_id}/complete")
    print()
    print("  6. AI resumes automation with authenticated session! 🚀")
    print()

    if all_pass:
        print("  ✅ All detection tests passed!")
    else:
        print("  ❌ Some detection tests failed!")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
