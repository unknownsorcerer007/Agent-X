"""
Agent-OS Auto-Retry Engine
Intelligent retry with adaptive strategies, circuit breakers, and error classification.

Production features:
  - Error classification: transient / permanent / rate-limit / timeout / network / unknown
  - Adaptive backoff: exponential with jitter, respects Retry-After headers
  - Circuit breaker: trips after N consecutive failures, half-open probe recovery
  - Retry budgets: max retries per time window (prevents retry storms)
  - Per-operation profiles: different strategies for navigate, click, fill, etc.
  - Request deduplication: in-flight request coalescing
  - Smart error parsing: extracts retry hints from error messages, status codes, headers
  - Integration with smart_wait + auto_heal for layered resilience
  - Full observability: per-operation stats, circuit breaker state, retry history
"""
import asyncio
import hashlib
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("agent-os.auto_retry")


# ─── Error Classification ───────────────────────────────────

class ErrorClass(Enum):
    TRANSIENT = "transient"        # Temporary failure, safe to retry (502, 503, timeout, connection reset)
    RATE_LIMIT = "rate_limit"      # Rate limited, must back off (429, "too many requests")
    TIMEOUT = "timeout"            # Operation timed out, retry with longer timeout
    NETWORK = "network"            # DNS, connection refused, SSL, unreachable
    PERMANENT = "permanent"        # Don't retry (400, 401, 403, 404, element not found)
    BROWSER = "browser_crash"      # Browser/page crashed, needs recovery
    UNKNOWN = "unknown"            # Can't classify, retry conservatively

# Patterns that indicate permanent failure (don't retry)
_PERMANENT_PATTERNS = [
    r"element not found",
    r"no element matches",
    r"selector.*not found",
    r"timeout waiting for",      # Element wait timeout = element doesn't exist
    r"400\b",
    r"401\b",
    r"403\b",
    r"404\b",
    r"405\b",
    r"410\b",
    r"unauthorized",
    r"forbidden",
    r"not found",
    r"invalid (request|argument|parameter)",
    r"bad request",
    r"method not allowed",
    r"page crashed",
    r"target closed",
    r"browser has been closed",
    r"context was destroyed",
]

# Patterns that indicate transient failure (retry)
_TRANSIENT_PATTERNS = [
    r"502\b",
    r"503\b",
    r"504\b",
    r"connection reset",
    r"econnreset",
    r"econnrefused",
    r"socket hang up",
    r"network.*error",
    r"temporarily unavailable",
    r"service unavailable",
    r"bad gateway",
    r"gateway timeout",
    r"overload",
    r"try again",
    r"internal server error",
]

# Patterns that indicate rate limiting
_RATE_LIMIT_PATTERNS = [
    r"429\b",
    r"too many (requests|attempts)",
    r"rate.?limit",
    r"throttl",
    r"retry.?after",
    r"quota exceeded",
    r"sending too quickly",
    r"slow down",
]

# Patterns that indicate timeout
_TIMEOUT_PATTERNS = [
    r"timed? ?out",
    r"timeout",
    r"deadline exceeded",
    r"took too long",
    r"navigation timeout",
    r"waiting timeout",
]

# Patterns that indicate network issues
_NETWORK_PATTERNS = [
    r"dns",
    r"name resolution",
    r"getaddrinfo",
    r"enotfound",
    r"eai_again",
    r"connection refused",
    r"no route to host",
    r"network is unreachable",
    r"ssl",
    r"certificate",
    r"handshake",
    r"proxy",
]

# Browser crash patterns
_BROWSER_PATTERNS = [
    r"page crashed",
    r"browser.*crash",
    r"target.*closed",
    r"context.*destroyed",
    r"session.*deleted",
    r"disconnected",
    r"browser has been closed",
    r"frame was detached",
]


