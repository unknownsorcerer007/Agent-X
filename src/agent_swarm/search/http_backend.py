"""HTTP-based search backend using curl_cffi for TLS fingerprinting."""

import re
import json
import base64
import logging
import asyncio
import atexit
import threading
import time
from typing import Optional
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

from src.agent_swarm.search.base import SearchBackend, combine_results

logger = logging.getLogger(__name__)

# Patterns that indicate a search-engine internal/redirect URL (not a real result)
_BAD_URL_PATTERNS = re.compile(
    r"^(https?://(www\.)?(bing\.com/ck/a|bing\.com/search|google\.com/search"
    r"|google\.com/url\?|duckduckgo\.com/\?|duckduckgo\.com/l/\?)"
    r"|/search\?|/url\?)",
    re.IGNORECASE,
)

# Semaphore to limit concurrent outgoing HTTP requests from search backends
_MAX_CONCURRENT_REQUESTS = 8
_request_semaphore = threading.Semaphore(_MAX_CONCURRENT_REQUESTS)


class HTTPSearchBackend(SearchBackend):
    """Fast HTTP-based search using curl_cffi with Chrome 146 TLS fingerprinting.

    Supports: Bing, DuckDuckGo, Google, SearXNG (in reliability order).
    All engines are tried and results are combined with deduplication.
    """

    # SearXNG public instances to try, in order
    SEARXNG_INSTANCES = [
        "https://searx.be",
        "https://search.sapti.me",
    ]

    def __init__(
        self,
        impersonate: str = "chrome146",
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        timeout: float = 15.0,
        max_retries: int = 2,
    ):
        self.impersonate = impersonate
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = None
        self._session_lock = threading.Lock()
        self._session_recreate_count = 0
        self._closed = False
        atexit.register(self.close)

    # ------------------------------------------------------------------
    # Session management with auto-recreation on corruption
    # ------------------------------------------------------------------

    def _get_session(self):
        """Get or create curl_cffi session (thread-safe)."""
        if self._closed:
            return None
        with self._session_lock:
            if self._session is None:
                try:
                    from curl_cffi.requests import Session
                    self._session = Session(impersonate=self.impersonate)
                    logger.debug(f"Created curl_cffi session with impersonate={self.impersonate}")
                except ImportError:
                    logger.error("curl_cffi not installed. Run: pip install curl_cffi")
                    return None
            return self._session

    def _recreate_session(self, reason: str = "unknown"):
        """Destroy and recreate the curl_cffi session (e.g. after SSL errors)."""
        with self._session_lock:
            self._session_recreate_count += 1
            if self._session is not None:
                try:
                    self._session.close()
                except Exception as close_err:
                    logger.debug(f"Error closing session during recreation: {close_err}")
            self._session = None
            try:
                from curl_cffi.requests import Session
                self._session = Session(impersonate=self.impersonate)
                logger.info(
                    f"Recreated curl_cffi session (reason={reason}, count={self._session_recreate_count})"
                )
            except ImportError:
                logger.error("curl_cffi not installed during session recreation")
            return self._session

    def _is_session_corrupted_error(self, exc: Exception) -> bool:
        """Return True if the exception indicates a corrupted/broken session."""
        exc_msg = str(exc).lower()
        corruption_indicators = [
            "ssl",
            "tls",
            "connection reset",
            "broken pipe",
            "connection refused",
            "eof occurred",
            "protocol error",
            "handshake",
            "cert",
            "cursor",  # curl_cffi internal
        ]
        return any(indicator in exc_msg for indicator in corruption_indicators)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check if curl_cffi is available."""
        try:
            import importlib.util
            return importlib.util.find_spec("curl_cffi") is not None
        except ImportError:
            return False

    def close(self):
        """Clean up resources."""
        self._closed = True
        with self._session_lock:
            if self._session is not None:
                try:
                    self._session.close()
                except Exception as close_err:
                    logger.debug(f"Error closing HTTPSearchBackend session: {close_err}")
                self._session = None
        logger.debug("HTTPSearchBackend closed")

    def __del__(self):
        try:
            self.close()
        except Exception:
            logger.debug("HTTPSearchBackend cleanup in __del__ failed")

    async def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Search using HTTP requests with TLS fingerprinting."""
        if self._closed:
            return []
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, self._search_sync, query, max_results)
        return results

    # ------------------------------------------------------------------
    # Core search logic – tries ALL engines and combines results
    # ------------------------------------------------------------------

    def _search_sync(self, query: str, max_results: int = 10) -> list[dict]:
        """Synchronous search: Bing → DuckDuckGo → Google → SearXNG.

        All engines are attempted; results are combined with deduplication
        so that even if the first engine fails, later engines fill in.
        """
        session = self._get_session()
        if session is None:
            return self._search_with_httpx(query, max_results)

        all_results: list[list[dict]] = []

        # Try each engine in order, collecting whatever succeeds
        engine_methods = [
            ("Bing", self._search_bing),
            ("DuckDuckGo", self._search_duckduckgo),
            ("Google", self._search_google),
            ("SearXNG", self._search_searxng),
        ]

        for engine_name, engine_method in engine_methods:
            try:
                results = engine_method(session, query, max_results)
                # Filter out obviously bad results
                valid_results = [r for r in results if self._validate_result(r)]
                if valid_results:
                    logger.debug(f"{engine_name} returned {len(valid_results)} valid results")
                    all_results.append(valid_results)
                else:
                    logger.debug(f"{engine_name} returned no valid results")
            except Exception as e:
                logger.warning(f"{engine_name} search raised exception: {e}")
                # If the session appears corrupted, recreate it before trying next engine
                if self._is_session_corrupted_error(e):
                    new_session = self._recreate_session(reason=str(e))
                    if new_session is not None:
                        session = new_session

        # Combine and dedup results from all engines
        if all_results:
            return combine_results(*all_results, max_results=max_results)

        # Last resort: httpx fallback
        logger.warning("All engines failed, trying httpx fallback...")
        return self._search_with_httpx(query, max_results)

    # ------------------------------------------------------------------
    # Retry with exponential backoff (generic wrapper)
    # ------------------------------------------------------------------

    def _retry_request(
        self,
        session,
        method: str,
        url: str,
        headers: dict,
        timeout: float,
        allow_redirects: bool = True,
        retry_on_status: Optional[set[int]] = None,
    ):
        """Execute an HTTP request with retry + exponential backoff.

        Args:
            session: curl_cffi session
            method: "GET" or "POST"
            url: Request URL
            headers: Request headers
            timeout: Request timeout
            allow_redirects: Whether to follow redirects
            retry_on_status: Set of status codes that trigger a retry
                            (default: {429, 502, 503, 504, 202})

        Returns:
            Response object or None if all retries fail.
        """
        if retry_on_status is None:
            retry_on_status = {429, 502, 503, 504, 202}

        _last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                _request_semaphore.acquire()
                try:
                    if method.upper() == "GET":
                        response = session.get(
                            url, headers=headers, timeout=timeout,
                            allow_redirects=allow_redirects,
                        )
                    else:
                        response = session.post(
                            url, headers=headers, timeout=timeout,
                            allow_redirects=allow_redirects,
                        )
                finally:
                    _request_semaphore.release()

                if response.status_code == 200:
                    return response

                if response.status_code in retry_on_status and attempt < self.max_retries:
                    wait = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s …
                    logger.debug(
                        f"Retry {attempt+1}/{self.max_retries} for {url} "
                        f"(status={response.status_code}), waiting {wait:.1f}s"
                    )
                    time.sleep(wait)
                    continue

                # Non-retryable status
                if response.status_code not in retry_on_status:
                    logger.warning(f"Non-retryable status {response.status_code} for {url}")
                    return response

            except Exception as exc:
                _last_exc = exc
                if self._is_session_corrupted_error(exc) and attempt < self.max_retries:
                    wait = 0.5 * (2 ** attempt)
                    logger.debug(
                        f"Session error on attempt {attempt+1}/{self.max_retries} "
                        f"for {url}: {exc}, recreating session and waiting {wait:.1f}s"
                    )
                    new_session = self._recreate_session(reason=str(exc))
                    if new_session is not None:
                        session = new_session
                    time.sleep(wait)
                    continue
                elif attempt < self.max_retries:
                    wait = 0.5 * (2 ** attempt)
                    logger.debug(
                        f"Request error on attempt {attempt+1}/{self.max_retries} "
                        f"for {url}: {exc}, waiting {wait:.1f}s"
                    )
                    time.sleep(wait)
                    continue
                else:
                    logger.warning(f"All retries exhausted for {url}: {exc}")
                    raise exc

        return None

    # ------------------------------------------------------------------
    # Result validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_result(result: dict) -> bool:
        """Check if a search result is valid and not garbage.

        A valid result must have:
        - Non-empty title
        - A valid HTTP/HTTPS URL
        - URL must not be a search-engine internal/redirect URL
        - Snippet is allowed to be empty but not required
        """
        title = result.get("title", "").strip()
        url = result.get("url", "").strip()

        # Must have a non-empty title
        if not title:
            return False

        # Must have a URL
        if not url:
            return False

        # URL must be http or https
        if not url.startswith(("http://", "https://")):
            return False

        # Parse the URL to ensure it's well-formed
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return False
        except Exception:
            return False

        # Reject search-engine internal URLs
        if _BAD_URL_PATTERNS.match(url):
            return False

        return True

    # ------------------------------------------------------------------
    # Engine: Google
    # ------------------------------------------------------------------

    def _search_google(self, session, query: str, max_results: int) -> list[dict]:
        """Search Google via HTML scraping with retry."""
        try:
            url = f"https://www.google.com/search?q={quote_plus(query)}&num={max_results + 5}&hl=en&gl=us"
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.google.com/",
                "Cookie": "CONSENT=PENDING+987; SOCS=CAESHAgBEhJnd3NfMjAyMzEwMTAtMF9SQzEaAmVuIAEaBgiA-LaoBg",
            }
            response = self._retry_request(session, "GET", url, headers, self.timeout)
            if response is None or response.status_code != 200:
                logger.warning(f"Google returned status {response.status_code if response else 'None'}")
                return []

            results = self._parse_google_results(response.text, max_results)
            if not results:
                results = self._parse_google_results_alt(response.text, max_results)
            return results
        except Exception as e:
            logger.warning(f"Google search failed: {e}")
            return []

    def _parse_google_results(self, html: str, max_results: int) -> list[dict]:
        """Parse Google search results from HTML - primary parser."""
        results = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")

            selectors = ["div.g", "div[data-attrid]", "div.Gx5Zad", "div.yuRUbf"]
            found_divs = []
            for selector in selectors:
                found_divs = soup.select(selector)
                if found_divs:
                    break

            for g_div in found_divs:
                if len(results) >= max_results:
                    break
                title_elem = g_div.select_one("h3") or g_div.select_one("h2")
                title = title_elem.get_text(strip=True) if title_elem else ""
                link_elem = g_div.select_one("a[href]")
                url = link_elem.get("href", "") if link_elem else ""
                if url.startswith("/url?q="):
                    url = url.split("/url?q=")[1].split("&")[0]
                elif url.startswith("/search?"):
                    continue
                elif not url.startswith("http"):
                    continue

                snippet_elem = (
                    g_div.select_one("div[data-sncf]") or
                    g_div.select_one("span.aCOpRe") or
                    g_div.select_one("div.VwiC3b") or
                    g_div.select_one("div.IsZvec") or
                    g_div.select_one("span.st")
                )
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                if title and url:
                    results.append({
                        "title": title, "url": url, "snippet": snippet,
                        "content": "", "relevance_score": 0.7 - (len(results) * 0.05),
                        "source_type": "web", "provider": "google",
                    })
        except Exception as e:
            logger.warning(f"Failed to parse Google results: {e}")
        return results

    def _parse_google_results_alt(self, html: str, max_results: int) -> list[dict]:
        """Alternative Google parser - extracts links with h3 titles."""
        results = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            for h3 in soup.find_all("h3"):
                if len(results) >= max_results:
                    break
                title = h3.get_text(strip=True)
                if not title:
                    continue
                parent_a = h3.find_parent("a") or h3.find_previous_sibling("a")
                if not parent_a:
                    continue
                url = parent_a.get("href", "")
                if url.startswith("/url?q="):
                    url = url.split("/url?q=")[1].split("&")[0]
                elif url.startswith("/search?") or not url.startswith("http"):
                    continue
                snippet = ""
                parent_div = h3.find_parent("div")
                if parent_div:
                    for span in parent_div.find_all("span"):
                        text = span.get_text(strip=True)
                        if len(text) > 30 and text != title:
                            snippet = text
                            break
                results.append({
                    "title": title, "url": url, "snippet": snippet,
                    "content": "", "relevance_score": 0.65 - (len(results) * 0.05),
                    "source_type": "web", "provider": "google",
                })
        except Exception as e:
            logger.debug(f"Alt Google parser failed: {e}")
        return results

    # ------------------------------------------------------------------
    # Engine: Bing
    # ------------------------------------------------------------------

    def _search_bing(self, session, query: str, max_results: int) -> list[dict]:
        """Search Bing via HTML scraping with retry."""
        try:
            url = f"https://www.bing.com/search?q={quote_plus(query)}&count={max_results + 5}&setlang=en&cc=us"
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": self.user_agent,
            }
            response = self._retry_request(session, "GET", url, headers, self.timeout)
            if response is None or response.status_code != 200:
                logger.warning(f"Bing returned status {response.status_code if response else 'None'}")
                return []
            return self._parse_bing_results(response.text, max_results)
        except Exception as e:
            logger.warning(f"Bing search failed: {e}")
            return []

    @staticmethod
    def _decode_bing_url(url: str) -> str:
        """Decode Bing redirect URLs to get the actual target URL."""
        if not url or "bing.com/ck/a" not in url:
            return url
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'u' in params:
                encoded = params['u'][0]
                if encoded.startswith('a1') or encoded.startswith('a3'):
                    encoded = encoded[2:]
                missing_padding = len(encoded) % 4
                if missing_padding:
                    encoded += '=' * (4 - missing_padding)
                decoded = base64.b64decode(encoded).decode('utf-8')
                if decoded.startswith('http'):
                    return decoded
        except Exception as e:
            logger.debug(f"Failed to decode Bing redirect URL: {e}")
        return url

    def _parse_bing_results(self, html: str, max_results: int) -> list[dict]:
        """Parse Bing search results from HTML."""
        results = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            for li in soup.select("li.b_algo"):
                if len(results) >= max_results:
                    break
                title_elem = li.select_one("h2 a")
                title = title_elem.get_text(strip=True) if title_elem else ""
                url = title_elem.get("href", "") if title_elem else ""
                url = self._decode_bing_url(url)
                snippet_elem = li.select_one("p, .b_caption p")
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                if title and url and url.startswith('http'):
                    results.append({
                        "title": title, "url": url, "snippet": snippet,
                        "content": "", "relevance_score": 0.7 - (len(results) * 0.05),
                        "source_type": "web", "provider": "bing",
                    })
        except Exception as e:
            logger.warning(f"Failed to parse Bing results: {e}")
        return results

    # ------------------------------------------------------------------
    # Engine: DuckDuckGo
    # ------------------------------------------------------------------

    def _search_duckduckgo(self, session, query: str, max_results: int) -> list[dict]:
        """Search DuckDuckGo via HTML scraping with retry."""
        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&kl=us-en"
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": self.user_agent,
                "Referer": "https://duckduckgo.com/",
            }
            # Use the generic retry mechanism (202 is DDG's rate-limit indicator)
            response = self._retry_request(
                session, "GET", url, headers, self.timeout,
                retry_on_status={202, 429, 502, 503, 504},
            )
            if response is None or response.status_code != 200:
                return []
            return self._parse_ddg_results(response.text, max_results)
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
            return []

    def _parse_ddg_results(self, html: str, max_results: int) -> list[dict]:
        """Parse DuckDuckGo search results from HTML."""
        results = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            for result_div in soup.select(".result"):
                if len(results) >= max_results:
                    break
                title_elem = result_div.select_one(".result__a")
                title = title_elem.get_text(strip=True) if title_elem else ""
                url = title_elem.get("href", "") if title_elem else ""
                if url.startswith("//duckduckgo.com/l/?uddg="):
                    url = unquote(url.split("uddg=")[1].split("&")[0])
                elif url.startswith("/"):
                    continue
                snippet_elem = result_div.select_one(".result__snippet")
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                if title and url and url.startswith("http"):
                    results.append({
                        "title": title, "url": url, "snippet": snippet,
                        "content": "", "relevance_score": 0.6 - (len(results) * 0.05),
                        "source_type": "web", "provider": "duckduckgo",
                    })

            if not results:
                for link in soup.select("a.result__a"):
                    if len(results) >= max_results:
                        break
                    title = link.get_text(strip=True)
                    url = link.get("href", "")
                    if url.startswith("//duckduckgo.com/l/?uddg="):
                        url = unquote(url.split("uddg=")[1].split("&")[0])
                    if title and url.startswith("http"):
                        results.append({
                            "title": title, "url": url, "snippet": "",
                            "content": "", "relevance_score": 0.55 - (len(results) * 0.05),
                            "source_type": "web", "provider": "duckduckgo",
                        })
        except Exception as e:
            logger.warning(f"Failed to parse DuckDuckGo results: {e}")
        return results

    # ------------------------------------------------------------------
    # Engine: SearXNG (meta-search)
    # ------------------------------------------------------------------

    def _search_searxng(self, session, query: str, max_results: int) -> list[dict]:
        """Search via SearXNG public instances (JSON API) with fallback.

        Tries each configured instance in order; returns results from the
        first one that succeeds.
        """
        for instance_base in self.SEARXNG_INSTANCES:
            try:
                url = f"{instance_base}/search?q={quote_plus(query)}&format=json"
                headers = {
                    "Accept": "application/json",
                    "User-Agent": self.user_agent,
                }
                response = self._retry_request(
                    session, "GET", url, headers, timeout=10.0,
                )
                if response is None or response.status_code != 200:
                    logger.debug(
                        f"SearXNG instance {instance_base} returned "
                        f"status {response.status_code if response else 'None'}"
                    )
                    continue

                results = self._parse_searxng_results(response.text, max_results)
                if results:
                    return results
            except Exception as e:
                logger.debug(f"SearXNG instance {instance_base} failed: {e}")
                continue

        logger.info("All SearXNG instances failed")
        return []

    def _parse_searxng_results(self, response_text: str, max_results: int) -> list[dict]:
        """Parse SearXNG JSON response.

        Expected JSON structure:
        {
            "results": [
                {
                    "title": "...",
                    "url": "...",
                    "content": "..."   # snippet
                },
                ...
            ]
        }
        """
        results = []
        try:
            data = json.loads(response_text)
            raw_results = data.get("results", [])
            for item in raw_results:
                if len(results) >= max_results:
                    break
                title = (item.get("title") or "").strip()
                url = (item.get("url") or "").strip()
                snippet = (item.get("content") or "").strip()

                if title and url and url.startswith(("http://", "https://")):
                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "content": "",
                        "relevance_score": 0.55 - (len(results) * 0.05),
                        "source_type": "web",
                        "provider": "searxng",
                    })
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse SearXNG results: {e}")
        return results

    # ------------------------------------------------------------------
    # httpx fallback (no curl_cffi)
    # ------------------------------------------------------------------

    def _search_with_httpx(self, query: str, max_results: int) -> list[dict]:
        """Fallback search using httpx (no TLS fingerprinting)."""
        try:
            import httpx
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            headers = {"User-Agent": self.user_agent}
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
                if response.status_code == 200:
                    results = self._parse_ddg_results(response.text, max_results)
                    return [r for r in results if self._validate_result(r)]
        except Exception as e:
            logger.error(f"httpx fallback search failed: {e}")
        return []

    # ------------------------------------------------------------------
    # Content extraction
    # ------------------------------------------------------------------

    async def extract_content(self, url: str) -> Optional[str]:
        """Extract text content from a URL."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._extract_content_sync, url)

    def _extract_content_sync(self, url: str) -> Optional[str]:
        """Synchronous content extraction."""
        try:
            session = self._get_session()
            if session is None:
                return None
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            response = session.get(url, headers=headers, timeout=self.timeout, allow_redirects=True)
            if response.status_code != 200:
                return None
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, "lxml")
            for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
                element.decompose()
            text = soup.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            content = "\n".join(lines)
            if len(content) > 5000:
                content = content[:5000] + "..."
            return content
        except Exception as e:
            logger.warning(f"Content extraction failed for {url}: {e}")
            return None
