"""
Agent-OS Login Handoff — Comprehensive Stress Test
====================================================
Tests the login page detection, handoff state machine, REST API,
WebSocket notifications, auto-detection integration, and security.
"""
import asyncio
import json
import sys
import time
import unittest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/z/my-project/Agent-OS")

from src.tools.login_handoff import (
    HandoffState,
    HandoffSession,
    LoginDetector,
    LoginHandoffManager,
)


# ═══════════════════════════════════════════════════════════════
# Mock Browser for Testing
# ═══════════════════════════════════════════════════════════════

class MockPage:
    """Mock Playwright Page for testing."""

    def __init__(self, url: str = "https://example.com", dom_result: dict = None):
        self.url = url
        self._dom_result = dom_result or {
            "loginHits": 0,
            "signupHits": 0,
            "titleHit": None,
            "textHit": None,
            "hasPassword": False,
            "title": "Example Page",
        }

    async def evaluate(self, script: str):
        return self._dom_result


class MockBrowser:
    """Mock AgentBrowser for testing."""

    def __init__(self, pages: Dict[str, MockPage] = None):
        self._pages: Dict[str, MockPage] = pages or {"main": MockPage()}
        self._cookies = {"cookies": []}
        self._screenshot_data = "base64_screenshot_data"

    async def get_cookies(self):
        return self._cookies

    async def screenshot(self, full_page=False):
        return self._screenshot_data

    async def _save_cookies(self, profile="default"):
        pass

    async def _flush_cookies(self, profile="default"):
        pass


# ═══════════════════════════════════════════════════════════════
# Test: Login Page Detection (URL-based)
# ═══════════════════════════════════════════════════════════════

class TestLoginDetectorURL(unittest.TestCase):
    """Test URL-based login page detection."""

    def test_instagram_login_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://www.instagram.com/accounts/login/"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")
        self.assertGreater(confidence, 0.90)

    def test_twitter_login_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://x.com/login"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")
        self.assertGreater(confidence, 0.90)

    def test_facebook_login_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://www.facebook.com/login.php"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")
        self.assertGreater(confidence, 0.90)

    def test_github_login_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://github.com/login"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")
        self.assertGreater(confidence, 0.90)

    def test_linkedin_login_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://www.linkedin.com/login"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")
        self.assertGreater(confidence, 0.90)

    def test_google_accounts_login_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://accounts.google.com/v3/signin"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")
        self.assertGreater(confidence, 0.85)

    def test_amazon_signin_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://www.amazon.com/ap/signin"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")
        self.assertGreater(confidence, 0.90)

    def test_signup_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://example.com/signup"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "signup")
        self.assertGreater(confidence, 0.85)

    def test_register_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://example.com/register"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "signup")
        self.assertGreater(confidence, 0.85)

    def test_normal_page_no_detection(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://example.com/about"
        )
        self.assertFalse(is_login)
        self.assertEqual(page_type, "none")

    def test_wikipedia_no_detection(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://en.wikipedia.org/wiki/Python"
        )
        self.assertFalse(is_login)

    def test_reddit_login_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://www.reddit.com/login"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")

    def test_slack_login_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://slack.com/login"
        )
        self.assertTrue(is_login)

    def test_microsoft_login_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://login.microsoftonline.com/common/login"
        )
        self.assertTrue(is_login)

    def test_empty_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url("")
        self.assertFalse(is_login)

    def test_domain_only_instagram(self):
        # Instagram root should be detected (it's in LOGIN_REQUIRED_DOMAINS)
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://www.instagram.com/"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")

    def test_domain_only_twitter(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://x.com/"
        )
        self.assertTrue(is_login)

    def test_spotify_login_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://open.spotify.com/login"
        )
        # Should at least detect via URL path pattern
        self.assertTrue(is_login)


# ═══════════════════════════════════════════════════════════════
# Test: Login Page Detection (DOM-based)
# ═══════════════════════════════════════════════════════════════

