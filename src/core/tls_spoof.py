"""
Agent-OS TLS Fingerprint Engine
Real TLS fingerprinting via curl_cffi for HTTP requests.
CDP-level TLS metadata spoofing for Playwright browser.

curl_cffi uses BoringSSL and can impersonate real Chrome/Firefox/Safari
TLS ClientHello fingerprints at the network level — not just headers.
"""

import logging
import random
from typing import Optional, Dict, Any

logger = logging.getLogger("agent-os.tls")

# ═══════════════════════════════════════════════════════════════
# curl_cffi session pool for HTTP requests with real TLS
# ═══════════════════════════════════════════════════════════════

_CURL_AVAILABLE = False
_curl_Session = None
_curl_BrowserType = None

try:
    from curl_cffi.requests import Session as _curl_Session, BrowserType as _curl_BrowserType
    _CURL_AVAILABLE = True
except ImportError:
    pass


# Chrome versions and their curl_cffi BrowserType mappings
def _get_profiles():
    if not _CURL_AVAILABLE:
        return {}
    # Use getattr to handle missing profiles across curl_cffi versions
    profiles = {}
    _known = [
        "chrome116", "chrome119", "chrome120", "chrome124",
        "chrome131", "chrome133a", "chrome136", "chrome142",
        "chrome145", "chrome146",
        "firefox135", "firefox147",
        "safari15_3", "safari15_5", "safari17_0", "safari18_0",
        "edge99", "edge101",
    ]
    for name in _known:
        val = getattr(_curl_BrowserType, name, None)
        if val is not None:
            profiles[name] = val
    # Ensure at least one chrome profile exists
    if not any(k.startswith("chrome") for k in profiles):
        # Fallback: use whatever chrome profile is available
        for attr in dir(_curl_BrowserType):
            if attr.startswith("chrome") and not attr.startswith("_"):
                profiles[attr] = getattr(_curl_BrowserType, attr)
    return profiles


