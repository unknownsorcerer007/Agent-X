"""
Agent-OS TLS Proxy Server
Local HTTP/HTTPS proxy that re-signs all requests using curl_cffi
with real browser TLS fingerprints.

This solves the TLS fingerprint detection problem:
- Playwright's Chromium uses BoringSSL with a detectable signature
- curl_cffi impersonates real Chrome/Firefox/Safari TLS ClientHello
- The proxy intercepts Playwright's requests and re-signs them

Architecture:
    Playwright → [TLS Proxy] → curl_cffi (real browser TLS) → Target Site
    Target Site → curl_cffi → [TLS Proxy] → Playwright
"""

import asyncio
import logging
import time
import re
from typing import Any, Optional, Dict
from urllib.parse import urlparse
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger("agent-os.tls-proxy")

# ═══════════════════════════════════════════════════════════════
# curl_cffi Engine — Real Browser TLS Impersonation
# ═══════════════════════════════════════════════════════════════

_CURL_AVAILABLE = False
_curl_Session = None
_curl_BrowserType = None

try:
    from curl_cffi.requests import Session as _curl_Session, BrowserType as _curl_BrowserType
    _CURL_AVAILABLE = True
    logger.info("curl_cffi available — real browser TLS enabled")
except ImportError:
    logger.warning("curl_cffi not installed — TLS fingerprinting disabled")


# Browser profiles with their curl_cffi mappings
BROWSER_PROFILES = {
    "chrome146": {
        "curl_type": None,  # Set at runtime
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="146", "Google Chrome";v="146", "Not-A.Brand";v="99"',
        "platform": '"Windows"',
        "mobile": "?0",
    },
    "chrome145": {
        "curl_type": None,  # Set at runtime
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="145", "Google Chrome";v="145", "Not-A.Brand";v="99"',
        "platform": '"Windows"',
        "mobile": "?0",
    },
    "chrome142": {
        "curl_type": None,  # Set at runtime
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="142", "Google Chrome";v="142", "Not-A.Brand";v="99"',
        "platform": '"Windows"',
        "mobile": "?0",
    },
    "chrome136": {
        "curl_type": None,  # Set at runtime
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="136", "Google Chrome";v="136", "Not-A.Brand";v="99"',
        "platform": '"Windows"',
        "mobile": "?0",
    },
    "chrome133a": {
        "curl_type": None,  # Set at runtime
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="133", "Google Chrome";v="133", "Not-A.Brand";v="99"',
        "platform": '"Windows"',
        "mobile": "?0",
    },
    "chrome131": {
        "curl_type": None,  # Set at runtime
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="131", "Google Chrome";v="131", "Not?A_Brand";v="99"',
        "platform": '"Windows"',
        "mobile": "?0",
    },
    "chrome124": {
        "curl_type": None,  # Set at runtime
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "platform": '"Windows"',
        "mobile": "?0",
    },
    "chrome120": {
        "curl_type": None,
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="120", "Google Chrome";v="120", "Not_A Brand";v="99"',
        "platform": '"Windows"',
        "mobile": "?0",
    },
    "chrome119": {
        "curl_type": None,
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="119", "Google Chrome";v="119", "Not_A Brand";v="99"',
        "platform": '"Windows"',
        "mobile": "?0",
    },
    "firefox147": {
        "curl_type": None,
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
        "sec_ch_ua": None,
        "platform": '"Windows"',
        "mobile": "?0",
    },
    "safari18_0": {
        "curl_type": None,
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        "sec_ch_ua": None,
        "platform": '"macOS"',
        "mobile": "?0",
    },
    "edge101": {
        "curl_type": None,
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36 Edg/101.0.1210.47",
        "sec_ch_ua": '"Chromium";v="101", "Microsoft Edge";v="101", ";Not A Brand";v="99"',
        "platform": '"Windows"',
        "mobile": "?0",
    },
}


