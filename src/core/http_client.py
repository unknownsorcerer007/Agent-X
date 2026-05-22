"""
Agent-OS TLS-Spoofing HTTP Client
Impersonates real Chrome TLS fingerprint via curl-cffi for bypassing
JA3/JA4-based bot detection (Bloomberg, Oracle, HomeDepot, etc.).
Falls back to standard httpx if curl-cffi is unavailable.
"""
import logging
import random
from typing import Any, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger("agent-os.http_client")

# ── curl-cffi availability check ──────────────────────────────
try:
    from curl_cffi.requests import AsyncSession
    from curl_cffi.requests.errors import RequestsError
    _CURL_CFFI_AVAILABLE = True
except ImportError:
    _CURL_CFFI_AVAILABLE = False
    AsyncSession = None
    RequestsError = Exception  # type: ignore[assignment,misc]

# ── BeautifulSoup for fetch_page text extraction ───────────────
try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


class TLSClient:
    """
    HTTP client that impersonates real Chrome TLS fingerprint.

    Uses curl-cffi under the hood for JA3/JA4 spoofing — cipher suite
    order, GREASE values, and TLS extensions match real Chrome exactly.
    Falls back to standard httpx if curl-cffi is unavailable.

    Usage::

        async with TLSClient() as client:
            resp = await client.get("https://example.com")
            print(resp["status"], resp["text"][:200])
    """

    CHROME_PROFILES = [
        "chrome124",
        "chrome131",
        "chrome136",
        "chrome142",
        "chrome145",
        "chrome146",
    ]

    # Chrome version → Sec-CH-UA brand string mapping
    CHROME_BRAND_VERSIONS = {
        "chrome124": "124",
        "chrome131": "131",
        "chrome136": "136",
        "chrome142": "142",
        "chrome145": "145",
        "chrome146": "146",
    }

    # Domains known for aggressive anti-bot (need extra stealth headers)
    STEALTH_REQUIRED_DOMAINS = {
        "glassdoor.com", "homedepot.com", "etsy.com", "wayfair.com",
        "realtor.com", "expedia.com", "dickssportinggoods.com",
        "crateandbarrel.com", "wsj.com", "underarmour.com",
        "reddit.com", "peacocktv.com", "paramountplus.com",
        "espn.com", "loc.gov", "berkeley.edu",
        "bloomberg.com", "airbnb.com", "booking.com",
        "zillow.com", "coinbase.com", "binance.com",
    }

    # Default browser-like headers that real Chrome sends
    DEFAULT_BROWSER_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self, profile: Optional[str] = None) -> None:
        if profile is None:
            self._profile = random.choice(self.CHROME_PROFILES)
        else:
            if profile not in self.CHROME_PROFILES:
                logger.warning(
                    "Unknown TLS profile '%s', falling back to chrome131. "
                    "Available: %s",
                    profile,
                    ", ".join(self.CHROME_PROFILES),
                )
                self._profile = "chrome136"
            else:
                self._profile = profile

        self._session: Optional[Any] = None
        self._fallback_client: Optional[Any] = None

        if _CURL_CFFI_AVAILABLE:
            self._session = AsyncSession(
                impersonate=self._profile,
                verify=True,
                timeout=30,
            )
            logger.info("TLSClient initialized with profile: %s", self._profile)
        else:
            logger.warning(
                "curl_cffi not installed — TLS fingerprint will NOT match "
                "real Chrome. Bot detection risk HIGH. "
                "Install with: pip install curl-cffi>=0.7.0"
            )
            import httpx
            self._fallback_client = httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
            )

    @property
    def available(self) -> bool:
        """True if curl-cffi is available (real TLS spoofing)."""
        return _CURL_CFFI_AVAILABLE

    @property
    def profile(self) -> str:
        """Currently active TLS profile name."""
        return self._profile

    # ── Header Building ─────────────────────────────────────────

    def _build_headers(self, url: str, user_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Build realistic browser headers for the given URL.

        Automatically adds Sec-CH-UA and stealth headers for anti-bot sites.
        User-provided headers override defaults.
        """
        headers = dict(self.DEFAULT_BROWSER_HEADERS)

        # Add Sec-CH-UA based on profile version
        chrome_ver = self.CHROME_BRAND_VERSIONS.get(self._profile, "146")
        headers["Sec-Ch-Ua"] = (
            f'"Chromium";v="{chrome_ver}", '
            f'"Google Chrome";v="{chrome_ver}", '
            f'"Not-A.Brand";v="99"'
        )

        # Add User-Agent matching the profile
        headers["User-Agent"] = (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_ver}.0.0.0 Safari/537.36"
        )

        # Add Referer for same-origin requests (helps with WAF)
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        # Only set Origin for non-navigation requests (POST, PUT, PATCH, DELETE)
        # Real Chrome does not send Origin on initial GET navigations
        method = headers.get("X-Method-Override", "GET")  # Will be set by post() below
        if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            headers["Origin"] = origin

        # Stealth mode: extra headers for anti-bot domains
        domain = parsed.hostname or ""
        bare_domain = domain.replace("www.", "")
        if bare_domain in self.STEALTH_REQUIRED_DOMAINS or any(
            d in bare_domain for d in self.STEALTH_REQUIRED_DOMAINS
        ):
            # Add DNT and more realistic browser signals
            headers["Dnt"] = "1"
            # Keep Sec-Fetch-Site: none for initial navigations
            # same-origin is only used for subsequent requests within the same origin
            if headers.get("Sec-Fetch-Site") != "none":
                headers["Sec-Fetch-Site"] = "same-origin"

        # User headers override everything
        if user_headers:
            headers.update(user_headers)

        return headers

    # ── Core Methods ───────────────────────────────────────────

    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        follow_redirects: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute GET with curl-cffi impersonation.

        Returns:
            Dict with keys: status, headers, text, url, cookies, ok.
            On error: status=0, ok=False, error=<message>.
        """
        # Build realistic browser headers
        final_headers = self._build_headers(url, headers)

        try:
            if _CURL_CFFI_AVAILABLE and self._session:
                resp = await self._session.get(
                    url,
                    headers=final_headers,
                    cookies=cookies,
                    timeout=timeout,
                    allow_redirects=follow_redirects,
                )
            else:
                resp = await self._fallback_client.get(
                    url,
                    headers=final_headers,
                    cookies=cookies,
                    timeout=timeout,
                    follow_redirects=follow_redirects,
                )

            result = {
                "status": resp.status_code,
                "headers": dict(resp.headers),
                "text": resp.text,
                "url": str(resp.url),
                "cookies": dict(resp.cookies),
                "ok": resp.status_code < 400,
            }

            if resp.status_code == 403:
                logger.warning("GET %s returned 403 — site may be blocking TLS fingerprint", url)

            return result

        except Exception as exc:
            exc_str = str(exc)
            # HTTP/2 stream errors — retry with HTTP/1.1 via fallback
            if "HTTP/2 stream" in exc_str or "INTERNAL_ERROR" in exc_str or "http2" in exc_str.lower():
                logger.warning("HTTP/2 protocol error for %s, retrying with httpx (HTTP/1.1): %s", url, exc_str[:120])
                try:
                    import httpx
                    async with httpx.AsyncClient(
                        timeout=timeout,
                        follow_redirects=follow_redirects,
                        http2=False,
                    ) as fallback:
                        resp = await fallback.get(url, headers=final_headers, cookies=cookies)
                        return {
                            "status": resp.status_code,
                            "headers": dict(resp.headers),
                            "text": resp.text,
                            "url": str(resp.url),
                            "cookies": dict(resp.cookies),
                            "ok": resp.status_code < 400,
                        }
                except Exception as fallback_exc:
                    logger.error("HTTP/1.1 fallback also failed for %s: %s", url, fallback_exc)

            logger.error("TLS GET failed for %s: %s", url, exc)
            return {
                "status": 0,
                "headers": {},
                "text": "",
                "url": url,
                "cookies": {},
                "ok": False,
                "error": str(exc),
            }

    async def post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Execute POST with curl-cffi impersonation.
        Supports both form data (``data``) and JSON body (``json``).

        Returns:
            Same dict format as :meth:`get`.
        """
        # Build realistic browser headers — mark as POST so Origin header is included
        override_headers = dict(headers) if headers else {}
        override_headers["X-Method-Override"] = "POST"
        final_headers = self._build_headers(url, override_headers)
        # Remove the internal marker before sending
        final_headers.pop("X-Method-Override", None)
        # Override Accept for POST
        final_headers.setdefault("Accept", "application/json, text/plain, */*")
        final_headers["Sec-Fetch-Dest"] = "empty"
        final_headers["Sec-Fetch-Mode"] = "cors"

        try:
            if _CURL_CFFI_AVAILABLE and self._session:
                resp = await self._session.post(
                    url,
                    data=data,
                    json=json,
                    headers=final_headers,
                    timeout=timeout,
                )
            else:
                resp = await self._fallback_client.post(
                    url,
                    data=data,
                    json=json,
                    headers=final_headers,
                    timeout=timeout,
                )

            result = {
                "status": resp.status_code,
                "headers": dict(resp.headers),
                "text": resp.text,
                "url": str(resp.url),
                "cookies": dict(resp.cookies),
                "ok": resp.status_code < 400,
            }

            if resp.status_code == 403:
                logger.warning("POST %s returned 403 — site may be blocking TLS fingerprint", url)

            return result

        except Exception as exc:
            logger.error("TLS POST failed for %s: %s", url, exc)
            return {
                "status": 0,
                "headers": {},
                "text": "",
                "url": url,
                "cookies": {},
                "ok": False,
                "error": str(exc),
            }

    async def fetch_page(
        self,
        url: str,
        extract_text: bool = True,
    ) -> Dict[str, Any]:
        """
        Higher-level method: GET a URL and optionally extract clean text.

        1. Fetches the page via TLS-spoofed GET.
        2. If ``extract_text=True``, strips scripts, styles, nav, footer
           using BeautifulSoup for clean readable text.
        3. Extracts the ``<title>`` tag content.

        Returns:
            Dict with keys: status, url, title, text, html, ok, word_count.
        """
        resp = await self.get(url)

        if not resp.get("ok") and resp.get("status", 0) == 0:
            return {
                "status": 0,
                "url": url,
                "title": "",
                "text": "",
                "html": "",
                "ok": False,
                "word_count": 0,
                "error": resp.get("error", "request failed"),
            }

        html = resp.get("text", "")
        title = ""
        clean_text = html  # fallback: raw HTML if BS4 unavailable

        if _BS4_AVAILABLE and html:
            try:
                soup = BeautifulSoup(html, "html.parser")

                # Extract <title>
                title_tag = soup.find("title")
                if title_tag and title_tag.string:
                    title = title_tag.string.strip()

                if extract_text:
                    # Remove non-content elements
                    for tag_name in ("script", "style", "noscript", "svg", "iframe"):
                        for element in soup.find_all(tag_name):
                            element.decompose()

                    # Remove nav, footer, header boilerplate
                    for tag_name in ("nav", "footer", "header"):
                        for element in soup.find_all(tag_name):
                            element.decompose()

                    # Get clean text
                    clean_text = soup.get_text(separator="\n", strip=True)

                    # Collapse multiple blank lines
                    import re
                    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)

            except Exception as exc:
                logger.warning("BeautifulSoup extraction failed: %s", exc)
                clean_text = html

        word_count = len(clean_text.split()) if clean_text else 0

        return {
            "status": resp.get("status", 0),
            "url": resp.get("url", url),
            "title": title,
            "text": clean_text,
            "html": html,
            "ok": resp.get("ok", False),
            "word_count": word_count,
        }

    # ── Lifecycle ──────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying session cleanly."""
        try:
            if self._session:
                await self._session.close()
            if self._fallback_client:
                await self._fallback_client.aclose()
        except Exception:
            pass
        logger.info("TLSClient session closed")

    async def __aenter__(self) -> "TLSClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