class TLSFingerprintEngine:
    """
    Manages curl_cffi sessions with real browser TLS fingerprint impersonation.
    Each session mimics a specific browser version's TLS ClientHello,
    HTTP/2 settings, and cipher suite order at the network level.
    """

    def __init__(self, default_profile: str = "chrome131"):
        if not _CURL_AVAILABLE:
            logger.error(
                "curl_cffi not installed! TLS fingerprinting will NOT work.\n"
                "Run: pip install curl_cffi\n"
                "Without this, bot detection WILL catch you."
            )
            raise ImportError("curl_cffi is required for TLS fingerprinting")

        self._profiles = _get_profiles()
        self._sessions: Dict[str, Any] = {}
        # Use requested profile, fall back to best available
        if default_profile not in self._profiles:
            # Pick the newest available Chrome profile
            chrome_profiles = sorted(
                [k for k in self._profiles if k.startswith("chrome")],
                key=lambda x: int(x.replace("chrome", "").replace("a", "").replace("_android", "")) if x.replace("chrome", "").replace("a", "").replace("_android", "").isdigit() else 0,
                reverse=True,
            )
            default_profile = chrome_profiles[0] if chrome_profiles else "chrome124"
        self._default_profile = default_profile
        self._session_cookies: Dict[str, Dict] = {}
        self._request_count: int = 0

    def _get_or_create_session(self, profile: str) -> Any:
        """Get or create a curl_cffi session for a browser profile."""
        if profile not in self._sessions:
            browser_type = self._profiles.get(profile)
            if not browser_type:
                raise ValueError(f"Unknown profile: {profile}. Available: {list(self._profiles.keys())}")

            session = _curl_Session(impersonate=browser_type)
            self._sessions[profile] = session
            logger.info(f"Created TLS session: {profile}")

        return self._sessions[profile]

    def request(
        self,
        method: str,
        url: str,
        profile: Optional[str] = None,
        headers: Optional[Dict] = None,
        proxy: Optional[str] = None,
        timeout: int = 30,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Perform HTTP request with real browser TLS fingerprint.

        Args:
            method: GET, POST, PUT, DELETE, etc.
            url: Target URL
            profile: Browser profile (chrome124, safari17_0, etc.)
            headers: Additional headers (merged with browser's default)
            proxy: Proxy URL (http://user:pass@host:port)
            timeout: Request timeout in seconds

        Returns:
            {
                "status_code": int,
                "text": str,
                "headers": dict,
                "cookies": dict,
                "url": str,
                "tls_profile": str,
            }
        """
        profile = profile or self._default_profile
        session = self._get_or_create_session(profile)

        # Merge extra headers
        req_kwargs = {"timeout": timeout, **kwargs}
        if headers:
            req_kwargs["headers"] = headers
        if proxy:
            req_kwargs["proxy"] = proxy

        self._request_count += 1

        try:
            resp = session.request(method, url, **req_kwargs)

            # Persist cookies across requests in the same session
            self._session_cookies[profile] = dict(resp.cookies)

            return {
                "status_code": resp.status_code,
                "text": resp.text,
                "headers": dict(resp.headers),
                "cookies": dict(resp.cookies),
                "url": resp.url,
                "tls_profile": profile,
            }
        except Exception as e:
            logger.error(f"TLS request failed ({profile} {method} {url[:80]}): {e}")
            return {
                "status_code": 0,
                "text": "",
                "headers": {},
                "cookies": {},
                "url": url,
                "tls_profile": profile,
                "error": str(e),
            }

    def get(self, url: str, **kwargs) -> Dict[str, Any]:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Dict[str, Any]:
        return self.request("POST", url, **kwargs)

    def rotate_profile(self) -> str:
        """Switch to a random browser profile for the next request."""
        available = list(self._profiles.keys())
        # Avoid using the same profile twice in a row
        choices = [p for p in available if p != self._default_profile]
        self._default_profile = random.choice(choices)
        logger.info(f"Rotated TLS profile to: {self._default_profile}")
        return self._default_profile

    def set_profile(self, profile: str):
        """Set a specific browser profile."""
        if profile not in self._profiles:
            raise ValueError(f"Unknown profile: {profile}")
        self._default_profile = profile

    def close(self):
        """Close all sessions."""
        for session in self._sessions.values():
            try:
                session.close()
            except Exception:
                pass
        self._sessions.clear()

    @property
    def available(self) -> bool:
        return _CURL_AVAILABLE

    @property
    def stats(self) -> Dict:
        return {
            "requests_made": self._request_count,
            "active_sessions": list(self._sessions.keys()),
            "default_profile": self._default_profile,
        }


# ═══════════════════════════════════════════════════════════════
# CDP-level TLS metadata for Playwright browser
# ═══════════════════════════════════════════════════════════════

# Real Chrome sec-ch-ua brand strings per version
CHROME_BRAND_VERSIONS = {
    "146": [
        {"brand": "Chromium", "version": "146"},
        {"brand": "Google Chrome", "version": "146"},
        {"brand": "Not-A.Brand", "version": "99"},
    ],
    "145": [
        {"brand": "Chromium", "version": "145"},
        {"brand": "Google Chrome", "version": "145"},
        {"brand": "Not-A.Brand", "version": "99"},
    ],
    "142": [
        {"brand": "Chromium", "version": "142"},
        {"brand": "Google Chrome", "version": "142"},
        {"brand": "Not-A.Brand", "version": "99"},
    ],
    "136": [
        {"brand": "Chromium", "version": "136"},
        {"brand": "Google Chrome", "version": "136"},
        {"brand": "Not-A.Brand", "version": "99"},
    ],
    "133": [
        {"brand": "Chromium", "version": "133"},
        {"brand": "Google Chrome", "version": "133"},
        {"brand": "Not?A_Brand", "version": "99"},
    ],
    "131": [
        {"brand": "Chromium", "version": "131"},
        {"brand": "Google Chrome", "version": "131"},
        {"brand": "Not?A_Brand", "version": "99"},
    ],
    "124": [
        {"brand": "Chromium", "version": "124"},
        {"brand": "Google Chrome", "version": "124"},
        {"brand": "Not-A.Brand", "version": "99"},
    ],
    "120": [
        {"brand": "Chromium", "version": "120"},
        {"brand": "Google Chrome", "version": "120"},
        {"brand": "Not_A Brand", "version": "99"},
    ],
    "116": [
        {"brand": "Chromium", "version": "116"},
        {"brand": "Google Chrome", "version": "116"},
        {"brand": "Not/A.Brand", "version": "99"},
    ],
}


async def apply_browser_tls_spoofing(page, chrome_version: str = "124", browser_profile=None) -> bool:
    """
    Apply TLS metadata spoofing to a Playwright page via CDP.

    This sets HTTP headers and User-Agent Client Hints to match a real
    Chrome browser. It does NOT change the TLS ClientHello (that's
    controlled by Chromium's BoringSSL). But it prevents header-level
    fingerprinting from detecting automation.

    Args:
        page: Playwright Page object
        chrome_version: Chrome version to emulate
        browser_profile: Optional BrowserProfile dataclass for platform-aware
                         values (platform, locale, sec_ch_ua_platform, etc.)

    Returns:
        True if applied successfully
    """
    try:
        cdp = await page.context.new_cdp_session(page)

        try:
            # Derive platform-aware values from the browser profile when available
            if browser_profile is not None:
                platform = browser_profile.platform
                sec_ch_platform = browser_profile.sec_ch_ua_platform.strip('"')
                locale = browser_profile.locale
                accept_lang = f"{locale},{locale.split('-')[0]};q=0.9"
                if platform == "Win32":
                    platform_version = "15.0.0"
                    ua_os = "Windows NT 10.0; Win64; x64"
                elif platform == "MacIntel":
                    platform_version = "14.0.0"
                    ua_os = "Macintosh; Intel Mac OS X 10_15_7"
                else:
                    platform_version = "6.0.0"
                    ua_os = "X11; Linux x86_64"
            else:
                platform = "Win32"
                sec_ch_platform = "Windows"
                locale = "en-US"
                accept_lang = "en-US,en;q=0.9"
                platform_version = "15.0.0"
                ua_os = "Windows NT 10.0; Win64; x64"

            # Build realistic User-Agent string
            ua = (
                f"Mozilla/5.0 ({ua_os}) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome_version}.0.0.0 Safari/537.36"
            )

            # Set User-Agent override with full metadata
            brands = CHROME_BRAND_VERSIONS.get(chrome_version, CHROME_BRAND_VERSIONS["124"])
            await cdp.send("Network.setUserAgentOverride", {
                "userAgent": ua,
                "acceptLanguage": accept_lang,
                "platform": platform,
                "userAgentMetadata": {
                    "brands": brands,
                    "fullVersionList": [
                        {**b, "version": f"{b['version']}.0.0.0"} for b in brands
                    ],
                    "fullVersion": f"{chrome_version}.0.0.0",
                    "platform": sec_ch_platform,
                    "platformVersion": platform_version,
                    "architecture": "x86",
                    "model": "",
                    "mobile": False,
                    "bitness": "64",
                    "wow64": False,
                },
            })

            # Enable Network domain
            await cdp.send("Network.enable")

            # Set extra HTTP headers that match real Chrome navigations
            await cdp.send("Network.setExtraHTTPHeaders", {
                "headers": {
                    "sec-ch-ua": ', '.join(
                        f'"{b["brand"]}";v="{b["version"]}"' for b in brands
                    ),
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": f'"{sec_ch_platform}"',
                    "Upgrade-Insecure-Requests": "1",
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;"
                        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                    ),
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-User": "?1",
                    "Sec-Fetch-Dest": "document",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": accept_lang,
                }
            })

            # Also spoof via CDP Page domain for JavaScript-level checks
            await cdp.send("Emulation.setUserAgentOverride", {
                "userAgent": ua,
                "acceptLanguage": accept_lang,
                "platform": platform,
            })

            logger.info(f"Browser TLS spoofing applied (Chrome {chrome_version}, {platform})")
            return True

        finally:
            # ALWAYS detach CDP session to prevent leaks
            try:
                await cdp.detach()
            except Exception:
                pass

    except Exception as e:
        logger.warning(f"Browser TLS spoofing failed: {e}")
        return False