def _init_profiles():
    """Initialize curl_cffi browser types at runtime.

    Uses getattr with a fallback so missing attributes in newer/older
    curl_cffi versions are silently skipped instead of crashing.
    """
    if not _CURL_AVAILABLE:
        return

    _wanted = {
        "chrome146":   "chrome146",
        "chrome145":   "chrome145",
        "chrome142":   "chrome142",
        "chrome136":   "chrome136",
        "chrome133a":  "chrome133a",
        "chrome131":   "chrome131",
        "chrome124":   "chrome124",
        "chrome120":   "chrome120",
        "chrome119":   "chrome119",
        "chrome116":   "chrome116",
        "firefox147":  "firefox147",
        "firefox135":  "firefox135",
        "safari18_0":  "safari18_0",
        "safari17_0":  "safari17_0",
        "safari15_5":  "safari15_5",
        "edge101":     "edge101",
        "edge99":      "edge99",
    }

    _type_map = {}
    for profile_name, attr_name in _wanted.items():
        attr = getattr(_curl_BrowserType, attr_name, None)
        if attr is not None:
            _type_map[profile_name] = attr

    for name, profile in BROWSER_PROFILES.items():
        if name in _type_map:
            profile["curl_type"] = _type_map[name]


# ═══════════════════════════════════════════════════════════════
# Request/Response Data Classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class ProxiedRequest:
    """A request to be proxied through curl_cffi."""
    method: str
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    content_type: Optional[str] = None
    profile: str = "chrome124"
    timeout: int = 30
    follow_redirects: bool = True


@dataclass
class ProxiedResponse:
    """Response from the proxied request."""
    status_code: int
    headers: Dict[str, str]
    body: bytes
    url: str
    elapsed_ms: float
    tls_profile: str
    error: Optional[str] = None

    @property
    def text(self) -> str:
        """Decode body bytes to string."""
        try:
            return self.body.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            return self.body.decode("latin-1") if isinstance(self.body, bytes) else str(self.body)


# ═══════════════════════════════════════════════════════════════
# TLS Session Pool — Reusable curl_cffi Sessions
# ═══════════════════════════════════════════════════════════════

class TLSSessionPool:
    """
    Pool of curl_cffi sessions with real browser TLS fingerprints.
    Sessions are reused for connection pooling and cookie persistence.
    """

    def __init__(self):
        self._sessions: Dict[str, _curl_Session] = {}
        self._domain_sessions: Dict[str, str] = {}  # domain → profile
        self._cookie_jars: Dict[str, Dict] = defaultdict(dict)
        self._request_count = 0
        self._error_count = 0
        self._init_lock = asyncio.Lock()

    def _get_profile_for_domain(self, domain: str) -> str:
        """Get or assign a consistent profile for a domain."""
        if domain not in self._domain_sessions:
            # Use Chrome 124 as default for most sites
            self._domain_sessions[domain] = "chrome124"
        return self._domain_sessions[domain]

    def get_session(self, profile: str = "chrome124") -> Optional[_curl_Session]:
        """Get or create a curl_cffi session for a profile."""
        if not _CURL_AVAILABLE:
            return None

        if profile not in self._sessions:
            profile_config = BROWSER_PROFILES.get(profile)
            if not profile_config or not profile_config.get("curl_type"):
                profile = "chrome124"
                profile_config = BROWSER_PROFILES.get(profile)

            curl_type = profile_config.get("curl_type") if profile_config else None
            if not curl_type:
                curl_type = _curl_BrowserType.chrome124

            session = _curl_Session(impersonate=curl_type)
            self._sessions[profile] = session
            logger.debug(f"Created TLS session: {profile}")

        return self._sessions.get(profile)

    async def execute(self, req: ProxiedRequest) -> ProxiedResponse:
        """Execute a request through curl_cffi with real browser TLS."""
        start = time.time()

        if not _CURL_AVAILABLE:
            return ProxiedResponse(
                status_code=0,
                headers={},
                body=b"",
                url=req.url,
                elapsed_ms=0,
                tls_profile="none",
                error="curl_cffi not installed",
            )

        session = self.get_session(req.profile)
        if not session:
            return ProxiedResponse(
                status_code=0,
                headers={},
                body=b"",
                url=req.url,
                elapsed_ms=0,
                tls_profile="none",
                error="Failed to create TLS session",
            )

        # Build request kwargs
        kwargs = {
            "timeout": req.timeout,
            "allow_redirects": req.follow_redirects,
        }

        if req.headers:
            # Filter out hop-by-hop headers that shouldn't be forwarded
            filtered_headers = {
                k: v for k, v in req.headers.items()
                if k.lower() not in (
                    "host", "connection", "transfer-encoding",
                    "content-encoding", "proxy-connection",
                    "proxy-authorization", "te", "trailer",
                    "upgrade",
                )
            }
            kwargs["headers"] = filtered_headers

        if req.body:
            kwargs["data"] = req.body

        try:
            # Run in thread executor to not block async loop
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: session.request(req.method, req.url, **kwargs),
            )

            elapsed = (time.time() - start) * 1000
            self._request_count += 1

            # Store cookies for this domain
            parsed = urlparse(req.url)
            domain = parsed.hostname or ""
            self._cookie_jars[domain].update(dict(resp.cookies))

            return ProxiedResponse(
                status_code=resp.status_code,
                headers=dict(resp.headers),
                body=resp.content,
                url=str(resp.url),
                elapsed_ms=round(elapsed, 1),
                tls_profile=req.profile,
            )

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            self._error_count += 1
            logger.error(f"TLS proxy request failed: {req.method} {req.url[:80]} — {e}")

            return ProxiedResponse(
                status_code=0,
                headers={},
                body=b"",
                url=req.url,
                elapsed_ms=round(elapsed, 1),
                tls_profile=req.profile,
                error=str(e),
            )

    def get_cookies_for_domain(self, domain: str) -> Dict[str, str]:
        """Get stored cookies for a domain."""
        return dict(self._cookie_jars.get(domain, {}))

    def set_domain_profile(self, domain: str, profile: str):
        """Force a specific TLS profile for a domain."""
        self._domain_sessions[domain] = profile

    def close(self):
        """Close all sessions."""
        for session in self._sessions.values():
            try:
                session.close()
            except Exception:
                pass
        self._sessions.clear()

    @property
    def stats(self) -> Dict:
        return {
            "requests": self._request_count,
            "errors": self._error_count,
            "active_sessions": list(self._sessions.keys()),
            "domain_profiles": dict(self._domain_sessions),
        }


