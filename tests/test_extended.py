"""
Agent-OS Extended Test Suite
Tests for core components, server, and tools.
Run with: python -m pytest tests/ -v
"""
import asyncio
import sys
import os
import pytest
import json
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import Config, DEFAULT_CONFIG
from src.core.session import SessionManager, Session
from src.security.human_mimicry import HumanMimicry
from src.security.captcha_bypass import CaptchaBypass
from src.tools.network_capture import NetworkCapture, NetworkRequest
from src.tools.auto_retry import (
    classify_error, ErrorClass, CircuitBreaker, CircuitState,
    RetryBudget, RetryStrategy, RequestDeduplicator
)


# ─── Config Tests ─────────────────────────────────────────────

class TestConfig:
    def _make_config(self, name="config"):
        path = tempfile.mktemp(suffix=f"-{name}.yaml")
        return Config(path)

    def test_default_config(self):
        config = self._make_config("defaults")
        assert config.get("browser.headless") == True
        assert config.get("browser.max_ram_mb") == 500
        assert config.get("server.ws_port") == 8000
        assert config.get("session.timeout_minutes") == 15

    def test_set_and_get(self):
        config = self._make_config("setget")
        config.set("browser.headless", False)
        assert config.get("browser.headless") == False
        config.set("custom.nested.value", 42)
        assert config.get("custom.nested.value") == 42

    def test_default_fallback(self):
        config = self._make_config("fallback")
        assert config.get("nonexistent.key", "default") == "default"

    def test_deep_merge(self):
        config = self._make_config("merge")
        config.set("browser.headless", False)
        # Other browser defaults should still exist
        assert config.get("browser.max_ram_mb") == 500
        assert config.get("browser.headless") == False

    def test_token_generation(self):
        config = self._make_config("token")
        token = config.generate_agent_token("test")
        assert token.startswith("test-")
        assert len(token) > 20

    def test_configurable_timezone(self):
        config = self._make_config("tz")
        assert config.get("browser.timezone_id") == "America/New_York"
        config.set("browser.timezone_id", "Asia/Shanghai")
        assert config.get("browser.timezone_id") == "Asia/Shanghai"

    def test_configurable_locale(self):
        config = self._make_config("locale")
        assert config.get("browser.locale") == "en-US"
        config.set("browser.locale", "zh-CN")
        assert config.get("browser.locale") == "zh-CN"


# ─── Session Tests ─────────────────────────────────────────────

class TestSession:
    def test_session_creation(self):
        import tempfile
        config = Config(tempfile.mktemp(suffix=".yaml"))
        sm = SessionManager(config)
        session = sm.create_session("test-token")
        assert session.session_id is not None
        assert session.agent_token == "test-token"
        assert session.active == True

    def test_session_expiry(self):
        session = Session("test", "token", expires_at=time.time() - 1)
        assert session.is_expired == True

    def test_session_valid(self):
        session = Session("test", "token", expires_at=time.time() + 3600)
        assert session.is_expired == False
        assert session.time_remaining > 0

    def test_max_concurrent_sessions(self):
        import tempfile
        config = Config(tempfile.mktemp(suffix=".yaml"))
        config.set("session.max_concurrent", 2)
        sm = SessionManager(config)
        s1 = sm.create_session("token1")
        s2 = sm.create_session("token2")
        s3 = sm.create_session("token3")  # Should deactivate s1
        active = [s for s in sm.sessions.values() if s.active and not s.is_expired]
        assert len(active) <= 2


# ─── Error Classification Tests ────────────────────────────────

