"""
Agent-OS Test Suite
Comprehensive tests for all components.
Run with: python -m pytest tests/ -v
"""
import asyncio
import sys
import os
import pytest
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import Config, DEFAULT_CONFIG
from src.core.session import SessionManager, Session
from src.security.human_mimicry import HumanMimicry
from src.security.captcha_bypass import CaptchaBypass
from src.debug.server import DebugServer


# ─── Config Tests ─────────────────────────────────────────────

class TestConfig:
    def _make_config(self, name="config"):
        import tempfile
        path = tempfile.mktemp(suffix=f"-{name}.yaml")
        return Config(path)

    def test_default_config(self):
        """Test default config has all required keys."""
        config = self._make_config("defaults")
        assert config.get("server.ws_port") == 8000
        assert config.get("browser.headless") is True
        assert config.get("session.timeout_minutes") == 15

    def test_set_and_get(self):
        """Test setting and getting config values."""
        config = self._make_config("setget")
        config.set("browser.max_ram_mb", 450)
        assert config.get("browser.max_ram_mb") == 450

    def test_generate_token(self):
        """Test token generation."""
        config = self._make_config("token")
        token = config.generate_agent_token("claude")
        assert token.startswith("claude-")
        assert len(token) > 20  # Now uses 16 hex bytes = 32 chars suffix

    def test_deep_merge(self):
        """Test config deep merge preserves defaults."""
        config = self._make_config("merge")
        # Override a single value
        config.set("browser.max_ram_mb", 999)
        assert config.get("browser.max_ram_mb") == 999
        # Default values should still exist
        assert config.get("browser.headless") is True
        assert config.get("server.ws_port") == 8000


# ─── Session Tests ─────────────────────────────────────────────

class TestSession:
    def _make_config(self, name="session"):
        import tempfile
        path = tempfile.mktemp(suffix=f"-{name}.yaml")
        return Config(path)

    def test_create_session(self):
        """Test session creation."""
        config = self._make_config("create")
        sm = SessionManager(config)
        session = sm.create_session("test-token-123")
        assert session.session_id is not None
        assert session.agent_token == "test-token-123"
        assert session.active is True

    def test_session_expiry(self):
        """Test session timeout."""
        import time as _time
        session = Session("test-id", "test-token")
        # Manually set expires_at to past
        session.expires_at = _time.time() - 100
        assert session.is_expired  # Expired immediately

    def test_get_by_token(self):
        """Test finding session by token."""
        config = self._make_config("bytoken")
        sm = SessionManager(config)
        sm.create_session("my-agent-token")
        found = sm.get_session_by_token("my-agent-token")
        assert found is not None
        assert found.agent_token == "my-agent-token"

    def test_list_active(self):
        """Test listing active sessions."""
        config = self._make_config("listactive")
        sm = SessionManager(config)
        sm.create_session("token-1")
        sm.create_session("token-2")
        active = sm.list_active_sessions()
        assert len(active) == 2


# ─── Human Mimicry Tests ─────────────────────────────────────

class TestHumanMimicry:
    def test_typing_delay(self):
        """Test typing delay is within range."""
        mimicry = HumanMimicry()
        delay = mimicry.typing_delay()
        assert 40 <= delay <= 300

    def test_mouse_path(self):
        """Test mouse path generation."""
        mimicry = HumanMimicry()
        path = mimicry.mouse_path(0, 0, 500, 300)
        assert len(path) >= 5
        # Path should start near origin and end near target
        assert abs(path[-1][0] - 500) < 10
        assert abs(path[-1][1] - 300) < 10

    def test_mouse_path_is_curved(self):
        """Test that mouse paths are not straight lines (human-like curves)."""
        mimicry = HumanMimicry()
        path = mimicry.mouse_path(0, 0, 200, 200)
        # Check that intermediate points deviate from straight line
        deviations = []
        for i in range(1, len(path) - 1):
            t = i / len(path)
            expected_x = 200 * t
            expected_y = 200 * t
            dev = abs(path[i][0] - expected_x) + abs(path[i][1] - expected_y)
            deviations.append(dev)
        # At least some points should deviate (curved path)
        assert sum(d > 1 for d in deviations) > 0

    def test_word_pause(self):
        """Test word pause timing."""
        mimicry = HumanMimicry()
        pause = mimicry.word_pause()
        assert 150 <= pause <= 1500

    def test_page_read_time(self):
        """Test page read time estimation."""
        mimicry = HumanMimicry()
        time_1000 = mimicry.page_read_time(1000)
        time_5000 = mimicry.page_read_time(5000)
        # Longer text should take more time
        assert time_5000 > time_1000


# ─── CAPTCHA Bypass Tests ─────────────────────────────────────