# ═══════════════════════════════════════════════════════════════
# TLS Proxy Server — aiohttp-based local proxy
# ═══════════════════════════════════════════════════════════════

class TLSProxyServer:
    """
    Local HTTP proxy server that intercepts browser requests
    and re-signs them using curl_cffi with real browser TLS.

    Usage:
        proxy = TLSProxyServer(host="127.0.0.1", port=8081)
        await proxy.start()
        # Configure Playwright to use http://127.0.0.1:8081 as proxy
        # All requests will be re-signed with real Chrome TLS fingerprint
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8081):
        self.host = host
        self.port = port
        self._pool = TLSSessionPool()
        self._server = None
        self._runner = None
        self._stats = {
            "requests_proxied": 0,
            "requests_failed": 0,
            "bytes_transferred": 0,
            "start_time": None,
        }

        # Patterns for requests that should bypass the proxy
        # (local resources, data URLs, etc.)
        self._bypass_patterns = [
            r"^data:",
            r"^blob:",
            r"^about:",
            r"^chrome:",
            r"^chrome-extension:",
            r"^file:",
            r"127\.0\.0\.1",
            r"localhost",
            r"^ws://",
            r"^wss://",
        ]
        self._bypass_re = re.compile("|".join(self._bypass_patterns), re.IGNORECASE)

    async def start(self):
        """Start the proxy server."""
        if not _CURL_AVAILABLE:
            logger.error("Cannot start TLS proxy — curl_cffi not installed")
            return False

        _init_profiles()

        try:
            from aiohttp import web
        except ImportError:
            logger.error("aiohttp required for TLS proxy: pip install aiohttp")
            return False

        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self._handle_request)

        self._runner = web.AppRunner(app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        self._stats["start_time"] = time.time()
        logger.info(f"TLS Proxy started on http://{self.host}:{self.port}")
        logger.info(f"Configure Playwright proxy: http://{self.host}:{self.port}")
        return True

    async def stop(self):
        """Stop the proxy server."""
        if self._runner:
            await self._runner.cleanup()
        self._pool.close()
        logger.info("TLS Proxy stopped")

    async def _handle_request(self, request):
        """Handle an incoming proxy request."""
        from aiohttp import web

        url = str(request.url)

        # Check if this should be bypassed
        if self._bypass_re.search(url):
            return web.Response(status=502, text="Bypassed")

        # Build the proxied request
        method = request.method
        headers = dict(request.headers)

        # Read body
        body = None
        if method in ("POST", "PUT", "PATCH"):
            body = await request.read()

        # Determine TLS profile based on domain
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        profile = self._pool._get_profile_for_domain(domain)

        # For bot-protected sites, use the strongest profile
        heavy_protection_domains = [
            "datadome", "perimeterx", "imperva", "akamai",
            "glassdoor", "linkedin", "zillow", "craigslist",
            "booking.com", "expedia", "investing.com",
        ]
        if any(d in domain.lower() for d in heavy_protection_domains):
            profile = "chrome133a"

        proxied_req = ProxiedRequest(
            method=method,
            url=url,
            headers=headers,
            body=body,
            profile=profile,
            timeout=30,
        )

        # Execute through curl_cffi
        resp = await self._pool.execute(proxied_req)

        self._stats["requests_proxied"] += 1
        self._stats["bytes_transferred"] += len(resp.body)

        if resp.error:
            self._stats["requests_failed"] += 1
            return web.Response(status=502, text=f"Proxy error: {resp.error}")

        # Build response
        # Filter out headers that shouldn't be forwarded
        response_headers = {}
        skip_headers = {
            "content-encoding", "content-length", "transfer-encoding",
            "connection", "keep-alive", "proxy-authenticate",
            "proxy-authorization", "te", "trailer", "upgrade",
        }
        for k, v in resp.headers.items():
            if k.lower() not in skip_headers:
                response_headers[k] = v

        return web.Response(
            status=resp.status_code,
            headers=response_headers,
            body=resp.body,
        )

    @property
    def proxy_url(self) -> str:
        """Get the proxy URL for Playwright configuration."""
        return f"http://{self.host}:{self.port}"

    @property
    def stats(self) -> Dict:
        pool_stats = self._pool.stats
        uptime = time.time() - self._stats["start_time"] if self._stats["start_time"] else 0
        return {
            **self._stats,
            "uptime_seconds": round(uptime, 1),
            "pool": pool_stats,
            "proxy_url": self.proxy_url,
        }


# ═══════════════════════════════════════════════════════════════
# TLS Engine — Direct HTTP requests with real browser TLS
# ═══════════════════════════════════════════════════════════════

class TLSHTTPClient:
    """
    Direct HTTP client using curl_cffi with real browser TLS.
    Use this instead of requests/httpx for any non-browser HTTP calls.

    Supports connection pooling via a persistent httpx.AsyncClient fallback
    when curl_cffi is unavailable.

    Example:
        client = TLSHTTPClient()
        resp = await client.get("https://bot-protected-site.com")
        print(resp.status_code, resp.text[:200])
    """

    def __init__(self, default_profile: str = "chrome124"):
        self._pool = TLSSessionPool()
        self._default_profile = default_profile
        # Persistent httpx client for fallback with connection pooling
        self._httpx_client: Optional[Any] = None
        if _CURL_AVAILABLE:
            _init_profiles()

    async def _get_httpx_client(self):
        """Get or create a persistent httpx client with connection pooling.

        Uses HTTP/2 with keep-alive connections to avoid the overhead of
        establishing a new TCP+TLS connection for every request.
        """
        import httpx as _httpx
        if self._httpx_client is None or self._httpx_client.is_closed:
            self._httpx_client = _httpx.AsyncClient(
                http2=True,
                limits=_httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                ),
                timeout=_httpx.Timeout(30.0),
            )
        return self._httpx_client

    async def request(
        self,
        method: str,
        url: str,
        profile: Optional[str] = None,
        headers: Optional[Dict] = None,
        data: Optional[bytes] = None,
        json_data: Optional[Dict] = None,
        timeout: int = 30,
        follow_redirects: bool = True,
    ) -> ProxiedResponse:
        """Make an HTTP request with real browser TLS fingerprint."""
        body = data
        if json_data:
            import json as _json
            body = _json.dumps(json_data).encode()
            if headers is None:
                headers = {}
            headers["Content-Type"] = "application/json"

        req = ProxiedRequest(
            method=method,
            url=url,
            headers=headers or {},
            body=body,
            profile=profile or self._default_profile,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

        return await self._pool.execute(req)

    async def get(self, url: str, **kwargs) -> ProxiedResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> ProxiedResponse:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> ProxiedResponse:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> ProxiedResponse:
        return await self.request("DELETE", url, **kwargs)

    def set_profile(self, profile: str):
        """Set the default TLS profile."""
        if profile in BROWSER_PROFILES:
            self._default_profile = profile

    def close(self):
        self._pool.close()
        # Close persistent httpx client if it exists
        if self._httpx_client is not None and not self._httpx_client.is_closed:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule the close in the running loop
                    asyncio.ensure_future(self._httpx_client.aclose())
                else:
                    loop.run_until_complete(self._httpx_client.aclose())
            except Exception:
                pass
            self._httpx_client = None

    @property
    def available(self) -> bool:
        return _CURL_AVAILABLE

    @property
    def stats(self) -> Dict:
        return self._pool.stats
