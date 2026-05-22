"""
Agent-OS Auto-Proxy Rotation Engine
Production-grade automatic proxy rotation with block detection, exponential backoff,
geo-targeting, and per-domain proxy affinity.

When a site blocks a request (403/429/406), automatically:
  1. Detects the block
  2. Rotates to a different proxy
  3. Applies exponential backoff
  4. Tracks which proxies are burned per domain
  5. Retries with increasing delay

Features:
  - Automatic block detection from HTTP status codes
  - Exponential backoff with jitter
  - Per-domain proxy blacklist (burned proxies)
  - Geo-targeted proxy selection
  - Proxy health scoring and auto-recovery
  - Integration with residential/mobile/datacenter proxy providers
  - Cost tracking per provider
  - Session persistence with proxy switching
"""
import asyncio
import json
import logging
import random
import time
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger("agent-os.auto-proxy")


# ═══════════════════════════════════════════════════════════════
# BLOCK DETECTION
# ═══════════════════════════════════════════════════════════════

class BlockDetector:
    """
    Detects when a request has been blocked by the target site.
    Uses multiple signals beyond just HTTP status codes.
    """

    # HTTP status codes that indicate blocking
    BLOCK_STATUS_CODES = {
        403: "forbidden",
        406: "not_acceptable",
        429: "rate_limited",
        444: "nginx_no_response",
        503: "service_unavailable",
        1020: "cf_waf_rule",
        1015: "cf_rate_limit",
        1012: "cf_firewall",
    }

    # Body patterns indicating blocking
    BLOCK_BODY_PATTERNS = [
        "access denied",
        "blocked",
        "captcha",
        "bot detected",
        "just a moment",
        "checking your browser",
        "please verify",
        "unusual traffic",
        "rate limit",
        "too many requests",
        "security check",
        "challenge",
        "cloudflare ray id",
        "attention required",
        "you have been blocked",
        "request blocked",
        "forbidden",
        "temporarily blocked",
        "suspicious activity",
        "automation detected",
    ]

    @classmethod
    def is_blocked(cls, status_code: int, body: str = "",
                   headers: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Check if a response indicates blocking.

        Returns:
            {
                "blocked": bool,
                "reason": str,
                "severity": "hard" | "soft",
                "should_rotate_proxy": bool,
                "suggested_backoff_seconds": float,
            }
        """
        body_lower = (body or "").lower()[:2000]
        headers = headers or {}

        # Check HTTP status
        if status_code in cls.BLOCK_STATUS_CODES:
            _reason = cls.BLOCK_STATUS_CODES[status_code]

            # Soft blocks (rate limit) vs hard blocks (WAF)
            if status_code == 429:
                # Rate limited — extract retry-after
                retry_after = headers.get("retry-after", headers.get("Retry-After", ""))
                try:
                    backoff = float(retry_after)
                except (ValueError, TypeError):
                    backoff = 30.0

                return {
                    "blocked": True,
                    "reason": f"rate_limited (HTTP {status_code})",
                    "severity": "soft",
                    "should_rotate_proxy": True,
                    "suggested_backoff_seconds": backoff,
                }

            elif status_code in (1020, 1015, 1012):
                return {
                    "blocked": True,
                    "reason": f"cf_waf (HTTP {status_code})",
                    "severity": "hard",
                    "should_rotate_proxy": True,
                    "suggested_backoff_seconds": 10.0,
                }

            else:
                return {
                    "blocked": True,
                    "reason": f"http_{status_code}",
                    "severity": "hard" if status_code == 403 else "soft",
                    "should_rotate_proxy": status_code == 403,
                    "suggested_backoff_seconds": 5.0,
                }

        # Check body content for block indicators
        block_matches = [p for p in cls.BLOCK_BODY_PATTERNS if p in body_lower]
        if len(block_matches) >= 2:
            return {
                "blocked": True,
                "reason": f"body_block ({', '.join(block_matches[:3])})",
                "severity": "hard",
                "should_rotate_proxy": True,
                "suggested_backoff_seconds": 8.0,
            }

        # Check for CF challenge page specifically
        if "just a moment" in body_lower and "cloudflare" in body_lower:
            return {
                "blocked": True,
                "reason": "cloudflare_challenge",
                "severity": "hard",
                "should_rotate_proxy": True,
                "suggested_backoff_seconds": 15.0,
            }

        return {
            "blocked": False,
            "reason": "ok",
            "severity": "none",
            "should_rotate_proxy": False,
            "suggested_backoff_seconds": 0,
        }


# ═══════════════════════════════════════════════════════════════
# EXPONENTIAL BACKOFF WITH JITTER
# ═══════════════════════════════════════════════════════════════

class BackoffStrategy:
    """
    Exponential backoff with jitter for retry delays.

    Formula: min(base * (2 ** attempt) + random_jitter, max_delay)

    Features:
    - Configurable base delay, max delay, and jitter range
    - Per-domain backoff tracking
    - Different backoff curves for soft vs hard blocks
    """

    def __init__(self, base_delay: float = 2.0, max_delay: float = 120.0,
                 jitter_range: float = 1.0):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_range = jitter_range
        self._domain_attempts: Dict[str, int] = defaultdict(int)
        self._domain_last_attempt: Dict[str, float] = {}

    def get_delay(self, domain: str = "", severity: str = "hard",
                  attempt: int = None) -> float:
        """
        Calculate delay for the next retry.

        Args:
            domain: Domain being retried (tracks per-domain)
            severity: "soft" or "hard" block
            attempt: Override attempt number
        """
        if domain:
            self._domain_attempts[domain] = self._domain_attempts.get(domain, 0) + 1
            self._domain_last_attempt[domain] = time.time()
            if attempt is None:
                attempt = self._domain_attempts[domain]
        elif attempt is None:
            attempt = 1

        # Soft blocks get shorter backoff
        if severity == "soft":
            base = self.base_delay * 0.5
        else:
            base = self.base_delay

        # Exponential: base * 2^attempt
        delay = base * (2 ** (attempt - 1))

        # Cap at max
        delay = min(delay, self.max_delay)

        # Add jitter: ±jitter_range seconds
        jitter = random.uniform(-self.jitter_range, self.jitter_range)
        delay = max(0.5, delay + jitter)

        return round(delay, 2)

    def reset(self, domain: str = None):
        """Reset backoff for a domain or all domains."""
        if domain:
            self._domain_attempts.pop(domain, None)
            self._domain_last_attempt.pop(domain, None)
        else:
            self._domain_attempts.clear()
            self._domain_last_attempt.clear()

    def get_attempts(self, domain: str) -> int:
        """Get current attempt count for a domain."""
        return self._domain_attempts.get(domain, 0)


# ═══════════════════════════════════════════════════════════════
# BURNED PROXY TRACKER
# ═══════════════════════════════════════════════════════════════

class BurnedProxyTracker:
    """
    Tracks proxies that have been "burned" (blocked) per domain.

    A proxy is burned when it gets blocked by a specific site.
    Burned proxies are excluded from rotation for that domain
    for a configurable cooldown period.

    After cooldown, proxies are retried (they might have recovered).
    """

    def __init__(self, cooldown_seconds: float = 300):
        self.cooldown = cooldown_seconds
        # domain -> {proxy_id -> burn_time}
        self._burns: Dict[str, Dict[str, float]] = defaultdict(dict)
        # domain -> {proxy_id -> burn_count}
        self._burn_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def burn(self, domain: str, proxy_id: str):
        """Mark a proxy as burned for a domain."""
        self._burns[domain][proxy_id] = time.time()
        self._burn_counts[domain][proxy_id] += 1
        burn_count = self._burn_counts[domain][proxy_id]
        logger.info(f"Proxy {proxy_id} burned for {domain} (burn #{burn_count})")

    def is_burned(self, domain: str, proxy_id: str) -> bool:
        """Check if a proxy is currently burned for a domain."""
        burn_time = self._burns.get(domain, {}).get(proxy_id)
        if not burn_time:
            return False

        elapsed = time.time() - burn_time
        if elapsed < self.cooldown:
            return True

        # Cooldown expired — remove burn
        self._burns[domain].pop(proxy_id, None)
        return False

    def get_burned(self, domain: str) -> Set[str]:
        """Get all currently burned proxy IDs for a domain."""
        now = time.time()
        burned = set()
        burns = self._burns.get(domain, {})
        for proxy_id, burn_time in list(burns.items()):
            if now - burn_time < self.cooldown:
                burned.add(proxy_id)
            else:
                del burns[proxy_id]
        return burned

    def get_excluded(self, domain: str) -> List[str]:
        """Get proxy IDs to exclude for a domain."""
        return list(self.get_burned(domain))

    def get_burn_count(self, domain: str, proxy_id: str) -> int:
        """Get how many times a proxy has been burned for a domain."""
        return self._burn_counts.get(domain, {}).get(proxy_id, 0)

    def clear(self, domain: str = None):
        """Clear burns for a domain or all domains."""
        if domain:
            self._burns.pop(domain, None)
            self._burn_counts.pop(domain, None)
        else:
            self._burns.clear()
            self._burn_counts.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get burn statistics."""
        total_burns = sum(
            len(burns) for burns in self._burns.values()
        )
        domains_with_burns = len([d for d, b in self._burns.items() if b])
        return {
            "total_active_burns": total_burns,
            "domains_with_burns": domains_with_burns,
            "cooldown_seconds": self.cooldown,
        }


# ═══════════════════════════════════════════════════════════════
# PROXY PROVIDER INTEGRATION
# ═══════════════════════════════════════════════════════════════

@dataclass
class ProxyEndpoint:
    """A single proxy endpoint with metadata."""
    proxy_id: str
    url: str
    proxy_type: str = "http"  # http, https, socks5
    country: str = ""
    city: str = ""
    provider: str = ""  # brightdata, oxylabs, smartproxy, etc.
    is_residential: bool = False
    is_mobile: bool = False
    is_datacenter: bool = True
    cost_per_gb: float = 0.0
    total_traffic_gb: float = 0.0
    success_count: int = 0
    fail_count: int = 0
    avg_latency_ms: float = 0.0
    last_used: float = 0.0
    last_success: float = 0.0
    consecutive_fails: int = 0
    tags: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 1.0

    @property
    def score(self) -> float:
        """Combined quality score (0-100)."""
        rate_score = self.success_rate * 60
        latency_score = max(0, 40 - (self.avg_latency_ms / 100))
        return min(100, rate_score + latency_score)

    def to_playwright_config(self) -> Dict[str, Any]:
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        config = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 8080}"}
        if parsed.username:
            config["username"] = parsed.username
        if parsed.password:
            config["password"] = parsed.password
        return config


