"""
Agent-OS Proxy Rotation Engine
Production-grade proxy pool management, health checking, and intelligent rotation.

Features:
  - Multi-source proxy loading: file, API endpoint, inline config
  - Health checking: latency, success rate, anonymity level, geo-location
  - Rotation strategies: round-robin, random, weighted, sticky, per-domain, least-used
  - Automatic failover: dead proxies auto-skipped, recovery probes
  - Rate limit tracking: per-proxy request counts, rotate before hitting limits
  - Geo-targeting: select proxies by country/region
  - Proxy types: HTTP, HTTPS, SOCKS5 with auth
  - Per-proxy statistics: requests, failures, avg latency, last used
  - Persistence: save/load proxy pools to disk
  - Session affinity: keep same proxy for a domain/session
  - Concurrent proxy testing with parallel health checks
"""
import asyncio
import json
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict
from urllib.parse import urlparse

logger = logging.getLogger("agent-os.proxy_rotation")


# ─── Proxy Data Model ───────────────────────────────────────

class ProxyStatus(str, Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"     # High latency or intermittent failures
    DEAD = "dead"             # Not responding
    TESTING = "testing"       # Health check in progress
    DISABLED = "disabled"     # Manually disabled


class ProxyType(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class RotationStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"       # Cycle through proxies in order
    RANDOM = "random"                 # Random selection
    WEIGHTED = "weighted"             # Weighted by success rate
    LEAST_USED = "least_used"         # Pick the least recently used
    STICKY = "sticky"                 # Same proxy per domain/session
    PER_DOMAIN = "per_domain"         # Consistent proxy per domain
    FASTEST = "fastest"               # Pick lowest latency
    GEO = "geo"                       # Pick by country/region


@dataclass
class ProxyInfo:
    """A single proxy server."""
    proxy_id: str
    url: str                           # Full proxy URL (scheme://user:pass@host:port)
    proxy_type: ProxyType = ProxyType.HTTP
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    country: str = ""                  # ISO country code
    region: str = ""
    tags: List[str] = field(default_factory=list)

    # Health status
    status: ProxyStatus = ProxyStatus.ACTIVE
    last_check: float = 0
    last_used: float = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    # Statistics
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0
    avg_latency_ms: float = 0
    last_latency_ms: float = 0

    # Rate limiting
    requests_this_window: int = 0
    window_start: float = 0
    max_requests_per_minute: int = 0  # 0 = unlimited

    # Weight for weighted rotation
    weight: float = 1.0

    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Parse URL components if not set."""
        if not self.host and self.url:
            parsed = urlparse(self.url)
            self.host = parsed.hostname or ""
            self.port = parsed.port or (443 if parsed.scheme == "https" else 1080 if "socks" in (parsed.scheme or "") else 8080)
            self.username = parsed.username or ""
            self.password = parsed.password or ""
            if "socks" in (parsed.scheme or ""):
                self.proxy_type = ProxyType.SOCKS5
            elif parsed.scheme == "https":
                self.proxy_type = ProxyType.HTTPS
            else:
                self.proxy_type = ProxyType.HTTP

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.total_successes / self.total_requests

    @property
    def is_available(self) -> bool:
        return self.status in (ProxyStatus.ACTIVE, ProxyStatus.DEGRADED)

    @property
    def is_rate_limited(self) -> bool:
        if self.max_requests_per_minute <= 0:
            return False
        # Reset window if needed
        if time.time() - self.window_start > 60:
            return False
        return self.requests_this_window >= self.max_requests_per_minute

    def to_dict(self) -> Dict:
        # Mask password
        masked_url = self.url
        if self.password:
            masked_url = masked_url.replace(self.password, "****")

        return {
            "proxy_id": self.proxy_id,
            "url": masked_url,
            "type": self.proxy_type.value,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "country": self.country,
            "region": self.region,
            "status": self.status.value,
            "success_rate": round(self.success_rate * 100, 1),
            "total_requests": self.total_requests,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "last_used_seconds_ago": round(time.time() - self.last_used, 1) if self.last_used else None,
            "consecutive_failures": self.consecutive_failures,
            "weight": self.weight,
            "tags": self.tags,
            "rate_limited": self.is_rate_limited,
        }

    def to_playwright_config(self) -> Dict[str, Any]:
        """Convert to Playwright proxy config."""
        config = {"server": f"{self.proxy_type.value}://{self.host}:{self.port}"}
        if self.username:
            config["username"] = self.username
        if self.password:
            config["password"] = self.password
        return config


# ─── Health Checker ─────────────────────────────────────────

class ProxyHealthChecker:
    """
    Async proxy health checker with parallel testing.

    Tests:
    1. TCP connectivity (can we connect?)
    2. HTTP request through proxy (does it work?)
    3. Latency measurement
    4. Anonymity check (does it leak our IP?)
    5. Geo-location detection
    """

    # URLs for health checks
    CHECK_URLS = [
        "http://httpbin.org/ip",
        "http://icanhazip.com",
        "http://ifconfig.me/ip",
        "http://api.ipify.org",
    ]

    GEO_CHECK_URLS = [
        "http://ip-api.com/json/",
        "http://ipinfo.io/json",
    ]

    def __init__(self, timeout_ms: int = 10000, check_urls: List[str] = None):
        self.timeout_ms = timeout_ms
        self.check_urls = check_urls or self.CHECK_URLS

    async def check(self, proxy: ProxyInfo) -> Dict[str, Any]:
        """
        Run a health check on a proxy.

        Returns:
            {
                "alive": bool,
                "latency_ms": float,
                "anonymity": "high" | "medium" | "low",
                "country": str,
                "error": str,
            }
        """
        proxy.status = ProxyStatus.TESTING
        start = time.time()

        try:
            # Use aiohttp with proxy
            import aiohttp

            proxy_url = proxy.url
            timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                check_url = random.choice(self.check_urls)

                try:
                    async with session.get(check_url, proxy=proxy_url) as resp:
                        latency = (time.time() - start) * 1000

                        if resp.status == 200:
                            body = await resp.text()

                            # Anonymity check
                            anonymity = "high"  # Default
                            headers = dict(resp.headers)
                            forwarded = headers.get("X-Forwarded-For", "")
                            via = headers.get("Via", "")
                            if forwarded or via:
                                anonymity = "medium"

                            proxy.status = ProxyStatus.ACTIVE
                            proxy.consecutive_failures = 0
                            proxy.consecutive_successes += 1
                            proxy.avg_latency_ms = (
                                proxy.avg_latency_ms * 0.7 + latency * 0.3
                                if proxy.avg_latency_ms > 0 else latency
                            )
                            proxy.last_latency_ms = latency
                            proxy.last_check = time.time()

                            return {
                                "alive": True,
                                "latency_ms": round(latency, 1),
                                "anonymity": anonymity,
                                "status_code": resp.status,
                                "response_preview": body[:100],
                            }
                        else:
                            proxy.consecutive_failures += 1
                            proxy.consecutive_successes = 0
                            return {"alive": False, "error": f"HTTP {resp.status}", "latency_ms": round(latency, 1)}

                except asyncio.TimeoutError:
                    proxy.consecutive_failures += 1
                    proxy.consecutive_successes = 0
                    return {"alive": False, "error": "Timeout", "latency_ms": self.timeout_ms}

                except Exception as e:
                    proxy.consecutive_failures += 1
                    proxy.consecutive_successes = 0
                    return {"alive": False, "error": str(e)[:200], "latency_ms": round((time.time() - start) * 1000, 1)}

        except ImportError:
            # Fallback: use curl subprocess
            return await self._check_with_curl(proxy, start)

        finally:
            # Update status based on failures
            if proxy.consecutive_failures >= 3:
                proxy.status = ProxyStatus.DEAD
            elif proxy.consecutive_failures >= 1:
                proxy.status = ProxyStatus.DEGRADED
            elif proxy.status == ProxyStatus.TESTING:
                proxy.status = ProxyStatus.ACTIVE

    async def _check_with_curl(self, proxy: ProxyInfo, start: float) -> Dict[str, Any]:
        """Fallback health check using curl."""
        proxy_arg = f"--proxy {proxy.url}"
        if proxy.username and proxy.password:
            proxy_arg = f"--proxy {proxy.proxy_type.value}://{proxy.host}:{proxy.port} --proxy-user {proxy.username}:{proxy.password}"

        check_url = random.choice(self.check_urls)
        cmd = f'curl -s -o /dev/null -w "%{{http_code}}" --max-time {self.timeout_ms // 1000} {proxy_arg} "{check_url}" 2>&1'

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_ms / 1000 + 5)
            latency = (time.time() - start) * 1000
            status_code = stdout.decode().strip()

            if status_code == "200":
                proxy.status = ProxyStatus.ACTIVE
                proxy.consecutive_failures = 0
                proxy.consecutive_successes += 1
                proxy.avg_latency_ms = proxy.avg_latency_ms * 0.7 + latency * 0.3 if proxy.avg_latency_ms > 0 else latency
                proxy.last_latency_ms = latency
                proxy.last_check = time.time()
                return {"alive": True, "latency_ms": round(latency, 1), "method": "curl"}
            else:
                proxy.consecutive_failures += 1
                proxy.consecutive_successes = 0
                return {"alive": False, "error": f"HTTP {status_code}", "latency_ms": round(latency, 1)}
        except Exception as e:
            proxy.consecutive_failures += 1
            proxy.consecutive_successes = 0
            return {"alive": False, "error": str(e)[:200], "latency_ms": round((time.time() - start) * 1000, 1)}

    async def check_batch(self, proxies: List[ProxyInfo], max_concurrent: int = 10) -> Dict[str, List]:
        """
        Check multiple proxies in parallel.

        Args:
            proxies: List of proxies to check.
            max_concurrent: Max parallel checks.
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def check_one(proxy):
            async with semaphore:
                result = await self.check(proxy)
                return proxy.proxy_id, result

        tasks = [check_one(p) for p in proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        alive = []
        dead = []
        for r in results:
            if isinstance(r, Exception):
                continue
            proxy_id, result = r
            if result.get("alive"):
                alive.append(proxy_id)
            else:
                dead.append(proxy_id)

        return {"alive": alive, "dead": dead, "total_checked": len(proxies)}

    async def detect_geo(self, proxy: ProxyInfo) -> Dict[str, Any]:
        """Detect proxy's exit IP geo-location."""
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = random.choice(self.GEO_CHECK_URLS)
                async with session.get(url, proxy=proxy.url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        country = data.get("country") or data.get("countryCode", "")
                        region = data.get("regionName") or data.get("region", "")
                        city = data.get("city", "")
                        ip = data.get("query") or data.get("ip", "")

                        proxy.country = country.upper()[:2] if country else ""
                        proxy.region = region
                        proxy.metadata["city"] = city
                        proxy.metadata["exit_ip"] = ip

                        return {"country": proxy.country, "region": region, "city": city, "ip": ip}
        except Exception as e:
            logger.debug(f"Geo detection failed for {proxy.proxy_id}: {e}")

        return {"country": "", "region": "", "error": "Detection failed"}


# ─── Proxy Pool ─────────────────────────────────────────────

class ProxyPool:
    """
    Manages a pool of proxy servers with health tracking.

    Supports:
    - Add/remove proxies dynamically
    - Load from file (JSON, CSV, plain list)
    - Load from API endpoint
    - Continuous health monitoring
    - Per-proxy statistics
    """

    def __init__(self, health_checker: ProxyHealthChecker = None):
        self._proxies: Dict[str, ProxyInfo] = {}
        self._health_checker = health_checker or ProxyHealthChecker()
        self._health_task: Optional[asyncio.Task] = None
        self._health_check_interval: float = 60  # seconds
        self._storage_dir = Path(os.path.expanduser("~/.agent-os/proxies"))
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def add(self, url: str, **kwargs) -> ProxyInfo:
        """Add a proxy to the pool."""
        proxy_id = kwargs.pop("proxy_id", str(uuid.uuid4())[:8])

        # Check for duplicate URL
        for p in self._proxies.values():
            if p.url == url:
                return p  # Already exists

        proxy = ProxyInfo(proxy_id=proxy_id, url=url, **kwargs)
        self._proxies[proxy_id] = proxy
        logger.info(f"Proxy added: {proxy_id} ({proxy.host}:{proxy.port})")
        return proxy

    def remove(self, proxy_id: str) -> bool:
        """Remove a proxy from the pool."""
        if proxy_id in self._proxies:
            del self._proxies[proxy_id]
            return True
        return False

    def get(self, proxy_id: str) -> Optional[ProxyInfo]:
        """Get a proxy by ID."""
        return self._proxies.get(proxy_id)

    def get_all(self, status: str = None, country: str = None) -> List[ProxyInfo]:
        """Get all proxies with optional filters."""
        proxies = list(self._proxies.values())
        if status:
            proxies = [p for p in proxies if p.status.value == status]
        if country:
            proxies = [p for p in proxies if p.country.upper() == country.upper()]
        return proxies

    def get_available(self, country: str = None, tags: List[str] = None) -> List[ProxyInfo]:
        """Get available (active/degraded) proxies."""
        available = [p for p in self._proxies.values() if p.is_available and not p.is_rate_limited]
        if country:
            available = [p for p in available if p.country.upper() == country.upper()]
        if tags:
            available = [p for p in available if any(t in p.tags for t in tags)]
        return available

    def load_from_file(self, filepath: str, proxy_type: str = "http") -> int:
        """
        Load proxies from file. Supports:
        - JSON: [{"url": "http://...", "country": "US"}, ...]
        - Plain text: one proxy URL per line
        - CSV: url,user,pass,country
        """
        path = Path(filepath)
        if not path.exists():
            logger.error(f"Proxy file not found: {filepath}")
            return 0

        count = 0
        content = path.read_text().strip()

        if path.suffix == ".json":
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, str):
                            self.add(item)
                            count += 1
                        elif isinstance(item, dict):
                            url = item.get("url", "")
                            if url:
                                self.add(url, **{k: v for k, v in item.items() if k != "url"})
                                count += 1
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in proxy file: {filepath}")

        elif path.suffix == ".csv":
            for line in content.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",")
                if len(parts) >= 1:
                    url = parts[0].strip()
                    if url:
                        kwargs = {}
                        if len(parts) >= 2:
                            kwargs["username"] = parts[1].strip()
                        if len(parts) >= 3:
                            kwargs["password"] = parts[2].strip()
                        if len(parts) >= 4:
                            kwargs["country"] = parts[3].strip()
                        self.add(url, **kwargs)
                        count += 1

        else:
            # Plain text: one URL per line
            for line in content.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                self.add(line)
                count += 1

        logger.info(f"Loaded {count} proxies from {filepath}")
        return count

    async def load_from_api(self, api_url: str, api_key: str = None) -> int:
        """Load proxies from an API endpoint."""
        try:
            import aiohttp
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        count = 0
                        if isinstance(data, list):
                            for item in data:
                                url = item if isinstance(item, str) else item.get("url", "")
                                if url:
                                    kwargs = {k: v for k, v in item.items() if k != "url"} if isinstance(item, dict) else {}
                                    self.add(url, **kwargs)
                                    count += 1
                        elif isinstance(data, dict) and "proxies" in data:
                            for item in data["proxies"]:
                                url = item if isinstance(item, str) else item.get("url", "")
                                if url:
                                    kwargs = {k: v for k, v in item.items() if k != "url"} if isinstance(item, dict) else {}
                                    self.add(url, **kwargs)
                                    count += 1
                        logger.info(f"Loaded {count} proxies from API")
                        return count
                    else:
                        logger.error(f"API returned {resp.status}")
                        return 0
        except Exception as e:
            logger.error(f"Failed to load proxies from API: {e}")
            return 0

    async def check_all(self, max_concurrent: int = 10) -> Dict[str, Any]:
        """Run health check on all proxies."""
        proxies = list(self._proxies.values())
        if not proxies:
            return {"status": "no_proxies", "checked": 0}

        results = await self._health_checker.check_batch(proxies, max_concurrent)

        return {
            "status": "success",
            "checked": len(proxies),
            "alive": len(results["alive"]),
            "dead": len(results["dead"]),
            "alive_ids": results["alive"],
            "dead_ids": results["dead"],
        }

    async def start_health_monitoring(self, interval_seconds: float = 60, max_concurrent: int = 10):
        """Start background health monitoring."""
        self._health_check_interval = interval_seconds
        if self._health_task:
            self._health_task.cancel()

        async def monitor_loop():
            while True:
                try:
                    await asyncio.sleep(self._health_check_interval)
                    # Only check active/degraded proxies
                    to_check = [p for p in self._proxies.values() if p.status != ProxyStatus.DISABLED]
                    if to_check:
                        await self._health_checker.check_batch(to_check, max_concurrent)
                        dead = [p for p in to_check if p.status == ProxyStatus.DEAD]
                        if dead:
                            logger.info(f"Health check: {len(dead)} proxies marked dead")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Health monitor error: {e}")
                    await asyncio.sleep(10)

        self._health_task = asyncio.create_task(monitor_loop())
        logger.info(f"Health monitoring started (interval: {interval_seconds}s)")

    def stop_health_monitoring(self):
        """Stop background health monitoring."""
        if self._health_task:
            self._health_task.cancel()
            self._health_task = None

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        proxies = list(self._proxies.values())
        by_status = defaultdict(int)
        by_country = defaultdict(int)
        by_type = defaultdict(int)

        for p in proxies:
            by_status[p.status.value] += 1
            if p.country:
                by_country[p.country] += 1
            by_type[p.proxy_type.value] += 1

        total_requests = sum(p.total_requests for p in proxies)
        total_successes = sum(p.total_successes for p in proxies)

        return {
            "total": len(proxies),
            "by_status": dict(by_status),
            "by_country": dict(by_country),
            "by_type": dict(by_type),
            "available": len([p for p in proxies if p.is_available]),
            "total_requests": total_requests,
            "total_successes": total_successes,
            "overall_success_rate": round(total_successes / max(1, total_requests) * 100, 1),
        }

    def save(self, filename: str = "proxies.json"):
        """Save proxy pool to disk."""
        path = self._storage_dir / filename
        data = []
        for p in self._proxies.values():
            d = {
                "url": p.url,
                "proxy_type": p.proxy_type.value,
                "country": p.country,
                "region": p.region,
                "tags": p.tags,
                "weight": p.weight,
                "max_requests_per_minute": p.max_requests_per_minute,
            }
            data.append(d)

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        return {"status": "success", "saved": len(data), "path": str(path)}

    def load(self, filename: str = "proxies.json"):
        """Load proxy pool from disk."""
        path = self._storage_dir / filename
        if not path.exists():
            return {"status": "error", "error": f"File not found: {path}"}

        return {"status": "success", "loaded": self.load_from_file(str(path))}


# ─── Proxy Rotator ──────────────────────────────────────────

class ProxyRotator:
    """
    Intelligent proxy rotation engine.

    Selects the best proxy based on strategy, tracks usage, handles failover.

    Usage:
        pool = ProxyPool()
        pool.add("http://proxy1:8080")
        pool.add("http://proxy2:8080")

        rotator = ProxyRotator(pool, strategy="weighted")

        # Get next proxy
        proxy = await rotator.get_proxy()

        # Record result
        rotator.record_result(proxy.proxy_id, success=True, latency_ms=150)

        # Get proxy for specific domain (sticky)
        proxy = await rotator.get_proxy(domain="example.com")
    """

    def __init__(
        self,
        pool: ProxyPool,
        strategy: str = "round_robin",
        max_retries_per_proxy: int = 2,
        fail_threshold: int = 3,
        recovery_probe_interval: float = 120,
    ):
        self.pool = pool
        self.strategy = RotationStrategy(strategy)
        self.max_retries_per_proxy = max_retries_per_proxy
        self.fail_threshold = fail_threshold
        self.recovery_probe_interval = recovery_probe_interval

        # Round-robin index
        self._rr_index = 0

        # Sticky sessions: domain -> proxy_id
        self._sticky_map: Dict[str, str] = {}

        # Session affinity: session_id -> proxy_id
        self._session_map: Dict[str, str] = {}

        # Failed proxy tracking (for automatic retry)
        self._failed_in_request: Dict[str, Set[str]] = {}  # request_id -> set of failed proxy_ids

        # Stats
        self._rotation_count = 0
        self._failover_count = 0

    async def get_proxy(
        self,
        domain: str = None,
        session_id: str = None,
        country: str = None,
        tags: List[str] = None,
        exclude: List[str] = None,
    ) -> Optional[ProxyInfo]:
        """
        Get the next proxy based on rotation strategy.

        Args:
            domain: For sticky/per-domain strategies.
            session_id: Session affinity (same proxy for session).
            country: Geo-targeting filter.
            tags: Tag filter.
            exclude: Proxy IDs to exclude (already tried).
        """
        available = self.pool.get_available(country=country, tags=tags)
        if not available:
            return None

        # Filter out excluded
        if exclude:
            exclude_set = set(exclude)
            available = [p for p in available if p.proxy_id not in exclude_set]

        if not available:
            return None

        # Session affinity check
        if session_id and session_id in self._session_map:
            sid_proxy = self._session_map[session_id]
            for p in available:
                if p.proxy_id == sid_proxy and p.is_available:
                    return p

        # Domain sticky check
        if domain and self.strategy in (RotationStrategy.STICKY, RotationStrategy.PER_DOMAIN):
            if domain in self._sticky_map:
                sticky_id = self._sticky_map[domain]
                for p in available:
                    if p.proxy_id == sticky_id and p.is_available:
                        return p

        # Apply strategy
        proxy = self._select_by_strategy(available)

        if proxy:
            self._rotation_count += 1
            proxy.last_used = time.time()

            # Update sticky maps
            if domain:
                self._sticky_map[domain] = proxy.proxy_id
            if session_id:
                self._session_map[session_id] = proxy.proxy_id

        return proxy

    async def get_proxy_with_retry(
        self,
        request_id: str = None,
        domain: str = None,
        session_id: str = None,
        country: str = None,
        max_attempts: int = None,
    ) -> Tuple[Optional[ProxyInfo], List[str]]:
        """
        Get a proxy, with automatic failover if previous proxies failed.

        Returns (proxy, list_of_tried_ids).
        If all proxies exhausted, returns (None, all_tried_ids).
        """
        request_id = request_id or str(uuid.uuid4())[:8]
        max_attempts = max_attempts or (self.max_retries_per_proxy + 1)
        tried = set()

        for attempt in range(max_attempts):
            proxy = await self.get_proxy(
                domain=domain,
                session_id=session_id,
                country=country,
                exclude=list(tried),
            )

            if not proxy:
                return None, list(tried)

            tried.add(proxy.proxy_id)

            # Quick availability check
            if proxy.status == ProxyStatus.DEAD:
                continue

            return proxy, list(tried)

        self._failover_count += 1
        return None, list(tried)

    def record_result(
        self,
        proxy_id: str,
        success: bool,
        latency_ms: float = 0,
        status_code: int = 0,
        error: str = "",
    ):
        """Record the result of using a proxy."""
        proxy = self.pool.get(proxy_id)
        if not proxy:
            return

        proxy.total_requests += 1
        proxy.requests_this_window += 1

        # Reset rate window
        if time.time() - proxy.window_start > 60:
            proxy.requests_this_window = 1
            proxy.window_start = time.time()

        if success:
            proxy.total_successes += 1
            proxy.consecutive_successes += 1
            proxy.consecutive_failures = 0

            # Update latency
            if latency_ms > 0:
                proxy.avg_latency_ms = (
                    proxy.avg_latency_ms * 0.7 + latency_ms * 0.3
                    if proxy.avg_latency_ms > 0 else latency_ms
                )
                proxy.last_latency_ms = latency_ms

            # Restore status if degraded
            if proxy.status == ProxyStatus.DEGRADED:
                proxy.status = ProxyStatus.ACTIVE
        else:
            proxy.total_failures += 1
            proxy.consecutive_failures += 1
            proxy.consecutive_successes = 0

            # Update status
            if proxy.consecutive_failures >= self.fail_threshold:
                proxy.status = ProxyStatus.DEAD
                logger.warning(f"Proxy {proxy_id} marked DEAD after {proxy.consecutive_failures} consecutive failures")
                # Clear sticky assignments for this proxy
                for domain, pid in list(self._sticky_map.items()):
                    if pid == proxy_id:
                        del self._sticky_map[domain]
            elif proxy.consecutive_failures >= 1:
                proxy.status = ProxyStatus.DEGRADED

    def enable(self, proxy_id: str) -> bool:
        """Re-enable a disabled/dead proxy."""
        proxy = self.pool.get(proxy_id)
        if proxy:
            proxy.status = ProxyStatus.ACTIVE
            proxy.consecutive_failures = 0
            return True
        return False

    def disable(self, proxy_id: str) -> bool:
        """Disable a proxy."""
        proxy = self.pool.get(proxy_id)
        if proxy:
            proxy.status = ProxyStatus.DISABLED
            return True
        return False

    def set_strategy(self, strategy: str):
        """Change rotation strategy."""
        self.strategy = RotationStrategy(strategy)

    def _select_by_strategy(self, available: List[ProxyInfo]) -> Optional[ProxyInfo]:
        """Select proxy based on current strategy."""
        if not available:
            return None

        if self.strategy == RotationStrategy.ROUND_ROBIN:
            self._rr_index = self._rr_index % len(available)
            proxy = available[self._rr_index]
            self._rr_index += 1
            return proxy

        elif self.strategy == RotationStrategy.RANDOM:
            return random.choice(available)

        elif self.strategy == RotationStrategy.WEIGHTED:
            weights = [p.weight * p.success_rate for p in available]
            total = sum(weights)
            if total <= 0:
                return random.choice(available)
            r = random.uniform(0, total)
            cumulative = 0
            for p, w in zip(available, weights):
                cumulative += w
                if r <= cumulative:
                    return p
            return available[-1]

        elif self.strategy == RotationStrategy.LEAST_USED:
            return min(available, key=lambda p: p.total_requests)

        elif self.strategy == RotationStrategy.FASTEST:
            # Prefer low-latency proxies (among active ones)
            with_latency = [p for p in available if p.avg_latency_ms > 0]
            if with_latency:
                return min(with_latency, key=lambda p: p.avg_latency_ms)
            return random.choice(available)

        elif self.strategy in (RotationStrategy.STICKY, RotationStrategy.PER_DOMAIN):
            # These are handled by the caller (get_proxy) via sticky maps
            return random.choice(available)

        elif self.strategy == RotationStrategy.GEO:
            # Geo is handled by the caller via country filter
            return random.choice(available)

        return random.choice(available)

    def get_stats(self) -> Dict[str, Any]:
        """Get rotation statistics."""
        return {
            "strategy": self.strategy.value,
            "rotation_count": self._rotation_count,
            "failover_count": self._failover_count,
            "sticky_sessions": len(self._sticky_map),
            "session_affinities": len(self._session_map),
            "pool_stats": self.pool.get_stats(),
        }


# ─── Proxy Manager (Main Entry Point) ──────────────────────

class ProxyManager:
    """
    High-level proxy management combining pool, rotator, and health checker.

    Usage:
        pm = ProxyManager()

        # Add proxies
        pm.add_proxy("http://user:pass@proxy1:8080", country="US")
        pm.add_proxy("socks5://proxy2:1080", country="DE")
        pm.load_proxies("proxies.txt")

        # Set strategy
        pm.set_strategy("weighted")

        # Get proxy for browser
        proxy = await pm.get_proxy(domain="example.com")
        config = proxy.to_playwright_config()

        # After use
        pm.record_result(proxy.proxy_id, success=True, latency_ms=200)
    """

    def __init__(self, strategy: str = "round_robin"):
        self.pool = ProxyPool()
        self.health_checker = ProxyHealthChecker()
        self.rotator = ProxyRotator(self.pool, strategy=strategy)
        self._started = False

    async def start(self, health_check_interval: float = 60):
        """Start health monitoring."""
        if not self._started:
            await self.pool.start_health_monitoring(interval_seconds=health_check_interval)
            self._started = True

    async def stop(self):
        """Stop health monitoring."""
        self.pool.stop_health_monitoring()
        self._started = False

    def add_proxy(self, url: str, **kwargs) -> Dict[str, Any]:
        """Add a proxy."""
        proxy = self.pool.add(url, **kwargs)
        return {"status": "success", "proxy": proxy.to_dict()}

    def remove_proxy(self, proxy_id: str) -> Dict[str, Any]:
        """Remove a proxy."""
        if self.pool.remove(proxy_id):
            return {"status": "success", "removed": proxy_id}
        return {"status": "error", "error": f"Proxy not found: {proxy_id}"}

    def load_proxies(self, filepath: str, proxy_type: str = "http") -> Dict[str, Any]:
        """Load proxies from file."""
        count = self.pool.load_from_file(filepath, proxy_type)
        return {"status": "success", "loaded": count}

    async def load_from_api(self, api_url: str, api_key: str = None) -> Dict[str, Any]:
        """Load proxies from API."""
        count = await self.pool.load_from_api(api_url, api_key)
        return {"status": "success", "loaded": count}

    async def get_proxy(
        self,
        domain: str = None,
        session_id: str = None,
        country: str = None,
        tags: List[str] = None,
        with_failover: bool = True,
    ) -> Dict[str, Any]:
        """
        Get the best available proxy.

        Args:
            domain: Domain for sticky rotation.
            session_id: Session for affinity.
            country: Geo-target (ISO code, e.g., "US", "DE", "JP").
            tags: Tag filter.
            with_failover: Auto-retry with different proxy on failure.
        """
        if with_failover:
            proxy, tried = await self.rotator.get_proxy_with_retry(
                domain=domain,
                session_id=session_id,
                country=country,
            )
        else:
            proxy = await self.rotator.get_proxy(
                domain=domain,
                session_id=session_id,
                country=country,
                tags=tags,
            )
            tried = []

        if not proxy:
            return {
                "status": "error",
                "error": "No available proxies",
                "tried": tried,
                "pool_stats": self.pool.get_stats(),
            }

        return {
            "status": "success",
            "proxy": proxy.to_dict(),
            "playwright_config": proxy.to_playwright_config(),
            "strategy": self.rotator.strategy.value,
            "tried_count": len(tried),
        }

    def record_result(
        self,
        proxy_id: str,
        success: bool,
        latency_ms: float = 0,
        status_code: int = 0,
        error: str = "",
    ) -> Dict[str, Any]:
        """Record proxy usage result."""
        self.rotator.record_result(proxy_id, success, latency_ms, status_code, error)
        proxy = self.pool.get(proxy_id)
        return {
            "status": "success",
            "proxy_id": proxy_id,
            "proxy_status": proxy.status.value if proxy else "unknown",
            "success_rate": round(proxy.success_rate * 100, 1) if proxy else 0,
        }

    async def check_proxy(self, proxy_id: str) -> Dict[str, Any]:
        """Run health check on a specific proxy."""
        proxy = self.pool.get(proxy_id)
        if not proxy:
            return {"status": "error", "error": f"Proxy not found: {proxy_id}"}
        result = await self.health_checker.check(proxy)
        return {"status": "success", "proxy_id": proxy_id, **result}

    async def check_all(self) -> Dict[str, Any]:
        """Run health check on all proxies."""
        return await self.pool.check_all()

    def set_strategy(self, strategy: str) -> Dict[str, Any]:
        """Change rotation strategy."""
        try:
            self.rotator.set_strategy(strategy)
            return {"status": "success", "strategy": strategy}
        except ValueError:
            return {"status": "error", "error": f"Invalid strategy: {strategy}. Valid: {[s.value for s in RotationStrategy]}"}

    def enable_proxy(self, proxy_id: str) -> Dict[str, Any]:
        """Re-enable a dead/disabled proxy."""
        if self.rotator.enable(proxy_id):
            return {"status": "success", "proxy_id": proxy_id, "proxy_status": "active"}
        return {"status": "error", "error": f"Proxy not found: {proxy_id}"}

    def disable_proxy(self, proxy_id: str) -> Dict[str, Any]:
        """Disable a proxy."""
        if self.rotator.disable(proxy_id):
            return {"status": "success", "proxy_id": proxy_id, "proxy_status": "disabled"}
        return {"status": "error", "error": f"Proxy not found: {proxy_id}"}

    def list_proxies(self, status: str = None, country: str = None) -> Dict[str, Any]:
        """List all proxies with stats."""
        proxies = self.pool.get_all(status=status, country=country)
        return {
            "status": "success",
            "proxies": [p.to_dict() for p in proxies],
            "count": len(proxies),
            "pool_stats": self.pool.get_stats(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive proxy stats."""
        return {"status": "success", **self.rotator.get_stats()}

    def save(self, filename: str = "proxies.json") -> Dict[str, Any]:
        """Save proxy pool to disk."""
        return self.pool.save(filename)

    def load(self, filename: str = "proxies.json") -> Dict[str, Any]:
        """Load proxy pool from disk."""
        return self.pool.load(filename)