def classify_error(error: str, status_code: int = None, headers: Dict = None) -> ErrorClass:
    """
    Classify an error into a category for intelligent retry decisions.

    Args:
        error: Error message string
        status_code: HTTP status code (if applicable)
        headers: Response headers (for Retry-After detection)
    """
    error_lower = error.lower() if error else ""

    # Check status code first (highest priority)
    if status_code:
        if status_code in (429,):
            return ErrorClass.RATE_LIMIT
        if status_code in (400, 401, 403, 404, 405, 410, 422):
            return ErrorClass.PERMANENT
        if status_code in (502, 503, 504):
            return ErrorClass.TRANSIENT
        if status_code >= 500:
            return ErrorClass.TRANSIENT

    # Check error message patterns — browser crash first (recoverable)
    for pattern in _BROWSER_PATTERNS:
        if re.search(pattern, error_lower):
            return ErrorClass.BROWSER

    for pattern in _PERMANENT_PATTERNS:
        if re.search(pattern, error_lower):
            return ErrorClass.PERMANENT

    for pattern in _RATE_LIMIT_PATTERNS:
        if re.search(pattern, error_lower):
            return ErrorClass.RATE_LIMIT

    for pattern in _TIMEOUT_PATTERNS:
        if re.search(pattern, error_lower):
            return ErrorClass.TIMEOUT

    for pattern in _NETWORK_PATTERNS:
        if re.search(pattern, error_lower):
            return ErrorClass.NETWORK

    for pattern in _TRANSIENT_PATTERNS:
        if re.search(pattern, error_lower):
            return ErrorClass.TRANSIENT

    return ErrorClass.UNKNOWN


def extract_retry_after(headers: Dict) -> Optional[float]:
    """Extract Retry-After value from headers (seconds)."""
    if not headers:
        return None

    for key in ["Retry-After", "retry-after", "X-RateLimit-Reset", "x-ratelimit-reset"]:
        val = headers.get(key) or headers.get(key.lower()) or headers.get(key.title())
        if val:
            # Could be seconds or HTTP-date
            try:
                return float(val)
            except ValueError:
                # Try parsing as HTTP-date
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(val)
                    return max(0, (dt.timestamp() - time.time()))
                except Exception:
                    pass
    return None


# ─── Retry Strategies ───────────────────────────────────────

@dataclass
class RetryStrategy:
    """Configuration for how to retry a specific error class."""
    max_retries: int = 3
    base_delay_ms: float = 1000
    max_delay_ms: float = 30000
    backoff_multiplier: float = 2.0
    jitter_range: Tuple[float, float] = (0.5, 1.5)  # Multiplied onto delay
    timeout_multiplier: float = 1.5  # Increase timeout on each retry
    should_retry: bool = True

    def get_delay(self, attempt: int, retry_after: float = None) -> float:
        """Calculate delay for this attempt in seconds."""
        if retry_after:
            return min(retry_after, self.max_delay_ms / 1000)

        # Exponential backoff: base * multiplier^attempt
        delay_ms = self.base_delay_ms * (self.backoff_multiplier ** attempt)
        delay_ms = min(delay_ms, self.max_delay_ms)

        # Jitter: randomize ±50%
        jitter = random.uniform(*self.jitter_range)
        delay_ms *= jitter

        return delay_ms / 1000


# Default strategies per error class
DEFAULT_STRATEGIES: Dict[ErrorClass, RetryStrategy] = {
    ErrorClass.TRANSIENT: RetryStrategy(
        max_retries=5,
        base_delay_ms=500,
        max_delay_ms=15000,
        backoff_multiplier=2.0,
    ),
    ErrorClass.RATE_LIMIT: RetryStrategy(
        max_retries=3,
        base_delay_ms=5000,
        max_delay_ms=60000,
        backoff_multiplier=3.0,  # Aggressive backoff for rate limits
        jitter_range=(1.0, 2.0),  # Extra jitter for rate limits
    ),
    ErrorClass.TIMEOUT: RetryStrategy(
        max_retries=3,
        base_delay_ms=2000,
        max_delay_ms=30000,
        backoff_multiplier=2.0,
        timeout_multiplier=2.0,  # Double timeout on each retry
    ),
    ErrorClass.NETWORK: RetryStrategy(
        max_retries=4,
        base_delay_ms=1000,
        max_delay_ms=20000,
        backoff_multiplier=2.0,
    ),
    ErrorClass.BROWSER: RetryStrategy(
        max_retries=2,
        base_delay_ms=3000,
        max_delay_ms=10000,
        backoff_multiplier=2.0,
    ),
    ErrorClass.UNKNOWN: RetryStrategy(
        max_retries=2,
        base_delay_ms=1000,
        max_delay_ms=10000,
        backoff_multiplier=2.0,
    ),
    ErrorClass.PERMANENT: RetryStrategy(
        should_retry=False,
        max_retries=0,
    ),
}


# ─── Per-Operation Profiles ─────────────────────────────────