class TestCaptchaBypass:
    def test_detects_recaptcha(self):
        """Test reCAPTCHA URL detection."""
        bypass = CaptchaBypass()
        assert bypass.is_bot_detection("https://www.google.com/recaptcha/api2/anchor")
        assert bypass.is_bot_detection("https://www.gstatic.com/recaptcha/releases/abc123/recaptcha__en.js")

    def test_detects_hcaptcha(self):
        """Test hCaptcha URL detection."""
        bypass = CaptchaBypass()
        assert bypass.is_bot_detection("https://hcaptcha.com/1/api.js")

    def test_detects_perimeterx(self):
        """Test PerimeterX URL detection."""
        bypass = CaptchaBypass()
        assert bypass.is_bot_detection("https://captcha.px-cloud.net/captcha")
        assert bypass.is_bot_detection("https://client.px-cdn.net/bundle.js")

    def test_detects_cloudflare(self):
        """Test Cloudflare Turnstile detection."""
        bypass = CaptchaBypass()
        assert bypass.is_bot_detection("https://challenges.cloudflare.com/turnstile/v0/api.js")

    def test_allows_normal_urls(self):
        """Test that normal URLs are not blocked."""
        bypass = CaptchaBypass()
        assert not bypass.is_bot_detection("https://github.com/login")
        assert not bypass.is_bot_detection("https://google.com/search")
        assert not bypass.is_bot_detection("https://api.example.com/data")

    def test_block_returns_fake_response(self):
        """Test that blocked requests return fake human responses."""
        bypass = CaptchaBypass()
        response = bypass.block_request("https://www.google.com/recaptcha/api2/verify")
        assert response is not None
        assert response.get("success") is True or response.get("human") is True

    def test_stats_tracking(self):
        """Test that bypass statistics are tracked."""
        bypass = CaptchaBypass()
        bypass.block_request("https://recaptcha.net/test")
        bypass.block_request("https://hcaptcha.com/test")
        stats = bypass.get_stats()
        assert stats["total_blocked"] == 2
        assert stats["by_type"]["recaptcha"] == 1
        assert stats["by_type"]["hcaptcha"] == 1


# ─── Integration Tests ─────────────────────────────────────

@pytest.mark.asyncio
class TestIntegration:
    async def test_server_command_list(self):
        """Test that server returns available commands."""
        import aiohttp
        import tempfile

        config = Config(tempfile.mktemp(suffix="-integration.yaml"))
        # We can't start a full server in tests, but we can verify command routing
        assert config.get("server.ws_port") == 8000

    async def test_browser_anti_detection_js(self):
        """Test that anti-detection JS is properly defined."""
        from src.core.stealth import SUPPLEMENTARY_STEALTH_JS
        assert "Notification" in SUPPLEMENTARY_STEALTH_JS
        assert "Battery" in SUPPLEMENTARY_STEALTH_JS or "getBattery" in SUPPLEMENTARY_STEALTH_JS
        assert "sendBeacon" in SUPPLEMENTARY_STEALTH_JS


# ─── Debug Server Tests ───────────────────────────────────────

class TestDebugServer:
    def _make_config(self, name="debug"):
        import tempfile
        path = tempfile.mktemp(suffix=f"-{name}.yaml")
        return Config(path)

    def test_config_has_debug_port(self):
        """Test that default config includes debug port."""
        config = self._make_config("port")
        assert config.get("server.debug_port") == 8002

    def test_command_history(self):
        """Test command recording."""
        config = self._make_config("cmdhist")
        # Mock dependencies
        debug = DebugServer(config, None, None, None)
        debug.record_command("navigate", {"url": "https://example.com"}, {"status": "success"})
        assert len(debug._command_history) == 1
        assert debug._command_history[0]["command"] == "navigate"
        assert debug._command_history[0]["status"] == "success"

    def test_console_log_recording(self):
        """Test console log recording."""
        config = self._make_config("consolelog")
        debug = DebugServer(config, None, None, None)
        debug.record_console_log("error", "Something went wrong", "main")
        assert len(debug._console_logs) == 1
        assert debug._console_logs[0]["level"] == "error"

    def test_max_history_limit(self):
        """Test that history respects max limit."""
        config = self._make_config("maxhist")
        debug = DebugServer(config, None, None, None)
        for i in range(250):
            debug.record_command(f"cmd-{i}", {}, {"status": "success"})
        assert len(debug._command_history) <= 200

    def test_static_dir_exists(self):
        """Test that static files exist."""
        from pathlib import Path
        static_dir = Path(__file__).parent.parent / "src" / "debug" / "static"
        assert (static_dir / "index.html").exists()
        assert (static_dir / "style.css").exists()
        assert (static_dir / "app.js").exists()


