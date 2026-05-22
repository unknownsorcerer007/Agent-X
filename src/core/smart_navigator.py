"""
Agent-OS Smart Navigator
Intelligent URL fetcher that picks the right strategy (HTTP vs browser)
per domain, retries on failure with escalating delays, and caches
which approach works for each site.

Supports ai_format=True to return AI-structured data instead of
raw HTML/text — same symmetrical JSON regardless of fetch strategy.
"""
import asyncio
import logging
import random
import time
from collections import defaultdict
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from src.core.browser import AgentBrowser
from src.core.http_client import TLSClient

logger = logging.getLogger("agent-os.smart_navigator")


class SmartNavigator:
    """
    Intelligent URL fetcher with automatic strategy selection.

    Tries strategies in order:
    1. TLSClient (curl-cffi) — fastest, best for static sites
    2. Patchright browser — for JS-heavy, Cloudflare sites
    3. Retry with delays — for rate-limited sites (429)

    Learns which strategy works per domain and caches it.
    """

    # Sites known to need browser (JS rendering required)
    BROWSER_REQUIRED_DOMAINS = [
        "glassdoor.com", "linkedin.com", "twitter.com",
        "x.com", "instagram.com", "facebook.com",
        "zillow.com", "trulia.com", "redfin.com",
        # Anti-bot sites that block HTTP requests (need Patchright browser)
        "homedepot.com", "etsy.com", "wayfair.com",
        "dickssportinggoods.com", "crateandbarrel.com",
        "realtor.com", "expedia.com", "booking.com",
        "wsj.com", "peacocktv.com", "espn.com",
        "underarmour.com",
    ]

    # Sites that need networkidle wait for full JS rendering (login pages, SPA)
    NETWORKIDLE_REQUIRED_DOMAINS = [
        "instagram.com", "facebook.com", "twitter.com", "x.com",
        "linkedin.com", "github.com", "accounts.google.com",
        "login.microsoftonline.com", "amazon.com", "netflix.com",
        "spotify.com", "tiktok.com", "reddit.com",
    ]

    # Sites known to need delays between requests
    RATE_SENSITIVE_DOMAINS = [
        "realtor.com", "expedia.com", "booking.com",
        "hotels.com", "airbnb.com",
    ]

    # Delay ranges per status code
    RETRY_DELAYS = {
        429: (5.0, 15.0),  # Rate limited: wait 5-15s
        403: (2.0, 6.0),   # Forbidden: wait 2-6s before retry
        503: (3.0, 8.0),   # Service unavailable
    }

    def __init__(self, browser: AgentBrowser) -> None:
        self._browser = browser
        self._tls_client = TLSClient()
        self._ai_extractor = None  # Lazy init
        # Cache: domain -> "http" | "browser" (with TTL and cap)
        self._strategy_cache: Dict[str, str] = {}
        self._strategy_cache_times: Dict[str, float] = {}
        self._strategy_cache_ttl = 3600  # 1 hour
        self._strategy_cache_max = 1000
        # Stats: domain -> {http_success, browser_success, http_fail, browser_fail}
        self._stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"http_success": 0, "browser_success": 0,
                     "http_fail": 0, "browser_fail": 0}
        )
        self._total_navigations: int = 0
        self._cache_hits: int = 0

    # ── Domain Extraction ──────────────────────────────────────

    def _get_domain(self, url: str) -> str:
        """Extract bare domain from URL, stripping www. prefix.

        >>> sn._get_domain("https://www.reddit.com/r/python")
        'reddit.com'
        """
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host.startswith("www."):
            host = host[4:]
        return host.lower()

    # ── Strategy Selection ─────────────────────────────────────

    def _get_cached_strategy(self, domain: str) -> Optional[str]:
        """Get cached strategy for domain, respecting TTL."""
        if domain in self._strategy_cache:
            if time.time() - self._strategy_cache_times.get(domain, 0) > self._strategy_cache_ttl:
                del self._strategy_cache[domain]
                del self._strategy_cache_times[domain]
                return None
            return self._strategy_cache[domain]
        return None

    def _set_cached_strategy(self, domain: str, strategy: str) -> None:
        """Cache strategy for domain with TTL tracking and size cap."""
        # Cap cache size
        if len(self._strategy_cache) >= self._strategy_cache_max:
            # Remove oldest entries
            oldest = sorted(self._strategy_cache_times.items(), key=lambda x: x[1])[:100]
            for d, _ in oldest:
                self._strategy_cache.pop(d, None)
                self._strategy_cache_times.pop(d, None)
        self._strategy_cache[domain] = strategy
        self._strategy_cache_times[domain] = time.time()

    def _pick_initial_strategy(self, url: str, prefer_browser: bool) -> str:
        """Decide whether to start with HTTP or browser."""
        domain = self._get_domain(url)

        # 1. Browser-required domains always go browser first
        for bd in self.BROWSER_REQUIRED_DOMAINS:
            if bd in domain:
                logger.info("Domain %s is browser-required — starting with browser", domain)
                return "browser"

        # 2. Cached strategy from previous successful attempt
        cached = self._get_cached_strategy(domain)
        if cached:
            self._cache_hits += 1
            logger.debug("Strategy cache hit for %s: %s", domain, cached)
            return cached

        # 3. Explicit preference
        if prefer_browser:
            return "browser"

        # 4. Default: try HTTP first (faster, cheaper)
        return "http"

    # ── Strategy Executors ─────────────────────────────────────

    async def _try_http(self, url: str, ai_format: bool = False) -> Dict[str, Any]:
        """Fetch via TLS-spoofed HTTP client and normalize result."""
        domain = self._get_domain(url)
        start_ms = time.monotonic()

        try:
            result = await self._tls_client.fetch_page(url, extract_text=True)
            elapsed_ms = (time.monotonic() - start_ms) * 1000.0

            ok = result.get("ok", False)
            status = result.get("status", 0)

            if ok:
                self._stats[domain]["http_success"] += 1
            else:
                self._stats[domain]["http_fail"] += 1

            # Build base response
            response = {
                "status": "success" if ok else "error",
                "url": result.get("url", url),
                "strategy_used": "http",
                "response_time_ms": round(elapsed_ms, 1),
                "blocked": not ok and status in (403, 429, 503),
                "content": result.get("text", ""),
                "title": result.get("title", ""),
                "http_status": status,
                "word_count": result.get("word_count", 0),
                "tls_profile": self._tls_client.profile,
                "curl_cffi": self._tls_client.available,
                "error": result.get("error"),
            }

            # If ai_format requested, transform raw content into structured JSON
            if ok and ai_format and result.get("text"):
                try:
                    extractor = self._get_ai_extractor()
                    ai_result = await extractor.extract_from_html(
                        result.get("html", ""), url=result.get("url", url)
                    )
                    if ai_result.get("status") == "success":
                        response["ai_content"] = ai_result["data"]
                        # Replace raw content with clean main_text
                        response["content"] = ai_result["data"].get("main_text", response["content"])
                except Exception as exc:
                    logger.warning("AI content extraction failed for %s: %s", url, exc)

            return response

        except Exception as exc:
            elapsed_ms = (time.monotonic() - start_ms) * 1000.0
            self._stats[domain]["http_fail"] += 1
            logger.error("HTTP fetch failed for %s: %s", url, exc)
            return {
                "status": "error",
                "url": url,
                "strategy_used": "http",
                "response_time_ms": round(elapsed_ms, 1),
                "blocked": False,
                "content": "",
                "title": "",
                "http_status": 0,
                "word_count": 0,
                "error": str(exc),
            }

    async def _try_browser(self, url: str, ai_format: bool = False) -> Dict[str, Any]:
        """Fetch via Patchright browser and normalize result."""
        domain = self._get_domain(url)
        start_ms = time.monotonic()

        # Pick wait strategy: use networkidle for JS-heavy/login sites
        wait_until = "domcontentloaded"
        for nd in self.NETWORKIDLE_REQUIRED_DOMAINS:
            if nd in domain:
                wait_until = "networkidle"
                logger.info(f"Using networkidle wait for JS-heavy domain: {domain}")
                break

        try:
            nav_result = await self._browser.navigate(
                url,
                page_id="main",
                wait_until=wait_until,
                retries=1,
                warmup=False,
            )

            # Grab page content after navigation
            content_result: Dict[str, Any] = {"text": "", "title": ""}
            
            # Wait for JS-heavy sites to fully render before reading content
            # Keep delay short — networkidle already waits for all network requests
            if wait_until == "networkidle":
                await asyncio.sleep(random.uniform(0.3, 0.8))
            
            try:
                content_result = await self._browser.get_content(page_id="main")
            except Exception:
                pass

            elapsed_ms = (time.monotonic() - start_ms) * 1000.0
            nav_ok = nav_result.get("status") == "success"
            status_code = nav_result.get("status_code", 0)
            blocked = nav_result.get("block_report") is not None

            if nav_ok and not blocked:
                self._stats[domain]["browser_success"] += 1
            else:
                self._stats[domain]["browser_fail"] += 1

            text = content_result.get("text", "") if isinstance(content_result, dict) else ""
            title = content_result.get("title", "") if isinstance(content_result, dict) else ""

            # Build base response
            response = {
                "status": "success" if (nav_ok and not blocked) else "error",
                "url": nav_result.get("url", url),
                "strategy_used": "browser",
                "response_time_ms": round(elapsed_ms, 1),
                "blocked": blocked,
                "content": text,
                "title": title,
                "http_status": status_code,
                "word_count": len(text.split()) if text else 0,
                "block_report": nav_result.get("block_report"),
                "error": nav_result.get("error"),
            }

            # If ai_format requested, extract structured data from browser DOM
            if nav_ok and not blocked and ai_format:
                try:
                    extractor = self._get_ai_extractor()
                    ai_result = await extractor.extract_from_browser(self._browser, page_id="main")
                    if ai_result.get("status") == "success":
                        response["ai_content"] = ai_result["data"]
                        response["content"] = ai_result["data"].get("main_text", text)
                except Exception as exc:
                    logger.warning("AI content extraction failed for %s: %s", url, exc)

            return response

        except Exception as exc:
            elapsed_ms = (time.monotonic() - start_ms) * 1000.0
            self._stats[domain]["browser_fail"] += 1
            logger.error("Browser fetch failed for %s: %s", url, exc)
            return {
                "status": "error",
                "url": url,
                "strategy_used": "browser",
                "response_time_ms": round(elapsed_ms, 1),
                "blocked": False,
                "content": "",
                "title": "",
                "http_status": 0,
                "word_count": 0,
                "error": str(exc),
            }

    # ── Rate-Sensitive Delay ───────────────────────────────────

    async def _maybe_rate_delay(self, domain: str) -> None:
        """Add a pre-request delay for rate-sensitive domains."""
        for rd in self.RATE_SENSITIVE_DOMAINS:
            if rd in domain:
                pre_delay = random.uniform(1.5, 3.5)
                logger.info(
                    "Rate-sensitive domain %s: waiting %.1fs before request",
                    domain, pre_delay,
                )
                await asyncio.sleep(pre_delay)
                return

    # ── Retry Delay ────────────────────────────────────────────

    async def _retry_delay(self, status_code: int, attempt: int) -> None:
        """Wait appropriate time before retry based on status code."""
        delay_range = self.RETRY_DELAYS.get(status_code, (1.0, 3.0))
        base_delay = random.uniform(*delay_range)
        # Exponential backoff for repeated retries
        total_delay = base_delay * (1.0 + 0.5 * attempt)
        logger.info(
            "Retry delay for status %d (attempt %d): %.1fs",
            status_code, attempt, total_delay,
        )
        await asyncio.sleep(total_delay)

    # ── Main Entry Point ───────────────────────────────────────

    def _get_ai_extractor(self):
        """Lazy-initialize AI content extractor."""
        if self._ai_extractor is None:
            from src.tools.ai_content import AIContentExtractor
            self._ai_extractor = AIContentExtractor()
        return self._ai_extractor

    async def navigate(
        self,
        url: str,
        prefer_browser: bool = False,
        max_retries: int = 3,
        ai_format: bool = False,
    ) -> Dict[str, Any]:
        """
        Smart navigate with automatic fallback and retry.

        Strategy selection:
        1. Domain in BROWSER_REQUIRED_DOMAINS → browser directly
        2. Domain in strategy_cache → cached strategy
        3. prefer_browser=True → start with browser
        4. Otherwise → HTTP first, fall back to browser on 403/blocked

        Retry logic:
        - On 429: wait RETRY_DELAYS[429] seconds, retry same strategy
        - On 403 with HTTP: switch to browser, retry once
        - On 403 with browser: add 3s delay, retry once
        - On success: cache the winning strategy
        - After max_retries: return last response with blocked=True

        Args:
            url: Target URL to navigate to
            prefer_browser: Force browser strategy on first attempt
            max_retries: Maximum retry attempts (default: 3)
            ai_format: Return AI-structured data instead of raw text
                       (symmetrical JSON with deduplicated, typed content)
        """
        self._total_navigations += 1

        try:
            return await asyncio.wait_for(
                self._navigate_inner(url, prefer_browser, max_retries, ai_format),
                timeout=60,
            )
        except asyncio.TimeoutError:
            return {"status": "error", "error": "Navigation timed out after 60s", "url": url}

    async def _navigate_inner(
        self,
        url: str,
        prefer_browser: bool = False,
        max_retries: int = 3,
        ai_format: bool = False,
    ) -> Dict[str, Any]:
        """Inner navigation logic, wrapped by navigate() with timeout."""
        domain = self._get_domain(url)
        strategy = self._pick_initial_strategy(url, prefer_browser)

        # Rate-sensitive pre-delay
        await self._maybe_rate_delay(domain)

        last_response: Dict[str, Any] = {}
        tried_browser_fallback = False

        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info(
                    "Retry %d/%d for %s (strategy=%s)",
                    attempt, max_retries, url[:80], strategy,
                )

            # ── Execute current strategy ───────────────────────
            if strategy == "http":
                response = await self._try_http(url, ai_format=ai_format)
            else:
                response = await self._try_browser(url, ai_format=ai_format)

            last_response = response
            status_code = response.get("http_status", 0)
            is_blocked = response.get("blocked", False)
            is_success = response.get("status") == "success"

            # ── Success: cache and return ──────────────────────
            if is_success and not is_blocked:
                self._set_cached_strategy(domain, strategy)
                response["attempts"] = attempt + 1
                return response

            # ── Exhausted retries ──────────────────────────────
            if attempt >= max_retries:
                break

            # ── 429 Rate Limited: delay + retry same strategy ──
            if status_code == 429:
                await self._retry_delay(429, attempt)
                continue

            # ── 403 Forbidden: escalate strategy ───────────────
            if status_code == 403 or is_blocked:
                if strategy == "http" and not tried_browser_fallback:
                    # HTTP failed → escalate to browser
                    logger.info(
                        "HTTP got 403/blocked for %s — escalating to browser",
                        domain,
                    )
                    strategy = "browser"
                    tried_browser_fallback = True
                    await asyncio.sleep(random.uniform(1.0, 3.0))
                    continue
                elif strategy == "browser":
                    # Browser also blocked — add delay, retry
                    await self._retry_delay(403, attempt)
                    continue

            # ── 503 Service Unavailable: delay + retry ─────────
            if status_code == 503:
                await self._retry_delay(503, attempt)
                continue

            # ── Other errors: brief delay, retry same strategy ─
            await asyncio.sleep(random.uniform(1.0, 2.0))

        # ── All retries exhausted ──────────────────────────────
        last_response["status"] = "error"
        last_response["blocked"] = True
        last_response["attempts"] = max_retries + 1
        last_response["final_status"] = last_response.get("http_status", 0)
        return last_response

    # ── Stats ──────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return navigation stats including per-domain success rates."""
        domain_stats: Dict[str, Dict[str, Any]] = {}
        for domain, counts in self._stats.items():
            total_http = counts["http_success"] + counts["http_fail"]
            total_browser = counts["browser_success"] + counts["browser_fail"]
            domain_stats[domain] = {
                "http_success_rate": (
                    round(counts["http_success"] / total_http * 100, 1)
                    if total_http > 0 else None
                ),
                "browser_success_rate": (
                    round(counts["browser_success"] / total_browser * 100, 1)
                    if total_browser > 0 else None
                ),
                **counts,
            }

        # Strategy breakdown
        http_cached = sum(1 for s in self._strategy_cache.values() if s == "http")
        browser_cached = sum(1 for s in self._strategy_cache.values() if s == "browser")

        return {
            "total_navigations": self._total_navigations,
            "cache_hits": self._cache_hits,
            "cached_domains": len(self._strategy_cache),
            "strategy_breakdown": {
                "http_cached": http_cached,
                "browser_cached": browser_cached,
            },
            "per_domain": domain_stats,
        }

    # ── Lifecycle ──────────────────────────────────────────────

    async def close(self) -> None:
        """Clean up resources."""
        await self._tls_client.close()
        logger.info("SmartNavigator closed")