OPERATION_PROFILES: Dict[str, Dict[ErrorClass, RetryStrategy]] = {
    "navigate": {
        ErrorClass.TRANSIENT: RetryStrategy(max_retries=5, base_delay_ms=1000, max_delay_ms=30000),
        ErrorClass.TIMEOUT: RetryStrategy(max_retries=3, base_delay_ms=2000, max_delay_ms=60000, timeout_multiplier=2.0),
        ErrorClass.NETWORK: RetryStrategy(max_retries=5, base_delay_ms=2000, max_delay_ms=30000),
        ErrorClass.BROWSER: RetryStrategy(max_retries=2, base_delay_ms=3000),
        ErrorClass.PERMANENT: RetryStrategy(should_retry=False),
        ErrorClass.RATE_LIMIT: DEFAULT_STRATEGIES[ErrorClass.RATE_LIMIT],
        ErrorClass.UNKNOWN: RetryStrategy(max_retries=2, base_delay_ms=1000),
    },
    "click": {
        ErrorClass.TRANSIENT: RetryStrategy(max_retries=3, base_delay_ms=300, max_delay_ms=5000),
        ErrorClass.PERMANENT: RetryStrategy(should_retry=False),  # Element not found = don't retry (use heal instead)
        ErrorClass.TIMEOUT: RetryStrategy(max_retries=2, base_delay_ms=500, max_delay_ms=5000),
        ErrorClass.BROWSER: RetryStrategy(max_retries=1, base_delay_ms=2000),
        ErrorClass.RATE_LIMIT: DEFAULT_STRATEGIES[ErrorClass.RATE_LIMIT],
        ErrorClass.NETWORK: DEFAULT_STRATEGIES[ErrorClass.NETWORK],
        ErrorClass.UNKNOWN: RetryStrategy(max_retries=1, base_delay_ms=500),
    },
    "fill": {
        ErrorClass.TRANSIENT: RetryStrategy(max_retries=3, base_delay_ms=300, max_delay_ms=5000),
        ErrorClass.PERMANENT: RetryStrategy(should_retry=False),
        ErrorClass.TIMEOUT: RetryStrategy(max_retries=2, base_delay_ms=500, max_delay_ms=5000),
        ErrorClass.BROWSER: RetryStrategy(max_retries=1, base_delay_ms=2000),
        ErrorClass.RATE_LIMIT: DEFAULT_STRATEGIES[ErrorClass.RATE_LIMIT],
        ErrorClass.NETWORK: DEFAULT_STRATEGIES[ErrorClass.NETWORK],
        ErrorClass.UNKNOWN: RetryStrategy(max_retries=1, base_delay_ms=500),
    },
    "api_call": {
        ErrorClass.TRANSIENT: RetryStrategy(max_retries=5, base_delay_ms=500, max_delay_ms=30000),
        ErrorClass.RATE_LIMIT: RetryStrategy(max_retries=5, base_delay_ms=5000, max_delay_ms=120000, backoff_multiplier=3.0),
        ErrorClass.TIMEOUT: RetryStrategy(max_retries=3, base_delay_ms=2000, max_delay_ms=30000, timeout_multiplier=2.0),
        ErrorClass.NETWORK: RetryStrategy(max_retries=4, base_delay_ms=1000, max_delay_ms=20000),
        ErrorClass.PERMANENT: RetryStrategy(should_retry=False),
        ErrorClass.BROWSER: RetryStrategy(max_retries=1, base_delay_ms=3000),
        ErrorClass.UNKNOWN: RetryStrategy(max_retries=2, base_delay_ms=1000),
    },
}