class TestLoginDetectorDOM(unittest.TestCase):
    """Test DOM-based login page detection."""

    def test_password_field_detected(self):
        page = MockPage(dom_result={
            "loginHits": 1,  # input[type="password"]
            "signupHits": 0,
            "titleHit": None,
            "textHit": None,
            "hasPassword": True,
            "title": "Welcome",
        })
        result = asyncio.get_event_loop().run_until_complete(
            LoginDetector.detect_from_dom(page)
        )
        is_login, page_type, confidence = result
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")
        self.assertGreaterEqual(confidence, 0.35)

    def test_login_title_detected(self):
        page = MockPage(dom_result={
            "loginHits": 0,
            "signupHits": 0,
            "titleHit": "log in",
            "textHit": None,
            "hasPassword": True,
            "title": "Log In - Example App",
        })
        result = asyncio.get_event_loop().run_until_complete(
            LoginDetector.detect_from_dom(page)
        )
        is_login, page_type, confidence = result
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")

    def test_signup_title_detected(self):
        page = MockPage(dom_result={
            "loginHits": 0,
            "signupHits": 2,
            "titleHit": "sign up",
            "textHit": None,
            "hasPassword": True,
            "title": "Sign Up - Example App",
        })
        result = asyncio.get_event_loop().run_until_complete(
            LoginDetector.detect_from_dom(page)
        )
        is_login, page_type, confidence = result
        self.assertTrue(is_login)
        self.assertEqual(page_type, "signup")

    def test_login_required_text_detected(self):
        page = MockPage(dom_result={
            "loginHits": 0,
            "signupHits": 0,
            "titleHit": None,
            "textHit": "log in to continue",
            "hasPassword": True,
            "title": "Access Required",
        })
        result = asyncio.get_event_loop().run_until_complete(
            LoginDetector.detect_from_dom(page)
        )
        is_login, page_type, confidence = result
        self.assertTrue(is_login)

    def test_normal_page_not_detected(self):
        page = MockPage(dom_result={
            "loginHits": 0,
            "signupHits": 0,
            "titleHit": None,
            "textHit": None,
            "hasPassword": False,
            "title": "Welcome to Example",
        })
        result = asyncio.get_event_loop().run_until_complete(
            LoginDetector.detect_from_dom(page)
        )
        is_login, page_type, confidence = result
        self.assertFalse(is_login)

    def test_none_page(self):
        result = asyncio.get_event_loop().run_until_complete(
            LoginDetector.detect_from_dom(None)
        )
        is_login, page_type, confidence = result
        self.assertFalse(is_login)

    def test_evaluate_exception_handled(self):
        page = MockPage()
        page.evaluate = AsyncMock(side_effect=Exception("Page crashed"))
        result = asyncio.get_event_loop().run_until_complete(
            LoginDetector.detect_from_dom(page)
        )
        is_login, page_type, confidence = result
        self.assertFalse(is_login)


# ═══════════════════════════════════════════════════════════════
# Test: Combined Detection
# ═══════════════════════════════════════════════════════════════

class TestLoginDetectorCombined(unittest.TestCase):
    """Test combined URL + DOM detection."""

    def test_url_high_confidence_short_circuits(self):
        # URL alone gives high confidence, no need for DOM
        page = MockPage(url="https://www.instagram.com/accounts/login/")
        result = asyncio.get_event_loop().run_until_complete(
            LoginDetector.detect(page, "https://www.instagram.com/accounts/login/")
        )
        is_login, page_type, confidence = result
        self.assertTrue(is_login)
        self.assertGreaterEqual(confidence, 0.90)

    def test_both_agree_boosts_confidence(self):
        # URL gives medium confidence, DOM confirms
        page = MockPage(
            url="https://example.com/login",
            dom_result={
                "loginHits": 2,
                "signupHits": 0,
                "titleHit": "log in",
                "textHit": None,
                "hasPassword": True,
                "title": "Log In",
            }
        )
        result = asyncio.get_event_loop().run_until_complete(
            LoginDetector.detect(page, "https://example.com/login")
        )
        is_login, page_type, confidence = result
        self.assertTrue(is_login)
        # Should be boosted above individual scores
        self.assertGreaterEqual(confidence, 0.90)


# ═══════════════════════════════════════════════════════════════
# Test: HandoffSession
# ═══════════════════════════════════════════════════════════════