class ProxyProviderAdapter:
    """
    Base adapter for proxy provider APIs.
    Supports common providers: Bright Data, Oxylabs, SmartProxy, IPRoyal.
    """

    PROVIDER_CONFIGS = {
        "brightdata": {
            "api_url": "https://api.brightdata.com",
            "rotate_url": "https://brd.superproxy.io",
            "auth_format": "brd-customer-{customer_id}-zone-{zone}:{password}",
            "supports_residential": True,
            "supports_mobile": True,
            "supports_country": True,
        },
        "oxylabs": {
            "api_url": "https://api.oxylabs.io",
            "rotate_url": "https://pr.oxylabs.io:7777",
            "auth_format": "{username}:{password}",
            "supports_residential": True,
            "supports_mobile": True,
            "supports_country": True,
        },
        "smartproxy": {
            "api_url": "https://api.smartproxy.com",
            "rotate_url": "https://gate.smartproxy.com",
            "auth_format": "{username}:{password}",
            "supports_residential": True,
            "supports_mobile": True,
            "supports_country": True,
        },
        "iproyal": {
            "api_url": "https://api.iproyal.com",
            "rotate_url": "https://geo.iproyal.com",
            "auth_format": "{username}:{password}",
            "supports_residential": True,
            "supports_country": True,
        },
    }

    @classmethod
    def build_proxy_url(cls, provider: str, config: Dict) -> str:
        """Build proxy URL from provider config."""
        prov = cls.PROVIDER_CONFIGS.get(provider)
        if not prov:
            raise ValueError(f"Unknown provider: {provider}")

        username = config.get("username", "")
        password = config.get("password", "")
        country = config.get("country", "")
        session_id = config.get("session_id", "")

        if provider == "brightdata":
            zone = config.get("zone", "residential")
            customer = config.get("customer_id", "")
            user = f"brd-customer-{customer}-zone-{zone}"
            if country:
                user += f"-country-{country}"
            if session_id:
                user += f"-session-{session_id}"
            return f"http://{user}:{password}@brd.superproxy.io:22225"

        elif provider == "oxylabs":
            user = username
            if country:
                user += f"-country-{country}"
            if session_id:
                user += f"-session-{session_id}"
            return f"http://{user}:{password}@pr.oxylabs.io:7777"

        elif provider == "smartproxy":
            port = config.get("port", 10000)
            user = username
            if country:
                user += f"-country-{country}"
            return f"http://{user}:{password}@gate.smartproxy.com:{port}"

        elif provider == "iproyal":
            port = config.get("port", 12321)
            user = username
            if country:
                user += f"-country-{country}"
            return f"http://{user}:{password}@geo.iproyal.com:{port}"

        return ""

    @classmethod
    def create_endpoints(cls, provider: str, config: Dict,
                         count: int = 10) -> List[ProxyEndpoint]:
        """Create proxy endpoints from provider config."""
        endpoints = []
        countries = config.get("countries", [""])

        for i in range(count):
            country = countries[i % len(countries)] if countries else ""
            session_id = f"s{random.randint(100000, 999999)}"

            proxy_config = {**config, "country": country, "session_id": session_id}
            url = cls.build_proxy_url(provider, proxy_config)

            if url:
                ep = ProxyEndpoint(
                    proxy_id=f"{provider}_{i:03d}",
                    url=url,
                    country=country,
                    provider=provider,
                    is_residential=config.get("type", "residential") == "residential",
                    is_mobile=config.get("type") == "mobile",
                    is_datacenter=config.get("type") == "datacenter",
                    cost_per_gb=config.get("cost_per_gb", 0),
                )
                endpoints.append(ep)

        return endpoints