# ─── Circuit Breaker ────────────────────────────────────────

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation, requests flow through
    OPEN = "open"           # Circuit tripped, all requests fail fast
    HALF_OPEN = "half_open" # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for a specific operation/context.

    CLOSED → OPEN: after `failure_threshold` consecutive failures
    OPEN → HALF_OPEN: after `recovery_timeout_ms` seconds
    HALF_OPEN → CLOSED: if probe request succeeds
    HALF_OPEN → OPEN: if probe request fails
    """
    failure_threshold: int = 5
    recovery_timeout_ms: float = 30000  # 30s before trying again
    half_open_max_probes: int = 1

    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    last_failure_time: float = 0
    total_trips: int = 0
    half_open_probes: int = 0

    def record_success(self):
        """Record a successful operation."""
        self.consecutive_failures = 0
        self.half_open_probes = 0
        if self.state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker CLOSED — service recovered")
        self.state = CircuitState.CLOSED

    def record_failure(self) -> bool:
        """
        Record a failure. Returns True if circuit just tripped.
        """
        self.consecutive_failures += 1

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_probes += 1
            if self.half_open_probes >= self.half_open_max_probes:
                logger.warning("Circuit breaker re-OPENED — probe failed")
                self.state = CircuitState.OPEN
                self.last_failure_time = time.time()
                self.total_trips += 1
                return True

        if self.state == CircuitState.CLOSED and self.consecutive_failures >= self.failure_threshold:
            logger.warning(f"Circuit breaker OPENED — {self.consecutive_failures} consecutive failures")
            self.state = CircuitState.OPEN
            self.last_failure_time = time.time()
            self.total_trips += 1
            return True

        return False

    def can_execute(self) -> bool:
        """Check if requests are allowed through."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            elapsed_ms = (time.time() - self.last_failure_time) * 1000
            if elapsed_ms >= self.recovery_timeout_ms:
                logger.info("Circuit breaker HALF_OPEN — testing recovery")
                self.state = CircuitState.HALF_OPEN
                self.half_open_probes = 0
                return True
            return False

        # HALF_OPEN: allow limited probes
        return self.half_open_probes < self.half_open_max_probes

    def get_state(self) -> Dict:
        return {
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "total_trips": self.total_trips,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_ms": self.recovery_timeout_ms,
            "time_since_last_failure_ms": round((time.time() - self.last_failure_time) * 1000) if self.last_failure_time else None,
        }

    def force_reset(self):
        """Force circuit back to closed state."""
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.half_open_probes = 0


# ─── Retry Budget ───────────────────────────────────────────

@dataclass
class RetryBudget:
    """
    Limits total retries within a time window.
    Prevents retry storms that could overload targets.

    Example: max 20 retries per 60 seconds.
    """
    max_retries: int = 20
    window_seconds: float = 60.0
    _attempts: List[float] = field(default_factory=list)

    def can_retry(self) -> bool:
        """Check if we have budget for another retry."""
        self._cleanup()
        return len(self._attempts) < self.max_retries

    def record_attempt(self):
        """Record a retry attempt."""
        self._attempts.append(time.time())

    def get_usage(self) -> Dict:
        self._cleanup()
        return {
            "used": len(self._attempts),
            "max": self.max_retries,
            "remaining": self.max_retries - len(self._attempts),
            "window_seconds": self.window_seconds,
            "utilization_pct": round(len(self._attempts) / self.max_retries * 100, 1),
        }

    def _cleanup(self):
        cutoff = time.time() - self.window_seconds
        self._attempts = [t for t in self._attempts if t > cutoff]


# ─── Request Deduplication ──────────────────────────────────

@dataclass
class InFlightRequest:
    """Tracks an in-flight request for deduplication."""
    key: str
    future: asyncio.Future
    started_at: float
    requestor_count: int = 1


class RequestDeduplicator:
    """
    Coalesces identical concurrent requests into a single execution.
    If two agents request the same URL at the same time, only one request fires.
    """

    def __init__(self):
        self._in_flight: Dict[str, InFlightRequest] = {}

    def get_request_key(self, operation: str, params: Dict) -> str:
        """Generate a dedup key from operation + params."""
        # Sort params for consistent hashing
        param_str = json.dumps(params, sort_keys=True, default=str)
        raw = f"{operation}:{param_str}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def execute_or_coalesce(self, key: str, coro_factory: Callable) -> Any:
        """
        Execute the coroutine, or coalesce with an existing in-flight request.

        Args:
            key: Dedup key
            coro_factory: Callable that returns a coroutine (called only if no in-flight match)
        """
        # Check for in-flight match
        existing = self._in_flight.get(key)
        if existing and not existing.future.done():
            existing.requestor_count += 1
            logger.debug(f"Coalescing request {key[:12]}... (count: {existing.requestor_count})")
            return await existing.future

        # Execute new request
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._in_flight[key] = InFlightRequest(
            key=key,
            future=future,
            started_at=time.time(),
        )

        try:
            result = await coro_factory()
            if not future.done():
                future.set_result(result)
            return result
        except Exception as e:
            if not future.done():
                future.set_exception(e)
            raise
        finally:
            self._in_flight.pop(key, None)

    def get_stats(self) -> Dict:
        return {
            "in_flight_count": len(self._in_flight),
            "in_flight_keys": list(self._in_flight.keys())[:10],
        }


# ─── Main Auto-Retry Engine ─────────────────────────────────