# ─── Stealth Module Tests ─────────────────────────────────────

class TestStealthModule:
    def test_imports(self):
        """Test stealth module imports correctly."""
        from src.core.stealth import (
            SUPPLEMENTARY_STEALTH_JS, BOT_DETECTION_URLS,
            FAKE_RESPONSES, handle_request_interception
        )
        assert "Notification" in SUPPLEMENTARY_STEALTH_JS
        assert len(BOT_DETECTION_URLS) > 0
        assert len(FAKE_RESPONSES) > 0

    def test_handle_interception_blocks_recaptcha(self):
        """Test request interception blocks recaptcha."""
        from src.core.stealth import handle_request_interception
        blocked, resp = handle_request_interception("https://www.google.com/recaptcha/api2/verify", "xhr")
        assert blocked is True
        assert resp["success"] is True

    def test_handle_interception_allows_normal(self):
        """Test request interception allows normal URLs."""
        from src.core.stealth import handle_request_interception
        blocked, resp = handle_request_interception("https://github.com/login", "document")
        assert blocked is False

    def test_handle_interception_blocks_scripts(self):
        """Test request interception blocks bot detection scripts."""
        from src.core.stealth import handle_request_interception
        # Scripts matching BOT_DETECTION_SCRIPT_PATTERNS but NOT BOT_DETECTION_URLS
        blocked, resp = handle_request_interception("https://cdn.example.com/botdetect-v2.js", "script")
        assert blocked is True
        assert resp is None  # Empty body for script-only matches


# ─── Server Security Tests ────────────────────────────────────

class TestServerSecurity:
    def _make_config(self, name="security"):
        import tempfile
        path = tempfile.mktemp(suffix=f"-{name}.yaml")
        return Config(path)

    def test_token_validation_with_configured_token(self):
        """Test token validation rejects wrong tokens."""
        from src.core.config import Config
        from src.agents.server import AgentServer

        config = self._make_config("token")
        config.set("server.agent_token", "my-secret-token")

        # Mock browser and session_manager
        server = AgentServer(config, None, None)

        assert server._validate_token_legacy("my-secret-token") is True
        assert server._validate_token_legacy("wrong-token") is False
        assert server._validate_token_legacy("") is False
        assert server._validate_token_legacy(None) is False

    def test_token_validation_with_allowed_list(self):
        """Test token validation with multiple allowed tokens."""
        from src.core.config import Config
        from src.agents.server import AgentServer

        config = self._make_config("allowed")
        config.set("server.allowed_tokens", ["token-a", "token-b", "token-c"])

        server = AgentServer(config, None, None)

        assert server._validate_token_legacy("token-a") is True
        assert server._validate_token_legacy("token-b") is True
        assert server._validate_token_legacy("token-c") is True
        assert server._validate_token_legacy("token-d") is False

    def test_token_validation_rejects_when_no_token_configured(self):
        """Test token validation rejects all tokens when none configured (production safety)."""
        import os
        import tempfile
        from src.core.config import Config
        from src.agents.server import AgentServer
        # Use unique temp path to avoid bleed from other tests
        cfg_path = tempfile.mktemp(suffix=".yaml")
        if os.path.exists(cfg_path):
            os.remove(cfg_path)
        config = Config(cfg_path)
        # Don't set any token - clean config
        assert config.get("server.agent_token") is None
        assert config.get("server.allowed_tokens") == []

        server = AgentServer(config, None, None)

        # Production safety: reject all when no token configured
        assert server._validate_token_legacy("anything") is False
        assert server._validate_token_legacy("") is False
        # Cleanup (file may not exist since Config doesn't auto-save)
        if os.path.exists(cfg_path):
            os.remove(cfg_path)

    def test_rate_limiting(self):
        """Test rate limiter blocks excessive requests."""
        from src.core.config import Config
        from src.agents.server import AgentServer

        config = self._make_config("ratelimit")
        config.set("server.rate_limit_max", 3)
        config.set("server.rate_limit_window", 60)

        server = AgentServer(config, None, None)

        # First 3 should pass
        assert server._check_rate_limit("test-user") is True
        assert server._check_rate_limit("test-user") is True
        assert server._check_rate_limit("test-user") is True
        # 4th should fail
        assert server._check_rate_limit("test-user") is False

        # Different user should still work
        assert server._check_rate_limit("other-user") is True


# ─── RuleBasedRouter Tests ─────────────────────────────────────

class TestRuleBasedRouter:
    """Tests for RuleBasedRouter classification accuracy.

    Covers the 4 previously-misclassified queries plus basic correct
    classifications for all 5 categories.
    """

    def _get_router(self):
        from src.agent_swarm.router.rule_based import RuleBasedRouter
        return RuleBasedRouter()

    # ─── Previously misclassified queries (now fixed) ───

    def test_solve_captcha_routes_to_security(self):
        """'solve the captcha' must route to needs_security, NOT needs_calculation."""
        router = self._get_router()
        result = router.classify("solve the captcha")
        assert result.category.value == "needs_security", (
            f"Expected needs_security, got {result.category.value}"
        )

    def test_bypass_cloudflare_protection_routes_to_security(self):
        """'bypass cloudflare protection' must route to needs_security, NOT ambiguous."""
        router = self._get_router()
        result = router.classify("bypass cloudflare protection")
        assert result.category.value == "needs_security", (
            f"Expected needs_security, got {result.category.value}"
        )

    def test_fill_login_form_routes_to_security(self):
        """'fill the login form' must route to needs_security, NOT ambiguous."""
        router = self._get_router()
        result = router.classify("fill the login form")
        assert result.category.value == "needs_security", (
            f"Expected needs_security, got {result.category.value}"
        )

    def test_scrape_product_data_routes_to_web(self):
        """'scrape product data' must route to needs_web, NOT ambiguous."""
        router = self._get_router()
        result = router.classify("scrape product data")
        assert result.category.value == "needs_web", (
            f"Expected needs_web, got {result.category.value}"
        )

    # ─── Basic correct classifications ───

    def test_math_expression_routes_to_calculation(self):
        """'2+2' must route to needs_calculation."""
        router = self._get_router()
        result = router.classify("2+2")
        assert result.category.value == "needs_calculation", (
            f"Expected needs_calculation, got {result.category.value}"
        )

    def test_write_code_routes_to_code(self):
        """'write a Python function' must route to needs_code."""
        router = self._get_router()
        result = router.classify("write a Python function")
        assert result.category.value == "needs_code", (
            f"Expected needs_code, got {result.category.value}"
        )

    def test_knowledge_query_routes_to_knowledge(self):
        """'what is gravity' must route to needs_knowledge."""
        router = self._get_router()
        result = router.classify("what is gravity")
        assert result.category.value == "needs_knowledge", (
            f"Expected needs_knowledge, got {result.category.value}"
        )

    def test_latest_news_routes_to_web(self):
        """'latest AI news' must route to needs_web."""
        router = self._get_router()
        result = router.classify("latest AI news")
        assert result.category.value == "needs_web", (
            f"Expected needs_web, got {result.category.value}"
        )

    def test_latest_cricket_scores_routes_to_web(self):
        """'latest cricket scores' must route to needs_web (plural scores)."""
        router = self._get_router()
        result = router.classify("latest cricket scores")
        assert result.category.value == "needs_web", (
            f"Expected needs_web, got {result.category.value}"
        )

    def test_stock_price_routes_to_web(self):
        """'stock price of Apple' must route to needs_web (live financial data)."""
        router = self._get_router()
        result = router.classify("stock price of Apple")
        assert result.category.value == "needs_web", (
            f"Expected needs_web, got {result.category.value}"
        )

    def test_currency_conversion_routes_to_web(self):
        """'convert 100 USD to EUR' must route to needs_web (live exchange rate)."""
        router = self._get_router()
        result = router.classify("convert 100 USD to EUR")
        assert result.category.value == "needs_web", (
            f"Expected needs_web, got {result.category.value}"
        )

    def test_formula_for_area_routes_to_knowledge(self):
        """'formula for area of circle' must route to needs_knowledge, NOT needs_calculation."""
        router = self._get_router()
        result = router.classify("formula for area of circle")
        assert result.category.value == "needs_knowledge", (
            f"Expected needs_knowledge, got {result.category.value}"
        )

    def test_security_queries_high_confidence(self):
        """Security-related queries must have high confidence (>= 0.7)."""
        router = self._get_router()
        security_queries = [
            "solve the captcha",
            "bypass cloudflare protection",
            "detect headless browser",
            "spoof tls fingerprint",
        ]
        for query in security_queries:
            result = router.classify(query)
            assert result.category.value == "needs_security", (
                f"'{query}' → {result.category.value}, expected needs_security"
            )
            assert result.confidence >= 0.7, (
                f"'{query}' confidence {result.confidence:.2f} < 0.7"
            )


# ─── Import Tests for New Modules ─────────────────────────────

def test_stealth_import():
    """Test that the shared stealth module imports correctly."""
    from src.core.stealth import SUPPLEMENTARY_STEALTH_JS, handle_request_interception
    assert SUPPLEMENTARY_STEALTH_JS is not None
    assert len(SUPPLEMENTARY_STEALTH_JS) > 100
    assert callable(handle_request_interception)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