class TestHandoffSession(unittest.TestCase):
    """Test HandoffSession dataclass."""

    def test_session_creation(self):
        hs = HandoffSession(
            handoff_id="ho_test123",
            url="https://instagram.com/accounts/login/",
            domain="instagram.com",
            page_type="login",
        )
        self.assertEqual(hs.state, HandoffState.IDLE)
        self.assertTrue(hs.is_active == False)  # IDLE is not active
        self.assertGreater(hs.timeout_seconds, 0)

    def test_session_is_active_waiting(self):
        hs = HandoffSession(
            handoff_id="ho_test123",
            url="https://instagram.com/accounts/login/",
            domain="instagram.com",
            page_type="login",
            state=HandoffState.WAITING_FOR_USER,
        )
        self.assertTrue(hs.is_active)

    def test_session_elapsed(self):
        hs = HandoffSession(
            handoff_id="ho_test123",
            url="https://instagram.com/accounts/login/",
            domain="instagram.com",
            page_type="login",
            created_at=time.time() - 60,
        )
        self.assertGreater(hs.elapsed_seconds, 55)
        self.assertLess(hs.elapsed_seconds, 65)

    def test_session_remaining(self):
        hs = HandoffSession(
            handoff_id="ho_test123",
            url="https://instagram.com/accounts/login/",
            domain="instagram.com",
            page_type="login",
            state=HandoffState.WAITING_FOR_USER,
            updated_at=time.time() - 60,
            timeout_seconds=300,
        )
        self.assertGreater(hs.remaining_seconds, 200)
        self.assertLess(hs.remaining_seconds, 250)

    def test_session_not_expired(self):
        hs = HandoffSession(
            handoff_id="ho_test123",
            url="https://instagram.com/accounts/login/",
            domain="instagram.com",
            page_type="login",
            state=HandoffState.WAITING_FOR_USER,
            updated_at=time.time(),
            timeout_seconds=300,
        )
        self.assertFalse(hs.is_expired)

    def test_session_expired(self):
        hs = HandoffSession(
            handoff_id="ho_test123",
            url="https://instagram.com/accounts/login/",
            domain="instagram.com",
            page_type="login",
            state=HandoffState.WAITING_FOR_USER,
            updated_at=time.time() - 400,
            timeout_seconds=300,
        )
        self.assertTrue(hs.is_expired)

    def test_to_dict_no_sensitive_data(self):
        hs = HandoffSession(
            handoff_id="ho_test123",
            url="https://instagram.com/accounts/login/",
            domain="instagram.com",
            page_type="login",
            screenshot_before="secret_base64_data",
        )
        d = hs.to_dict()
        # Screenshot data should NOT be in the dict
        self.assertNotIn("screenshot_before", d)
        self.assertNotIn("screenshot_after", d)
        self.assertNotIn("cookies_before", d)
        self.assertNotIn("cookies_after", d)
        # But public fields should be present
        self.assertIn("handoff_id", d)
        self.assertIn("url", d)
        self.assertIn("domain", d)
        self.assertIn("state", d)


# ═══════════════════════════════════════════════════════════════
# Test: LoginHandoffManager
# ═══════════════════════════════════════════════════════════════