class AutoRetry:
    """
    Intelligent retry engine for Agent-OS.

    Features:
    - Error classification: knows what's worth retrying
    - Adaptive backoff: exponential + jitter + Retry-After header respect
    - Circuit breaker: trips on sustained failure, auto-recovers
    - Retry budgets: prevents retry storms
    - Per-operation profiles: navigate gets more retries than click
    - Request deduplication: coalesces identical concurrent requests
    - Integration: wraps smart_wait + auto_heal for layered resilience

    Usage:
        retry = AutoRetry(browser, smart_wait, auto_heal)

        # Wrap any operation with intelligent retry
        result = await retry.execute(
            operation="navigate",
            action=lambda: browser.navigate("https://example.com"),
            params={"url": "https://example.com"},
        )

        # Or use convenience wrappers
        result = await retry.navigate("https://example.com")
        result = await retry.click("button.submit")
        result = await retry.api_call("https://api.example.com/data")
    """

    def __init__(self, browser, smart_wait=None, auto_heal=None):
        self.browser = browser
        self.smart_wait = smart_wait
        self.auto_heal = auto_heal

        # Per-operation circuit breakers
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

        # Global retry budget
        self._budget = RetryBudget(max_retries=100, window_seconds=60)

        # Request deduplicator
        self._deduplicator = RequestDeduplicator()

        # Stats
        self._stats = {
            "total_executions": 0,
            "total_retries": 0,
            "total_successes": 0,
            "total_failures": 0,
            "permanent_failures": 0,
            "circuit_breaker_blocks": 0,
            "budget_blocks": 0,
            "coalesced_requests": 0,
            "by_operation": {},
            "by_error_class": {},
            "history": [],
        }

    # ─── Convenience Wrappers ───────────────────────────────

    async def navigate(self, url: str, page_id: str = "main", **kwargs) -> Dict[str, Any]:
        """Navigate with intelligent retry."""
        return await self.execute(
            operation="navigate",
            action=lambda: self.browser.navigate(url, page_id=page_id, **kwargs),
            params={"url": url, "page_id": page_id},
            post_action=lambda r: self.smart_wait.network_idle(timeout_ms=5000, page_id=page_id) if self.smart_wait and r.get("status") == "success" else None,
        )

    async def click(self, selector: str, page_id: str = "main", **kwargs) -> Dict[str, Any]:
        """Click with intelligent retry + auto-heal."""
        return await self.execute(
            operation="click",
            action=lambda: self.browser.click(selector, page_id=page_id, **kwargs),
            params={"selector": selector, "page_id": page_id},
            heal_action=lambda: self.auto_heal.click(selector, page_id=page_id, **kwargs) if self.auto_heal else None,
        )

    async def fill(self, selector: str, value: str, page_id: str = "main", **kwargs) -> Dict[str, Any]:
        """Fill with intelligent retry + auto-heal."""
        return await self.execute(
            operation="fill",
            action=lambda: self.browser.fill_form({selector: value}, page_id=page_id, **kwargs),
            params={"selector": selector, "value": value, "page_id": page_id},
            heal_action=lambda: self.auto_heal.fill(selector, value, page_id=page_id, **kwargs) if self.auto_heal else None,
        )

    async def api_call(self, url: str, method: str = "GET", headers: Dict = None, body: Any = None, **kwargs) -> Dict[str, Any]:
        """API call with intelligent retry (uses evaluate_js for fetch)."""
        script = f"""
        (async () => {{
            try {{
                const opts = {{
                    method: '{method}',
                    headers: {json.dumps(headers or {})},
                }};
                if ({json.dumps(body)} && '{method}' !== 'GET') {{
                    opts.body = JSON.stringify({json.dumps(body)});
                    if (!opts.headers['Content-Type']) opts.headers['Content-Type'] = 'application/json';
                }}
                const resp = await fetch('{url}', opts);
                const text = await resp.text();
                let data;
                try {{ data = JSON.parse(text); }} catch {{ data = text; }}
                return {{ status: resp.status, headers: Object.fromEntries(resp.headers), data: data }};
            }} catch(e) {{
                return {{ status: 0, error: e.message }};
            }}
        }})()
        """

        async def do_fetch():
            _resp = await self.browser.evaluate_js(script)
            # evaluate_js now returns {"status": ..., "result": ...} dict
            # Unwrap the dual-return contract to get the actual fetch response
            result = _resp.get("result") if isinstance(_resp, dict) and _resp.get("status") == "success" else _resp
            # result is the fetch response dict
            # {status: HTTP_STATUS, headers: {...}, data: ...}
            if isinstance(result, dict):
                http_status = result.get("status", 200)
                # HTTP status could be int (fetch response) or string (error)
                if isinstance(http_status, int) and http_status >= 400:
                    raise Exception(f"HTTP {http_status}: {str(result.get('data', ''))[:200]}")
                # If status is 0, fetch itself failed (network error)
                if http_status == 0:
                    error_msg = result.get("error", "Network error")
                    raise Exception(f"Fetch failed: {error_msg}")
            return result

        return await self.execute(
            operation="api_call",
            action=do_fetch,
            params={"url": url, "method": method},
            status_code_getter=lambda r: r.get("status") if isinstance(r, dict) else None,
            headers_getter=lambda r: r.get("headers") if isinstance(r, dict) else None,
        )

    # ─── Core Retry Engine ──────────────────────────────────

    async def execute(
        self,
        operation: str,
        action: Callable,
        params: Dict = None,
        strategies: Dict[ErrorClass, RetryStrategy] = None,
        post_action: Callable = None,
        heal_action: Callable = None,
        status_code_getter: Callable = None,
        headers_getter: Callable = None,
        deduplicate: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute an action with intelligent retry.

        Args:
            operation: Operation name (navigate, click, fill, api_call, etc.)
            action: Async callable that performs the operation
            params: Parameters (used for logging and dedup)
            strategies: Override retry strategies per error class
            post_action: Async callable to run after success (e.g., smart_wait)
            heal_action: Async callable to try if retry fails (e.g., auto_heal)
            status_code_getter: Extract HTTP status from result
            headers_getter: Extract response headers from result
            deduplicate: If True, coalesce identical concurrent requests
        """
        self._stats["total_executions"] += 1
        params = params or {}
        strategies = strategies or OPERATION_PROFILES.get(operation, DEFAULT_STRATEGIES)

        # Track per-operation stats
        if operation not in self._stats["by_operation"]:
            self._stats["by_operation"][operation] = {
                "executions": 0, "successes": 0, "failures": 0, "retries": 0, "heals": 0
            }
        op_stats = self._stats["by_operation"][operation]
        op_stats["executions"] += 1

        # Get circuit breaker for this operation
        cb = self._get_circuit_breaker(operation)

        start_time = time.time()
        attempt = 0
        last_error = None  # noqa: F841
        last_error_class = None  # noqa: F841
        heal_attempted = False

        while True:
            # Check circuit breaker
            if not cb.can_execute():
                self._stats["circuit_breaker_blocks"] += 1
                logger.warning(f"Circuit breaker OPEN for '{operation}' — failing fast")
                result = {
                    "status": "error",
                    "error": f"Circuit breaker is OPEN for '{operation}'. Service may be down.",
                    "operation": operation,
                    "circuit_breaker": cb.get_state(),
                    "retry": {"attempt": attempt, "total_attempts": attempt},
                }
                op_stats["failures"] += 1
                self._stats["total_failures"] += 1
                self._record_history(operation, params, attempt, "circuit_open", start_time)
                return result

            # Check retry budget
            if attempt > 0 and not self._budget.can_retry():
                self._stats["budget_blocks"] += 1
                logger.warning(f"Retry budget exhausted — failing '{operation}'")
                result = {
                    "status": "error",
                    "error": "Retry budget exhausted. Too many concurrent retries.",
                    "operation": operation,
                    "retry": {"attempt": attempt, "total_attempts": attempt},
                }
                op_stats["failures"] += 1
                self._stats["total_failures"] += 1
                self._record_history(operation, params, attempt, "budget_exhausted", start_time)
                return result

            # Execute action (with optional dedup)
            try:
                if deduplicate and attempt == 0:
                    dedup_key = self._deduplicator.get_request_key(operation, params)
                    result = await self._deduplicator.execute_or_coalesce(dedup_key, action)
                else:
                    result = await action()

                # Check for errors in the result
                if isinstance(result, dict) and result.get("status") == "error":
                    error_msg = result.get("error", "Unknown error")
                    status_code = None
                    headers = None
                    if status_code_getter:
                        status_code = status_code_getter(result)
                    if headers_getter:
                        headers = headers_getter(result)
                    raise RetryableError(error_msg, status_code=status_code, headers=headers)

                # Success!
                cb.record_success()
                self._budget.record_attempt() if attempt > 0 else None

                # Run post-action (e.g., smart_wait)
                if post_action:
                    try:
                        await post_action(result)
                    except Exception:
                        pass  # Post-action failure shouldn't fail the main operation

                elapsed = time.time() - start_time
                op_stats["successes"] += 1
                if attempt > 0:
                    op_stats["retries"] += attempt
                    self._stats["total_retries"] += attempt

                self._record_history(operation, params, attempt, "success", start_time)

                return self._build_success_result(result, operation, attempt, elapsed)

            except RetryableError as e:
                error_msg = str(e)
                status_code = e.status_code
                headers = e.headers
            except asyncio.TimeoutError:
                error_msg = f"Operation '{operation}' timed out"
                status_code = None
                headers = None
            except Exception as e:
                error_msg = str(e)
                status_code = None
                headers = None

            # Classify the error
            error_class = classify_error(error_msg, status_code, headers)
            _last_error = error_msg
            _last_error_class = error_class

            # Track error class stats
            class_key = error_class.value
            self._stats["by_error_class"][class_key] = self._stats["by_error_class"].get(class_key, 0) + 1

            # Get strategy for this error class
            strategy = strategies.get(error_class, DEFAULT_STRATEGIES.get(error_class, DEFAULT_STRATEGIES[ErrorClass.UNKNOWN]))

            # Record failure for circuit breaker
            cb.record_failure()

            # Check if we should retry
            if not strategy.should_retry or attempt >= strategy.max_retries:
                # Permanent failure or max retries exhausted
                # Try auto-heal as last resort
                if not heal_attempted and heal_action and error_class != ErrorClass.PERMANENT:
                    heal_attempted = True
                    op_stats["heals"] += 1
                    logger.info(f"Retry exhausted for '{operation}', attempting auto-heal...")
                    try:
                        heal_result = await heal_action()
                        if heal_result and heal_result.get("status") == "success":
                            elapsed = time.time() - start_time
                            return self._build_success_result(heal_result, operation, attempt + 1, elapsed, healed=True)
                    except Exception as he:
                        logger.debug(f"Auto-heal also failed: {he}")

                # Truly failed
                self._stats["total_failures"] += 1
                if not strategy.should_retry:
                    self._stats["permanent_failures"] += 1
                op_stats["failures"] += 1
                op_stats["retries"] += attempt
                self._stats["total_retries"] += attempt
                elapsed = time.time() - start_time

                self._record_history(operation, params, attempt + 1, "failed", start_time)

                return {
                    "status": "error",
                    "error": error_msg,
                    "operation": operation,
                    "error_class": error_class.value,
                    "retry": {
                        "attempt": attempt,
                        "total_attempts": attempt + 1,
                        "max_retries": strategy.max_retries,
                        "permanent": not strategy.should_retry,
                        "heal_attempted": heal_attempted,
                    },
                    "circuit_breaker": cb.get_state(),
                    "elapsed_ms": round(elapsed * 1000, 1),
                }

            # Calculate delay and wait
            retry_after = extract_retry_after(headers)
            delay = strategy.get_delay(attempt, retry_after)
            self._budget.record_attempt()

            attempt += 1
            self._stats["total_retries"] += 1

            logger.info(
                f"Retry {attempt}/{strategy.max_retries} for '{operation}' "
                f"after {error_class.value} error, waiting {delay:.1f}s: {error_msg[:100]}"
            )

            self._record_history(operation, params, attempt, "retry", start_time, error=error_msg, error_class=error_class.value)

            await asyncio.sleep(delay)

    # ─── Convenience: Execute with Smart Wait ───────────────

    async def execute_with_wait(
        self,
        operation: str,
        action: Callable,
        wait_selector: str = None,
        params: Dict = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute with retry + smart wait integration.
        Waits for page/element readiness before and/or after the action.
        """
        async def wrapped_action():
            # Pre-wait: page ready
            if self.smart_wait:
                await self.smart_wait.page_ready(timeout_ms=10000)

            result = await action()

            # Post-wait: element or network ready
            if self.smart_wait and isinstance(result, dict) and result.get("status") == "success":
                if wait_selector:
                    await self.smart_wait.element_ready(wait_selector, timeout_ms=5000, require_interactable=False)
                else:
                    await self.smart_wait.network_idle(timeout_ms=2000)

            return result

        return await self.execute(operation=operation, action=wrapped_action, params=params, **kwargs)

    # ─── Circuit Breaker Management ─────────────────────────

    def get_circuit_breakers(self) -> Dict[str, Dict]:
        """Get state of all circuit breakers."""
        return {name: cb.get_state() for name, cb in self._circuit_breakers.items()}

    def reset_circuit_breaker(self, operation: str) -> Dict:
        """Force-reset a circuit breaker."""
        cb = self._get_circuit_breaker(operation)
        cb.force_reset()
        return {"status": "success", "operation": operation, "state": cb.get_state()}

    def reset_all_circuit_breakers(self) -> Dict:
        """Force-reset all circuit breakers."""
        for cb in self._circuit_breakers.values():
            cb.force_reset()
        return {"status": "success", "reset_count": len(self._circuit_breakers)}

    # ─── Stats & Observability ──────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive retry statistics."""
        return {
            "status": "success",
            "stats": {
                "total_executions": self._stats["total_executions"],
                "total_retries": self._stats["total_retries"],
                "total_successes": self._stats["total_successes"],
                "total_failures": self._stats["total_failures"],
                "permanent_failures": self._stats["permanent_failures"],
                "circuit_breaker_blocks": self._stats["circuit_breaker_blocks"],
                "budget_blocks": self._stats["budget_blocks"],
                "success_rate": round(
                    self._stats["total_successes"] / max(1, self._stats["total_executions"]) * 100, 1
                ),
                "avg_retries_per_op": round(
                    self._stats["total_retries"] / max(1, self._stats["total_executions"]), 2
                ),
            },
            "by_operation": self._stats["by_operation"],
            "by_error_class": self._stats["by_error_class"],
            "circuit_breakers": self.get_circuit_breakers(),
            "budget": self._budget.get_usage(),
            "deduplication": self._deduplicator.get_stats(),
            "recent_history": self._stats["history"][-30:],
        }

    def get_health(self) -> Dict[str, Any]:
        """Quick health check — are circuits open? Budget OK?"""
        open_circuits = [
            name for name, cb in self._circuit_breakers.items()
            if cb.state == CircuitState.OPEN
        ]
        budget_ok = self._budget.can_retry()

        healthy = len(open_circuits) == 0 and budget_ok

        return {
            "healthy": healthy,
            "open_circuits": open_circuits,
            "budget_ok": budget_ok,
            "budget_remaining": self._budget.max_retries - len(self._budget._attempts),
        }

    # ─── Internal Helpers ───────────────────────────────────

    def _get_circuit_breaker(self, operation: str) -> CircuitBreaker:
        """Get or create a circuit breaker for an operation."""
        if operation not in self._circuit_breakers:
            # Different thresholds per operation
            thresholds = {
                "navigate": 8,
                "click": 5,
                "fill": 5,
                "api_call": 10,
            }
            recovery = {
                "navigate": 30000,
                "click": 15000,
                "fill": 15000,
                "api_call": 60000,
            }
            self._circuit_breakers[operation] = CircuitBreaker(
                failure_threshold=thresholds.get(operation, 5),
                recovery_timeout_ms=recovery.get(operation, 30000),
            )
        return self._circuit_breakers[operation]

    def _build_success_result(self, result, operation: str, attempts: int, elapsed: float, healed: bool = False) -> Dict:
        """Build a standardized success result."""
        if isinstance(result, dict):
            result["retry"] = {
                "attempt": attempts,
                "total_attempts": attempts + 1,
                "healed": healed,
            }
            result["elapsed_ms"] = round(elapsed * 1000, 1)
            return result

        return {
            "status": "success",
            "operation": operation,
            "result": str(result),
            "retry": {"attempt": attempts, "total_attempts": attempts + 1, "healed": healed},
            "elapsed_ms": round(elapsed * 1000, 1),
        }

    def _record_history(self, operation, params, attempt, outcome, start_time, error=None, error_class=None):
        """Record execution in history."""
        self._stats["history"].append({
            "timestamp": time.time(),
            "operation": operation,
            "params_keys": list(params.keys()) if params else [],
            "attempt": attempt,
            "outcome": outcome,
            "elapsed_ms": round((time.time() - start_time) * 1000, 1),
            "error": (error or "")[:200],
            "error_class": error_class,
        })
        # Cap history
        if len(self._stats["history"]) > 500:
            self._stats["history"] = self._stats["history"][-500:]


class RetryableError(Exception):
    """Wrapper for errors that should be considered for retry."""
    def __init__(self, message: str, status_code: int = None, headers: Dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers
