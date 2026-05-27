"""
Agent-X Proxy Rotator
Thread-safe proxy rotation with pluggable strategies.

Supports:
- Cyclic rotation (default) — sequential round-robin
- Weighted rotation — prefer higher-weight proxies
- Random rotation — random selection
- Sticky rotation — same proxy for same domain/session
- Health-aware rotation — skip unhealthy proxies
- Custom strategies via callable

Based on the proxy rotation engine from Scrapling (BSD-3, Karim Shoair).
See THIRD_PARTY_LICENSES.md for attribution.
"""

import logging
import random
import time
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse
from dataclasses import dataclass, field

logger = logging.getLogger("agent-x.proxy-rotator")

# Proxy type: string URL or Playwright-style dict
ProxyType = Union[str, Dict[str, str]]

# Error patterns that indicate proxy failure
PROXY_ERROR_INDICATORS = {
    "net::err_proxy",
    "net::err_tunnel",
    "connection refused",
    "connection reset",
    "connection timed out",
    "failed to connect",
    "could not resolve proxy",
    "proxy connection failed",
    "407 proxy authentication required",
}


def is_proxy_error(error: Exception) -> bool:
    """Check if an error is proxy-related."""
    error_msg = str(error).lower()
    return any(indicator in error_msg for indicator in PROXY_ERROR_INDICATORS)


def get_proxy_key(proxy: ProxyType) -> str:
    """Generate a unique key for a proxy."""
    if isinstance(proxy, str):
        return proxy
    server = proxy.get("server", "")
    username = proxy.get("username", "")
    return f"{server}|{username}"


def normalize_proxy(proxy: ProxyType) -> Dict[str, str]:
    """Normalize proxy to Playwright-style dict format.

    Args:
        proxy: String URL or dict with server/username/password

    Returns:
        Normalized dict with server, username, password keys.
    """
    if isinstance(proxy, str):
        parsed = urlparse(proxy)
        result = {"server": f"{parsed.scheme}://{parsed.hostname}"}
        if parsed.port:
            result["server"] += f":{parsed.port}"
        if parsed.username:
            result["username"] = parsed.username
        if parsed.password:
            result["password"] = parsed.password
        return result
    elif isinstance(proxy, dict):
        return {
            "server": proxy.get("server", ""),
            "username": proxy.get("username", ""),
            "password": proxy.get("password", ""),
        }
    raise TypeError(f"Invalid proxy type: {type(proxy)}. Expected str or dict.")


# ═══════════════════════════════════════════════════════════════
# ROTATION STRATEGIES
# ═══════════════════════════════════════════════════════════════

def cyclic_rotation(proxies: List[ProxyType], current_index: int) -> Tuple[ProxyType, int]:
    """Default cyclic rotation — sequential round-robin with wrap-around."""
    idx = current_index % len(proxies)
    return proxies[idx], (idx + 1) % len(proxies)


def random_rotation(proxies: List[ProxyType], current_index: int) -> Tuple[ProxyType, int]:
    """Random proxy selection."""
    idx = random.randint(0, len(proxies) - 1)
    return proxies[idx], (current_index + 1) % len(proxies)


# ═══════════════════════════════════════════════════════════════
# PROXY HEALTH TRACKING
# ═══════════════════════════════════════════════════════════════

@dataclass
class ProxyHealth:
    """Track health metrics for a single proxy."""
    proxy_id: str
    url: str
    country: str = ""
    region: str = ""
    tags: List[str] = field(default_factory=list)
    weight: float = 1.0
    max_requests_per_minute: int = 0
    # Health tracking
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    last_used: float = 0.0
    last_failure: float = 0.0
    last_success: float = 0.0
    consecutive_failures: int = 0
    disabled: bool = False
    # Rolling window (last 100 requests)
    _recent_latencies: List[float] = field(default_factory=list)
    _recent_results: List[bool] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Success rate as percentage (0-100)."""
        total = self.total_requests
        if total == 0:
            return 100.0
        return (self.successful_requests / total) * 100

    @property
    def avg_latency_ms(self) -> float:
        """Average latency in milliseconds."""
        if not self._recent_latencies:
            return 0.0
        return sum(self._recent_latencies) / len(self._recent_latencies)

    @property
    def is_healthy(self) -> bool:
        """Proxy is considered healthy if:
        - Not disabled
        - Less than 5 consecutive failures
        - Success rate above 50% (after at least 5 requests)
        """
        if self.disabled:
            return False
        if self.consecutive_failures >= 5:
            return False
        if self.total_requests >= 5 and self.success_rate < 50:
            return False
        return True

    def record_success(self, latency_ms: float = 0):
        """Record a successful request."""
        self.total_requests += 1
        self.successful_requests += 1
        self.consecutive_failures = 0
        self.last_success = time.time()
        self.last_used = time.time()
        if latency_ms > 0:
            self.total_latency_ms += latency_ms
            self._recent_latencies.append(latency_ms)
            if len(self._recent_latencies) > 100:
                self._recent_latencies.pop(0)
        self._recent_results.append(True)
        if len(self._recent_results) > 100:
            self._recent_results.pop(0)

    def record_failure(self, error: str = ""):
        """Record a failed request."""
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.last_failure = time.time()
        self.last_used = time.time()
        self._recent_results.append(False)
        if len(self._recent_results) > 100:
            self._recent_results.pop(0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API responses."""
        return {
            "proxy_id": self.proxy_id,
            "url": self.url,
            "country": self.country,
            "region": self.region,
            "tags": self.tags,
            "weight": self.weight,
            "success_rate": round(self.success_rate, 1),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "total_requests": self.total_requests,
            "consecutive_failures": self.consecutive_failures,
            "is_healthy": self.is_healthy,
            "disabled": self.disabled,
            "last_used": self.last_used,
        }


# ═══════════════════════════════════════════════════════════════
# PROXY ROTATOR — Main class
# ═══════════════════════════════════════════════════════════════

class ProxyRotator:
    """Thread-safe proxy rotator with pluggable rotation strategies.

    Supports:
    - Cyclic rotation (default)
    - Weighted rotation (prefer higher-weight proxies)
    - Random rotation
    - Sticky sessions (same proxy for same domain)
    - Health-aware rotation (skip unhealthy proxies)
    - Custom strategies via callable
    """

    def __init__(
        self,
        proxies: Optional[List[ProxyType]] = None,
        strategy: str = "cyclic",
    ):
        """Initialize the proxy rotator.

        Args:
            proxies: List of proxy URLs or Playwright-style proxy dicts.
            strategy: Rotation strategy — "cyclic", "weighted", "random", "sticky"
        """
        self._lock = Lock()
        self._proxies: List[ProxyType] = []
        self._health: Dict[str, ProxyHealth] = {}
        self._strategy = strategy
        self._current_index = 0
        self._domain_sticky: Dict[str, str] = {}  # domain → proxy_key
        self._stats = {
            "total_rotations": 0,
            "total_failovers": 0,
            "strategy_changes": 0,
        }

        if proxies:
            for proxy in proxies:
                self.add_proxy(proxy)

    def add_proxy(
        self,
        proxy: ProxyType,
        country: str = "",
        region: str = "",
        tags: Optional[List[str]] = None,
        weight: float = 1.0,
        max_requests_per_minute: int = 0,
    ) -> str:
        """Add a proxy to the rotation pool.

        Args:
            proxy: Proxy URL string or dict
            country: Country code (e.g., "US", "GB")
            region: Region/state
            tags: Custom tags for filtering
            weight: Selection weight (higher = more likely to be selected)
            max_requests_per_minute: Rate limit per proxy

        Returns:
            Proxy ID.
        """
        key = get_proxy_key(proxy)
        url = proxy if isinstance(proxy, str) else proxy.get("server", "")

        with self._lock:
            # Check for duplicates
            if key in self._health:
                logger.warning(f"Proxy already exists: {key}")
                return key

            self._proxies.append(proxy)
            self._health[key] = ProxyHealth(
                proxy_id=key,
                url=url,
                country=country,
                region=region,
                tags=tags or [],
                weight=weight,
                max_requests_per_minute=max_requests_per_minute,
            )

        logger.info(f"Added proxy: {key} (total: {len(self._proxies)})")
        return key

    def remove_proxy(self, proxy_id: str) -> bool:
        """Remove a proxy from the pool."""
        with self._lock:
            if proxy_id in self._health:
                del self._health[proxy_id]
                self._proxies = [p for p in self._proxies if get_proxy_key(p) != proxy_id]
                return True
        return False

    def get_proxy(
        self,
        domain: Optional[str] = None,
        country: Optional[str] = None,
        tags: Optional[List[str]] = None,
        with_failover: bool = True,
    ) -> Optional[ProxyType]:
        """Get the next proxy according to the rotation strategy.

        Args:
            domain: Domain for sticky sessions
            country: Filter by country
            tags: Filter by tags
            with_failover: If selected proxy is unhealthy, try next one

        Returns:
            Proxy URL/dict or None if no healthy proxy available.
        """
        with self._lock:
            if not self._proxies:
                return None

            self._stats["total_rotations"] += 1

            # Filter proxies by criteria
            candidates = self._filter_proxies(country, tags)

            if not candidates:
                logger.warning("No proxies match the filter criteria")
                return None

            # Strategy-based selection
            if self._strategy == "sticky" and domain:
                proxy = self._get_sticky_proxy(domain, candidates)
            elif self._strategy == "weighted":
                proxy = self._get_weighted_proxy(candidates)
            elif self._strategy == "random":
                proxy = self._get_random_proxy(candidates)
            else:  # cyclic
                proxy = self._get_cyclic_proxy(candidates)

            if proxy is None:
                return None

            key = get_proxy_key(proxy)
            health = self._health.get(key)

            # Health check with failover
            if with_failover and health and not health.is_healthy:
                self._stats["total_failovers"] += 1
                # Try to find a healthy proxy
                for candidate in candidates:
                    candidate_key = get_proxy_key(candidate)
                    candidate_health = self._health.get(candidate_key)
                    if candidate_health and candidate_health.is_healthy:
                        logger.debug(f"Failover: {key} → {candidate_key}")
                        return candidate

                # All unhealthy — return the original anyway (best effort)
                logger.warning(f"All proxies unhealthy, returning best-effort: {key}")

            return proxy

    def _filter_proxies(
        self,
        country: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[ProxyType]:
        """Filter proxies by country and tags."""
        if not country and not tags:
            return list(self._proxies)

        result = []
        for proxy in self._proxies:
            key = get_proxy_key(proxy)
            health = self._health.get(key)
            if not health:
                continue

            if country and health.country.upper() != country.upper():
                continue
            if tags and not any(t in health.tags for t in tags):
                continue

            result.append(proxy)
        return result

    def _get_cyclic_proxy(self, candidates: List[ProxyType]) -> ProxyType:
        """Cyclic round-robin selection."""
        proxy, self._current_index = cyclic_rotation(candidates, self._current_index)
        return proxy

    def _get_random_proxy(self, candidates: List[ProxyType]) -> ProxyType:
        """Random selection."""
        proxy, self._current_index = random_rotation(candidates, self._current_index)
        return proxy

    def _get_weighted_proxy(self, candidates: List[ProxyType]) -> ProxyType:
        """Weighted random selection — higher weight = more likely."""
        weights = []
        for proxy in candidates:
            key = get_proxy_key(proxy)
            health = self._health.get(key)
            w = health.weight if health else 1.0
            # Reduce weight for unhealthy proxies
            if health and not health.is_healthy:
                w *= 0.1
            weights.append(w)

        total = sum(weights)
        if total == 0:
            return random.choice(candidates)

        r = random.uniform(0, total)
        cumulative = 0
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                return candidates[i]
        return candidates[-1]

    def _get_sticky_proxy(self, domain: str, candidates: List[ProxyType]) -> ProxyType:
        """Sticky selection — same domain gets same proxy."""
        # Check if domain already has a sticky proxy
        if domain in self._domain_sticky:
            sticky_key = self._domain_sticky[domain]
            for proxy in candidates:
                if get_proxy_key(proxy) == sticky_key:
                    return proxy

        # Assign new sticky proxy
        proxy = self._get_weighted_proxy(candidates)
        self._domain_sticky[domain] = get_proxy_key(proxy)
        return proxy

    def record_result(
        self,
        proxy_id: str,
        success: bool,
        latency_ms: float = 0,
        status_code: int = 0,
        error: str = "",
    ):
        """Record the result of using a proxy.

        Args:
            proxy_id: The proxy identifier
            success: Whether the request succeeded
            latency_ms: Request latency in milliseconds
            status_code: HTTP status code
            error: Error message if failed
        """
        with self._lock:
            health = self._health.get(proxy_id)
            if health:
                if success:
                    health.record_success(latency_ms)
                else:
                    health.record_failure(error)

    def set_strategy(self, strategy: str) -> Dict[str, Any]:
        """Change the rotation strategy at runtime.

        Args:
            strategy: "cyclic", "weighted", "random", or "sticky"
        """
        valid = ("cyclic", "weighted", "random", "sticky")
        if strategy not in valid:
            return {"status": "error", "error": f"Invalid strategy. Valid: {valid}"}

        with self._lock:
            self._strategy = strategy
            self._stats["strategy_changes"] += 1

        return {"status": "success", "strategy": strategy}

    def get_stats(self) -> Dict[str, Any]:
        """Get rotator statistics."""
        with self._lock:
            healthy_count = sum(1 for h in self._health.values() if h.is_healthy)
            return {
                "total_proxies": len(self._proxies),
                "healthy_proxies": healthy_count,
                "unhealthy_proxies": len(self._proxies) - healthy_count,
                "strategy": self._strategy,
                "sticky_domains": len(self._domain_sticky),
                **self._stats,
            }

    def list_proxies(
        self,
        status: Optional[str] = None,
        country: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all proxies with their health status.

        Args:
            status: Filter by "healthy" or "unhealthy"
            country: Filter by country code
        """
        result = []
        for health in self._health.values():
            if status == "healthy" and not health.is_healthy:
                continue
            if status == "unhealthy" and health.is_healthy:
                continue
            if country and health.country.upper() != country.upper():
                continue
            result.append(health.to_dict())
        return result

    def get_proxy_health(self, proxy_id: str) -> Optional[Dict[str, Any]]:
        """Get health info for a specific proxy."""
        health = self._health.get(proxy_id)
        return health.to_dict() if health else None

    def enable_proxy(self, proxy_id: str) -> bool:
        """Enable a disabled proxy."""
        with self._lock:
            health = self._health.get(proxy_id)
            if health:
                health.disabled = False
                return True
        return False

    def disable_proxy(self, proxy_id: str) -> bool:
        """Disable a proxy (skip in rotation)."""
        with self._lock:
            health = self._health.get(proxy_id)
            if health:
                health.disabled = True
                return True
        return False

    def load_from_list(self, proxy_list: List[str]) -> Dict[str, Any]:
        """Load proxies from a list of URL strings.

        Args:
            proxy_list: List of proxy URLs

        Returns:
            Status with count of loaded proxies.
        """
        loaded = 0
        for proxy_url in proxy_list:
            try:
                self.add_proxy(proxy_url.strip())
                loaded += 1
            except Exception as e:
                logger.warning(f"Failed to add proxy '{proxy_url}': {e}")
        return {"status": "success", "loaded": loaded, "total": len(self._proxies)}

    def clear_sticky(self, domain: Optional[str] = None):
        """Clear sticky domain mappings.

        Args:
            domain: Specific domain to clear, or None to clear all.
        """
        with self._lock:
            if domain:
                self._domain_sticky.pop(domain, None)
            else:
                self._domain_sticky.clear()