# ═══════════════════════════════════════════════════════════════
# AUTO-PROXY ROTATION MANAGER
# ═══════════════════════════════════════════════════════════════

class AutoProxyManager:
    """
    Production-grade auto-proxy rotation with intelligent retry.

    Combines:
    - Block detection
    - Exponential backoff
    - Burned proxy tracking
    - Proxy provider integration
    - Per-domain optimization

    Usage:
        manager = AutoProxyManager()

        # Load proxies
        manager.add_proxy("http://proxy1:8080", country="US")
        manager.load_provider("brightdata", {"customer_id": "xxx", "zone": "residential", ...})

        # Navigate with auto-retry
        result = await manager.execute_with_retry(
            url="https://protected-site.com",
            request_func=my_request_function,
            max_retries=5,
        )
    """

    def __init__(self, config=None):
        self.config = config

        # Core components
        self.block_detector = BlockDetector()
        self.backoff = BackoffStrategy(
            base_delay=config.get("auto_proxy.base_delay", 2.0) if config else 2.0,
            max_delay=config.get("auto_proxy.max_delay", 120.0) if config else 120.0,
            jitter_range=config.get("auto_proxy.jitter", 1.0) if config else 1.0,
        )
        self.burned_tracker = BurnedProxyTracker(
            cooldown_seconds=config.get("auto_proxy.burn_cooldown", 300) if config else 300,
        )

        # Proxy storage
        self._proxies: Dict[str, ProxyEndpoint] = {}
        self._domain_affinity: Dict[str, str] = {}  # domain -> preferred proxy_id

        # Stats
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "blocked_requests": 0,
            "proxy_rotations": 0,
            "total_retries": 0,
            "total_backoff_seconds": 0.0,
        }

    def add_proxy(self, url: str, **kwargs) -> str:
        """Add a single proxy."""
        import uuid
        proxy_id = kwargs.pop("proxy_id", f"proxy_{uuid.uuid4().hex[:8]}")
        ep = ProxyEndpoint(proxy_id=proxy_id, url=url, **kwargs)
        self._proxies[proxy_id] = ep
        logger.info(f"Proxy added: {proxy_id}")
        return proxy_id

    def add_proxies(self, urls: List[str], **kwargs) -> int:
        """Add multiple proxies."""
        count = 0
        for url in urls:
            self.add_proxy(url, **kwargs)
            count += 1
        return count

    def load_provider(self, provider: str, config: Dict) -> int:
        """Load proxies from a provider API."""
        endpoints = ProxyProviderAdapter.create_endpoints(provider, config, count=config.get("count", 10))
        for ep in endpoints:
            self._proxies[ep.proxy_id] = ep
        logger.info(f"Loaded {len(endpoints)} proxies from {provider}")
        return len(endpoints)

    def load_from_file(self, filepath: str) -> int:
        """Load proxies from file (JSON, TXT, CSV)."""
        path = Path(filepath)
        if not path.exists():
            return 0

        content = path.read_text().strip()
        count = 0

        if path.suffix == ".json":
            try:
                data = json.loads(content)
                for item in (data if isinstance(data, list) else data.get("proxies", [])):
                    if isinstance(item, str):
                        self.add_proxy(item)
                        count += 1
                    elif isinstance(item, dict):
                        url = item.get("url", "")
                        if url:
                            self.add_proxy(url, **{k: v for k, v in item.items() if k != "url"})
                            count += 1
            except json.JSONDecodeError:
                pass
        else:
            for line in content.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    self.add_proxy(line)
                    count += 1

        return count

    def _get_available_proxies(self, domain: str = "",
                                country: str = None) -> List[ProxyEndpoint]:
        """Get available proxies, excluding burned ones."""
        burned = self.burned_tracker.get_burned(domain) if domain else set()
        available = [
            p for p in self._proxies.values()
            if p.proxy_id not in burned and p.consecutive_fails < 10
        ]

        if country:
            # Filter by country, but don't exclude if none match
            country_match = [p for p in available if p.country.upper() == country.upper()]
            if country_match:
                available = country_match

        # Sort by score (best first)
        available.sort(key=lambda p: p.score, reverse=True)
        return available

    def _select_proxy(self, domain: str = "", country: str = None) -> Optional[ProxyEndpoint]:
        """Select the best proxy for a request."""
        # Check domain affinity
        if domain and domain in self._domain_affinity:
            preferred_id = self._domain_affinity[domain]
            preferred = self._proxies.get(preferred_id)
            if preferred and preferred.consecutive_fails < 3:
                burned = self.burned_tracker.get_burned(domain)
                if preferred_id not in burned:
                    return preferred

        # Get available and pick best
        available = self._get_available_proxies(domain, country)
        if not available:
            return None

        # Weighted random selection (top 3 candidates)
        candidates = available[:3]
        weights = [c.score for c in candidates]
        total = sum(weights)
        if total <= 0:
            return random.choice(candidates)

        r = random.uniform(0, total)
        cumulative = 0
        for c, w in zip(candidates, weights):
            cumulative += w
            if r <= cumulative:
                return c
        return candidates[-1]

    def _record_result(self, proxy: ProxyEndpoint, domain: str,
                       success: bool, status_code: int = 0,
                       latency_ms: float = 0, error: str = ""):
        """Record the result of using a proxy."""
        proxy.last_used = time.time()

        if success:
            proxy.success_count += 1
            proxy.consecutive_fails = 0
            proxy.last_success = time.time()
            if latency_ms > 0:
                proxy.avg_latency_ms = (
                    proxy.avg_latency_ms * 0.7 + latency_ms * 0.3
                    if proxy.avg_latency_ms > 0 else latency_ms
                )
            # Set domain affinity on success
            self._domain_affinity[domain] = proxy.proxy_id
        else:
            proxy.fail_count += 1
            proxy.consecutive_fails += 1

    async def execute_with_retry(
        self,
        url: str,
        request_func,
        max_retries: int = 5,
        country: str = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute a request with automatic proxy rotation and retry.

        Args:
            url: Target URL
            request_func: Async function(proxy_url, url, **kwargs) -> response dict
                          Must return dict with 'status_code' and optionally 'body', 'headers'
            max_retries: Maximum retry attempts
            country: Geo-target proxy selection
            **kwargs: Additional args passed to request_func

        Returns:
            Final response dict with metadata about retries and proxy used
        """
        domain = urlparse(url).hostname or ""
        self._stats["total_requests"] += 1

        tried_proxies: List[str] = []
        total_backoff = 0.0
        last_response = None

        for attempt in range(max_retries + 1):
            # Select proxy
            proxy = self._select_proxy(domain=domain, country=country)
            if not proxy:
                # No proxies available — try without proxy
                logger.warning(f"No available proxies for {domain}, trying direct")
                try:
                    start = time.time()
                    result = await request_func(None, url, **kwargs)
                    latency = (time.time() - start) * 1000

                    block_info = self.block_detector.is_blocked(
                        result.get("status_code", 0),
                        result.get("body", ""),
                        result.get("headers", {}),
                    )

                    if not block_info["blocked"]:
                        self._stats["successful_requests"] += 1
                        result["proxy_used"] = None
                        result["attempt"] = attempt + 1
                        result["total_backoff_seconds"] = round(total_backoff, 2)
                        return result

                except Exception as e:
                    logger.error(f"Direct request failed: {e}")

                return {
                    "status": "error",
                    "error": "No proxies available and direct request failed",
                    "attempts": attempt + 1,
                }

            tried_proxies.append(proxy.proxy_id)

            # Execute request
            try:
                start = time.time()
                proxy_url = proxy.url
                result = await request_func(proxy_url, url, **kwargs)
                latency = (time.time() - start) * 1000

                # Check if blocked
                block_info = self.block_detector.is_blocked(
                    result.get("status_code", 0),
                    result.get("body", ""),
                    result.get("headers", {}),
                )

                if not block_info["blocked"]:
                    # Success!
                    self._record_result(proxy, domain, success=True, latency_ms=latency)
                    self._stats["successful_requests"] += 1
                    self.backoff.reset(domain)

                    result["proxy_used"] = proxy.proxy_id
                    result["proxy_provider"] = proxy.provider
                    result["attempt"] = attempt + 1
                    result["total_backoff_seconds"] = round(total_backoff, 2)
                    result["proxies_tried"] = tried_proxies
                    return result

                # Blocked!
                self._record_result(proxy, domain, success=False,
                                    status_code=result.get("status_code", 0))
                self._stats["blocked_requests"] += 1
                last_response = result

                logger.warning(
                    f"Blocked on {domain} (attempt {attempt + 1}): "
                    f"{block_info['reason']} | proxy: {proxy.proxy_id}"
                )

                # Burn proxy for this domain
                if block_info["should_rotate_proxy"]:
                    self.burned_tracker.burn(domain, proxy.proxy_id)
                    self._stats["proxy_rotations"] += 1

                # Exponential backoff
                if attempt < max_retries:
                    delay = self.backoff.get_delay(
                        domain=domain,
                        severity=block_info["severity"],
                    )
                    # Use suggested backoff if available
                    suggested = block_info.get("suggested_backoff_seconds", 0)
                    if suggested > 0:
                        delay = max(delay, min(suggested, self.backoff.max_delay))

                    total_backoff += delay
                    self._stats["total_backoff_seconds"] += delay
                    logger.info(f"Backing off {delay:.1f}s before retry...")
                    await asyncio.sleep(delay)

            except Exception as e:
                self._record_result(proxy, domain, success=False, error=str(e))
                logger.error(f"Request failed with proxy {proxy.proxy_id}: {e}")

                if attempt < max_retries:
                    delay = self.backoff.get_delay(domain=domain, severity="hard")
                    total_backoff += delay
                    await asyncio.sleep(delay)

        # All retries exhausted
        self._stats["total_retries"] += len(tried_proxies)

        return {
            "status": "exhausted",
            "error": f"All {max_retries + 1} attempts blocked",
            "proxies_tried": tried_proxies,
            "total_backoff_seconds": round(total_backoff, 2),
            "last_status_code": last_response.get("status_code") if last_response else 0,
            "last_block_reason": self.block_detector.is_blocked(
                last_response.get("status_code", 0) if last_response else 0,
                last_response.get("body", "") if last_response else "",
            ).get("reason", "unknown"),
        }

    async def browser_navigate_with_retry(
        self,
        browser,
        url: str,
        max_retries: int = 5,
        country: str = None,
        **nav_kwargs,
    ) -> Dict[str, Any]:
        """
        Navigate a browser with automatic proxy rotation on block detection.

        Uses the browser's built-in navigate() method but wraps it with
        block detection and proxy rotation logic.

        Args:
            browser: AgentBrowser or FirefoxEngine instance
            url: Target URL
            max_retries: Max retries
            country: Geo-target
            **nav_kwargs: Passed to browser.navigate()
        """
        domain = urlparse(url).hostname or ""

        for attempt in range(max_retries):
            result = await browser.navigate(url, retries=1, **nav_kwargs)

            # Check if blocked
            status_code = result.get("status_code", 0)
            title = result.get("title", "")
            error = result.get("error", "")

            block_info = self.block_detector.is_blocked(
                status_code, title + " " + error
            )

            if not block_info["blocked"] and result.get("status") == "success":
                self.backoff.reset(domain)
                result["auto_retry_attempt"] = attempt + 1
                return result

            # Blocked — log and retry
            logger.warning(f"Browser blocked on {domain}: {block_info['reason']} (attempt {attempt + 1})")

            if attempt < max_retries - 1:
                delay = self.backoff.get_delay(domain=domain, severity=block_info["severity"])
                logger.info(f"Browser retry in {delay:.1f}s...")
                await asyncio.sleep(delay)

        return {
            "status": "exhausted",
            "error": f"All {max_retries} browser attempts blocked",
            "last_result": result,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        return {
            "requests": {
                "total": self._stats["total_requests"],
                "successful": self._stats["successful_requests"],
                "blocked": self._stats["blocked_requests"],
                "success_rate": round(
                    self._stats["successful_requests"] /
                    max(1, self._stats["total_requests"]) * 100, 1
                ),
            },
            "retries": {
                "proxy_rotations": self._stats["proxy_rotations"],
                "total_retries": self._stats["total_retries"],
                "total_backoff_seconds": round(self._stats["total_backoff_seconds"], 1),
            },
            "proxies": {
                "total": len(self._proxies),
                "with_affinity": len(self._domain_affinity),
            },
            "burned": self.burned_tracker.get_stats(),
        }

    def get_proxy_stats(self) -> List[Dict]:
        """Get per-proxy statistics."""
        return [
            {
                "proxy_id": p.proxy_id,
                "provider": p.provider,
                "country": p.country,
                "success_rate": round(p.success_rate * 100, 1),
                "total_uses": p.success_count + p.fail_count,
                "consecutive_fails": p.consecutive_fails,
                "avg_latency_ms": round(p.avg_latency_ms, 1),
                "score": round(p.score, 1),
            }
            for p in sorted(self._proxies.values(), key=lambda x: x.score, reverse=True)
        ]

    def clear_burns(self, domain: str = None):
        """Clear burned proxy blacklist."""
        self.burned_tracker.clear(domain)

    def reset_backoff(self, domain: str = None):
        """Reset backoff state."""
        self.backoff.reset(domain)