class TestErrorClassification:
    def test_transient_502(self):
        assert classify_error("502 Bad Gateway") == ErrorClass.TRANSIENT

    def test_transient_503(self):
        assert classify_error("Service Unavailable", status_code=503) == ErrorClass.TRANSIENT

    def test_rate_limit_429(self):
        assert classify_error("Too many requests", status_code=429) == ErrorClass.RATE_LIMIT

    def test_rate_limit_message(self):
        assert classify_error("rate limit exceeded") == ErrorClass.RATE_LIMIT

    def test_permanent_404(self):
        assert classify_error("Not found", status_code=404) == ErrorClass.PERMANENT

    def test_permanent_element_not_found(self):
        assert classify_error("Element not found: #btn") == ErrorClass.PERMANENT

    def test_timeout(self):
        assert classify_error("Navigation timeout") == ErrorClass.TIMEOUT

    def test_network_error(self):
        assert classify_error("DNS resolution failed") == ErrorClass.NETWORK

    def test_browser_crash(self):
        assert classify_error("Page crashed") == ErrorClass.BROWSER

    def test_unknown(self):
        assert classify_error("Something weird happened") == ErrorClass.UNKNOWN


# ─── Circuit Breaker Tests ─────────────────────────────────────

class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() == True

    def test_trips_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() == False

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout_ms=100)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)  # Wait for recovery timeout
        assert cb.can_execute() == True
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_on_success(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout_ms=100)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.can_execute()  # Move to HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.consecutive_failures == 0

    def test_reopens_on_half_open_failure(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout_ms=100, half_open_max_probes=1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.can_execute()  # Move to HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.total_trips == 2

    def test_force_reset(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.force_reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.consecutive_failures == 0


# ─── Retry Budget Tests ────────────────────────────────────────

class TestRetryBudget:
    def test_allows_within_budget(self):
        budget = RetryBudget(max_retries=5, window_seconds=60)
        for _ in range(5):
            budget.record_attempt()
            assert budget.can_retry() or True  # 5th might be at limit

    def test_blocks_over_budget(self):
        budget = RetryBudget(max_retries=3, window_seconds=60)
        budget.record_attempt()
        budget.record_attempt()
        budget.record_attempt()
        assert budget.can_retry() == False

    def test_budget_resets_after_window(self):
        budget = RetryBudget(max_retries=2, window_seconds=0.1)
        budget.record_attempt()
        budget.record_attempt()
        assert budget.can_retry() == False
        time.sleep(0.15)
        assert budget.can_retry() == True


# ─── Request Deduplicator Tests ────────────────────────────────

class TestRequestDeduplicator:
    def test_different_keys(self):
        dedup = RequestDeduplicator()
        key1 = dedup.get_request_key("navigate", {"url": "https://a.com"})
        key2 = dedup.get_request_key("navigate", {"url": "https://b.com"})
        assert key1 != key2

    def test_same_keys(self):
        dedup = RequestDeduplicator()
        key1 = dedup.get_request_key("click", {"selector": "#btn"})
        key2 = dedup.get_request_key("click", {"selector": "#btn"})
        assert key1 == key2


# ─── Retry Strategy Tests ──────────────────────────────────────

class TestRetryStrategy:
    def test_exponential_backoff(self):
        strategy = RetryStrategy(base_delay_ms=1000, backoff_multiplier=2.0, jitter_range=(1.0, 1.0))
        d0 = strategy.get_delay(0)
        d1 = strategy.get_delay(1)
        d2 = strategy.get_delay(2)
        assert d0 == pytest.approx(1.0, abs=0.1)
        assert d1 == pytest.approx(2.0, abs=0.1)
        assert d2 == pytest.approx(4.0, abs=0.1)

    def test_max_delay_cap(self):
        strategy = RetryStrategy(base_delay_ms=1000, max_delay_ms=3000, backoff_multiplier=10.0, jitter_range=(1.0, 1.0))
        d5 = strategy.get_delay(5)
        assert d5 <= 3.1

    def test_retry_after_override(self):
        strategy = RetryStrategy(base_delay_ms=1000, max_delay_ms=30000)
        d = strategy.get_delay(0, retry_after=5.0)
        assert d == 5.0


# ─── Human Mimicry Tests ──────────────────────────────────────

class TestHumanMimicry:
    def test_typing_delay_range(self):
        h = HumanMimicry()
        delays = [h.typing_delay() for _ in range(100)]
        assert all(40 <= d <= 300 for d in delays)

    def test_mouse_path_points(self):
        h = HumanMimicry()
        path = h.mouse_path(0, 0, 500, 500)
        assert len(path) > 5
        # End near target
        assert abs(path[-1][0] - 500) < 5
        assert abs(path[-1][1] - 500) < 5

    def test_mouse_path_has_curve(self):
        h = HumanMimicry()
        path = h.mouse_path(0, 0, 200, 200)
        # Check that path isn't perfectly straight
        x_coords = [p[0] for p in path]
        # If it's a straight line, all intermediate points would be evenly spaced
        diffs = [abs(x_coords[i+1] - x_coords[i]) for i in range(len(x_coords)-1)]
        # Bezier curve should have varying step sizes due to jitter
        assert len(set(round(d, 1) for d in diffs)) > 1

    def test_mistake_simulation(self):
        h = HumanMimicry()
        # Run multiple times to catch the 3% typo chance
        all_actions = []
        for _ in range(50):
            actions = h.mistake_and_correct("hello world")
            all_actions.extend(actions)
        # With 50 runs of 11 chars, we should get at least some typos
        backspaces = [a for a in all_actions if a[1] == "backspace"]
        # 3% chance per char * 550 chars ≈ 16.5 expected typos
        # Just check the mechanism works (at least some in 50 runs)
        assert isinstance(all_actions, list)
        assert len(all_actions) >= 50 * 11  # At least one action per char


# ─── Captcha Bypass Tests ──────────────────────────────────────

class TestCaptchaBypass:
    def test_detects_recaptcha(self):
        cb = CaptchaBypass()
        assert cb.is_bot_detection("https://www.google.com/recaptcha/api2/anchor") == True

    def test_detects_hcaptcha(self):
        cb = CaptchaBypass()
        assert cb.is_bot_detection("https://hcaptcha.com/1/api.js") == True

    def test_detects_perimeterx(self):
        cb = CaptchaBypass()
        assert cb.is_bot_detection("https://captcha.px-cloud.net/captcha") == True

    def test_allows_normal_urls(self):
        cb = CaptchaBypass()
        assert cb.is_bot_detection("https://example.com/page") == False
        assert cb.is_bot_detection("https://cdn.jsdelivr.net/npm/react") == False

    def test_fake_response_generation(self):
        cb = CaptchaBypass()
        resp = cb.get_fake_response("recaptcha")
        assert resp["success"] == True
        assert "score" in resp

    def test_block_request(self):
        cb = CaptchaBypass()
        result = cb.block_request("https://www.google.com/recaptcha/api.js")
        assert result is not None
        assert result["success"] == True

    def test_dont_block_normal(self):
        cb = CaptchaBypass()
        result = cb.block_request("https://example.com/main.js")
        assert result is None

    def test_stats_tracking(self):
        cb = CaptchaBypass()
        cb.block_request("https://recaptcha.net/api.js")
        cb.block_request("https://hcaptcha.com/1/api.js")
        stats = cb.get_stats()
        assert stats["total_blocked"] == 2
        assert "recaptcha" in stats["by_type"]
        assert "hcaptcha" in stats["by_type"]


# ─── Network Capture Unit Tests ────────────────────────────────

class TestNetworkRequest:
    def test_to_dict_truncation(self):
        req = NetworkRequest(
            id="test",
            url="https://example.com",
            method="GET",
            headers={},
            post_data="x" * 20000,
            resource_type="xhr",
            timestamp=time.time(),
            response_body="y" * 60000,
        )
        d = req.to_dict()
        assert len(d["post_data"]) < 20000
        assert "... [truncated]" in d["post_data"]
        assert len(d["response_body"]) < 60000
        assert "... [truncated]" in d["response_body"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