class TestLoginHandoffManager(unittest.TestCase):
    """Test the core handoff orchestration engine."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def _create_manager(self, page_url="https://www.instagram.com/accounts/login/"):
        page = MockPage(url=page_url, dom_result={
            "loginHits": 2,
            "signupHits": 0,
            "titleHit": "log in",
            "textHit": None,
            "hasPassword": True,
            "title": "Log In — Instagram",
        })
        browser = MockBrowser(pages={"main": page})
        manager = LoginHandoffManager(browser, config={"handoff.auto_detect": True})
        return manager

    def test_start_handoff_login_page(self):
        manager = self._create_manager()
        result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
                user_id="test_user",
                timeout_seconds=300,
            )
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("handoff_id", result)
        self.assertEqual(result["domain"], "instagram.com")
        self.assertEqual(result["page_type"], "login")
        self.assertGreater(result["confidence"], 0.5)

    def test_start_handoff_not_login_page(self):
        page = MockPage(url="https://example.com/about", dom_result={
            "loginHits": 0,
            "signupHits": 0,
            "titleHit": None,
            "textHit": None,
            "hasPassword": False,
            "title": "About Us",
        })
        browser = MockBrowser(pages={"main": page})
        manager = LoginHandoffManager(browser)
        result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://example.com/about",
                page_id="main",
                auto_detected=True,  # Auto-detected should fail on non-login
            )
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("does not appear to be a login", result["error"])

    def test_start_handoff_manual_override(self):
        """Manual trigger should work even on non-login pages (lower threshold)."""
        page = MockPage(url="https://example.com/portal", dom_result={
            "loginHits": 0,
            "signupHits": 0,
            "titleHit": None,
            "textHit": None,
            "hasPassword": False,
            "title": "Portal",
        })
        browser = MockBrowser(pages={"main": page})
        manager = LoginHandoffManager(browser)
        result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://example.com/portal",
                page_id="main",
                auto_detected=False,  # Manual trigger
            )
        )
        # Manual trigger should succeed even without detection
        self.assertEqual(result["status"], "success")

    def test_complete_handoff(self):
        manager = self._create_manager()
        start_result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
                user_id="test_user",
            )
        )
        handoff_id = start_result["handoff_id"]

        # Complete the handoff
        complete_result = self.loop.run_until_complete(
            manager.complete_handoff(handoff_id, user_id="test_user")
        )
        self.assertEqual(complete_result["status"], "success")
        self.assertEqual(complete_result["domain"], "instagram.com")
        self.assertIn("auth_cookie_names", complete_result)
        self.assertIn("duration_seconds", complete_result)

    def test_cancel_handoff(self):
        manager = self._create_manager()
        start_result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        handoff_id = start_result["handoff_id"]

        cancel_result = self.loop.run_until_complete(
            manager.cancel_handoff(handoff_id, reason="User changed mind")
        )
        self.assertEqual(cancel_result["status"], "success")
        self.assertEqual(cancel_result["state"], "cancelled")

    def test_get_handoff_status(self):
        manager = self._create_manager()
        start_result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        handoff_id = start_result["handoff_id"]

        status_result = self.loop.run_until_complete(
            manager.get_handoff_status(handoff_id)
        )
        self.assertEqual(status_result["status"], "success")
        self.assertEqual(status_result["handoff"]["handoff_id"], handoff_id)
        self.assertEqual(status_result["handoff"]["state"], "waiting_for_user")

    def test_list_handoffs(self):
        manager = self._create_manager()
        self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        list_result = self.loop.run_until_complete(manager.list_handoffs())
        self.assertEqual(list_result["status"], "success")
        self.assertGreaterEqual(list_result["count"], 1)

    def test_list_handoffs_state_filter(self):
        manager = self._create_manager()
        self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        list_result = self.loop.run_until_complete(
            manager.list_handoffs(state_filter="waiting_for_user")
        )
        self.assertGreaterEqual(list_result["count"], 1)

        list_result2 = self.loop.run_until_complete(
            manager.list_handoffs(state_filter="completed")
        )
        self.assertEqual(list_result2["count"], 0)

    def test_complete_wrong_state_fails(self):
        """Cannot complete a handoff that's already completed."""
        manager = self._create_manager()
        start_result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        handoff_id = start_result["handoff_id"]

        # Complete once
        self.loop.run_until_complete(manager.complete_handoff(handoff_id))

        # Try to complete again — should fail
        result = self.loop.run_until_complete(manager.complete_handoff(handoff_id))
        self.assertEqual(result["status"], "error")
        self.assertIn("not found", result["error"])

    def test_cancel_wrong_state_fails(self):
        """Cannot cancel a handoff that's already completed."""
        manager = self._create_manager()
        start_result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        handoff_id = start_result["handoff_id"]

        # Complete first
        self.loop.run_until_complete(manager.complete_handoff(handoff_id))

        # Try to cancel — should fail
        result = self.loop.run_until_complete(manager.cancel_handoff(handoff_id))
        self.assertEqual(result["status"], "error")

    def test_nonexistent_handoff(self):
        manager = self._create_manager()
        result = self.loop.run_until_complete(
            manager.get_handoff_status("ho_nonexistent")
        )
        self.assertEqual(result["status"], "error")

    def test_page_not_found(self):
        browser = MockBrowser(pages={})  # No pages
        manager = LoginHandoffManager(browser)
        result = self.loop.run_until_complete(
            manager.start_handoff(url="https://example.com/login", page_id="nonexistent")
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("not found", result["error"])

    def test_max_concurrent_handoffs(self):
        """Should not exceed MAX_CONCURRENT_HANDOFFS."""
        # Create manager with multiple pages
        pages = {f"tab_{i}": MockPage(url=f"https://example.com/login", dom_result={
            "loginHits": 2, "signupHits": 0, "titleHit": "log in",
            "textHit": None, "hasPassword": True, "title": "Login",
        }) for i in range(12)}
        browser = MockBrowser(pages=pages)
        manager = LoginHandoffManager(browser)

        # Start max handoffs
        results = []
        for i in range(LoginHandoffManager.MAX_CONCURRENT_HANDOFFS):
            result = self.loop.run_until_complete(
                manager.start_handoff(url="https://example.com/login", page_id=f"tab_{i}")
            )
            results.append(result)

        # All should succeed
        self.assertTrue(all(r["status"] == "success" for r in results))

        # One more should fail
        extra_result = self.loop.run_until_complete(
            manager.start_handoff(url="https://example.com/login", page_id=f"tab_{11}")
        )
        self.assertEqual(extra_result["status"], "error")
        self.assertIn("Maximum concurrent", extra_result["error"])

    def test_handoff_history(self):
        manager = self._create_manager()
        start_result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        handoff_id = start_result["handoff_id"]

        # Complete the handoff (moves to history)
        self.loop.run_until_complete(manager.complete_handoff(handoff_id))

        history = self.loop.run_until_complete(manager.get_handoff_history())
        self.assertEqual(history["status"], "success")
        self.assertGreaterEqual(history["count"], 1)

    def test_handoff_stats(self):
        manager = self._create_manager()
        start_result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        self.loop.run_until_complete(manager.complete_handoff(start_result["handoff_id"]))

        stats = manager.get_stats()
        self.assertEqual(stats["total_handoffs"], 1)
        self.assertEqual(stats["completed_handoffs"], 1)
        self.assertEqual(stats["active_handoffs"], 0)
        self.assertGreater(stats["success_rate"], 0)

    def test_detect_login_page(self):
        manager = self._create_manager()
        result = self.loop.run_until_complete(manager.detect_login_page(page_id="main"))
        self.assertIn("is_login_page", result)
        self.assertTrue(result["is_login_page"])

    def test_ws_notify_callback(self):
        """WebSocket notifications should be called on state changes."""
        notifications = []

        async def mock_notify(event_type, data):
            notifications.append({"event": event_type, "data": data})

        manager = self._create_manager()
        manager.set_ws_notify(mock_notify)

        start_result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        handoff_id = start_result["handoff_id"]

        # Should have received a "started" notification
        self.assertGreater(len(notifications), 0)
        self.assertEqual(notifications[0]["event"], "login_handoff_started")

        # Complete
        self.loop.run_until_complete(manager.complete_handoff(handoff_id))

        # Should have received a "completed" notification
        self.assertGreater(len(notifications), 1)
        completed_notifs = [n for n in notifications if n["event"] == "login_handoff_completed"]
        self.assertGreater(len(completed_notifs), 0)

    def test_cancel_notification(self):
        notifications = []

        async def mock_notify(event_type, data):
            notifications.append({"event": event_type, "data": data})

        manager = self._create_manager()
        manager.set_ws_notify(mock_notify)

        start_result = self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        handoff_id = start_result["handoff_id"]

        self.loop.run_until_complete(
            manager.cancel_handoff(handoff_id, reason="Testing")
        )

        cancelled_notifs = [n for n in notifications if n["event"] == "login_handoff_cancelled"]
        self.assertGreater(len(cancelled_notifs), 0)


# ═══════════════════════════════════════════════════════════════
# Test: Auto-detection integration
# ═══════════════════════════════════════════════════════════════

class TestAutoDetection(unittest.TestCase):
    """Test auto-detection of login pages during navigation."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_auto_handoff_on_login_page(self):
        page = MockPage(url="https://www.instagram.com/accounts/login/", dom_result={
            "loginHits": 3, "signupHits": 0, "titleHit": "log in",
            "textHit": None, "hasPassword": True, "title": "Log In — Instagram",
        })
        browser = MockBrowser(pages={"main": page})
        manager = LoginHandoffManager(browser, config={"handoff.auto_detect": True})

        result = self.loop.run_until_complete(
            manager.check_and_auto_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["domain"], "instagram.com")

    def test_no_auto_handoff_on_normal_page(self):
        page = MockPage(url="https://example.com/about", dom_result={
            "loginHits": 0, "signupHits": 0, "titleHit": None,
            "textHit": None, "hasPassword": False, "title": "About Us",
        })
        browser = MockBrowser(pages={"main": page})
        manager = LoginHandoffManager(browser, config={"handoff.auto_detect": True})

        result = self.loop.run_until_complete(
            manager.check_and_auto_handoff(
                url="https://example.com/about",
                page_id="main",
            )
        )
        self.assertIsNone(result)

    def test_auto_handoff_disabled(self):
        page = MockPage(url="https://www.instagram.com/accounts/login/", dom_result={
            "loginHits": 3, "signupHits": 0, "titleHit": "log in",
            "textHit": None, "hasPassword": True, "title": "Log In",
        })
        browser = MockBrowser(pages={"main": page})
        manager = LoginHandoffManager(browser, config={"handoff.auto_detect": False})

        result = self.loop.run_until_complete(
            manager.check_and_auto_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        self.assertIsNone(result)

    def test_no_auto_handoff_if_already_active(self):
        page = MockPage(url="https://www.instagram.com/accounts/login/", dom_result={
            "loginHits": 3, "signupHits": 0, "titleHit": "log in",
            "textHit": None, "hasPassword": True, "title": "Log In",
        })
        browser = MockBrowser(pages={"main": page})
        manager = LoginHandoffManager(browser, config={"handoff.auto_detect": True})

        # Start first handoff
        self.loop.run_until_complete(
            manager.start_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )

        # Second auto-handoff on same page should return None
        result = self.loop.run_until_complete(
            manager.check_and_auto_handoff(
                url="https://www.instagram.com/accounts/login/",
                page_id="main",
            )
        )
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════
# Test: Security - No credential leakage
# ═══════════════════════════════════════════════════════════════

class TestSecurity(unittest.TestCase):
    """Verify that credentials are never exposed to the AI agent."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_to_dict_excludes_screenshots(self):
        hs = HandoffSession(
            handoff_id="ho_test",
            url="https://instagram.com/login",
            domain="instagram.com",
            page_type="login",
            screenshot_before="SENSITIVE_BASE64_DATA",
            screenshot_after="SENSITIVE_BASE64_DATA",
        )
        d = hs.to_dict()
        self.assertNotIn("screenshot_before", d)
        self.assertNotIn("screenshot_after", d)

    def test_to_dict_excludes_cookies(self):
        hs = HandoffSession(
            handoff_id="ho_test",
            url="https://instagram.com/login",
            domain="instagram.com",
            page_type="login",
            cookies_before=[{"name": "sessionid", "value": "SECRET123"}],
            cookies_after=[{"name": "sessionid", "value": "SECRET456"}],
        )
        d = hs.to_dict()
        self.assertNotIn("cookies_before", d)
        self.assertNotIn("cookies_after", d)
        # Only cookie NAMES are exposed, not values
        self.assertIn("auth_cookie_names", d)

    def test_complete_result_no_cookie_values(self):
        page = MockPage(url="https://www.instagram.com/accounts/login/", dom_result={
            "loginHits": 2, "signupHits": 0, "titleHit": "log in",
            "textHit": None, "hasPassword": True, "title": "Login",
        })
        browser = MockBrowser(
            pages={"main": page},
        )
        browser._cookies = {
            "cookies": [
                {"name": "sessionid", "value": "super_secret_value", "domain": ".instagram.com"},
                {"name": "csrftoken", "value": "another_secret", "domain": ".instagram.com"},
            ]
        }
        manager = LoginHandoffManager(browser)
        start_result = self.loop.run_until_complete(
            manager.start_handoff(url="https://www.instagram.com/accounts/login/", page_id="main")
        )
        handoff_id = start_result["handoff_id"]

        # Simulate new cookies appearing after login
        browser._cookies = {
            "cookies": [
                {"name": "sessionid", "value": "super_secret_value", "domain": ".instagram.com"},
                {"name": "csrftoken", "value": "another_secret", "domain": ".instagram.com"},
                {"name": "ds_user_id", "value": "12345678", "domain": ".instagram.com"},
            ]
        }

        complete_result = self.loop.run_until_complete(
            manager.complete_handoff(handoff_id)
        )

        # Result should NOT contain cookie values
        self.assertEqual(complete_result["status"], "success")
        result_str = json.dumps(complete_result)
        self.assertNotIn("super_secret_value", result_str)
        self.assertNotIn("another_secret", result_str)
        self.assertNotIn("12345678", result_str)

        # But should contain cookie NAMES
        self.assertIn("auth_cookie_names", complete_result)
        self.assertIn("ds_user_id", complete_result["auth_cookie_names"])


# ═══════════════════════════════════════════════════════════════
# Test: Edge Cases & Robustness
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases(unittest.TestCase):
    """Test edge cases and robustness."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_empty_url_detection(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url("")
        self.assertFalse(is_login)

    def test_none_url_detection(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(None)
        self.assertFalse(is_login)

    def test_url_with_query_params(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://www.instagram.com/accounts/login/?next=/feed/"
        )
        self.assertTrue(is_login)

    def test_url_with_fragment(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://example.com/login#section"
        )
        self.assertTrue(is_login)

    def test_case_insensitive_url(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://EXAMPLE.COM/LOGIN"
        )
        self.assertTrue(is_login)

    def test_https_and_http(self):
        is_login_https, _, _ = LoginDetector.detect_from_url(
            "https://example.com/login"
        )
        is_login_http, _, _ = LoginDetector.detect_from_url(
            "http://example.com/login"
        )
        self.assertTrue(is_login_https)
        self.assertTrue(is_login_http)

    def test_wordpress_login(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://blog.example.com/wp-login.php"
        )
        self.assertTrue(is_login)
        self.assertEqual(page_type, "login")

    def test_oauth_login(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://auth.example.com/oauth/authorize"
        )
        self.assertTrue(is_login)

    def test_saml_login(self):
        is_login, page_type, confidence = LoginDetector.detect_from_url(
            "https://corp.example.com/saml/login"
        )
        self.assertTrue(is_login)

    def test_multiple_handoff_lifecycle(self):
        """Full lifecycle: start → check status → complete → verify history."""
        page = MockPage(url="https://www.instagram.com/accounts/login/", dom_result={
            "loginHits": 2, "signupHits": 0, "titleHit": "log in",
            "textHit": None, "hasPassword": True, "title": "Login",
        })
        browser = MockBrowser(pages={"main": page})
        manager = LoginHandoffManager(browser)

        # Start
        start = self.loop.run_until_complete(
            manager.start_handoff(url="https://www.instagram.com/accounts/login/", page_id="main")
        )
        self.assertEqual(start["status"], "success")
        handoff_id = start["handoff_id"]

        # Status
        status = self.loop.run_until_complete(manager.get_handoff_status(handoff_id))
        self.assertEqual(status["handoff"]["state"], "waiting_for_user")

        # Complete
        complete = self.loop.run_until_complete(manager.complete_handoff(handoff_id))
        self.assertEqual(complete["status"], "success")

        # History
        history = self.loop.run_until_complete(manager.get_handoff_history())
        self.assertGreater(history["count"], 0)

        # Stats
        stats = manager.get_stats()
        self.assertEqual(stats["completed_handoffs"], 1)
        self.assertEqual(stats["success_rate"], 100.0)


# ═══════════════════════════════════════════════════════════════
# Run All Tests
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  Agent-OS Login Handoff — Stress Test")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestLoginDetectorURL))
    suite.addTests(loader.loadTestsFromTestCase(TestLoginDetectorDOM))
    suite.addTests(loader.loadTestsFromTestCase(TestLoginDetectorCombined))
    suite.addTests(loader.loadTestsFromTestCase(TestHandoffSession))
    suite.addTests(loader.loadTestsFromTestCase(TestLoginHandoffManager))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestSecurity))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total - failures - errors
    success_rate = (passed / total * 100) if total > 0 else 0
    print(f"  Results: {passed}/{total} passed ({success_rate:.1f}% success rate)")
    print(f"  Failures: {failures}, Errors: {errors}")
    print("=" * 60)

    sys.exit(0 if result.wasSuccessful() else 1)
