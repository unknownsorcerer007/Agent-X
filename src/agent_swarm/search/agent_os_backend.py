"""Agent-OS browser-based search backend."""

import logging
import asyncio
import threading
import atexit
from typing import Optional

import httpx

from src.agent_swarm.search.base import SearchBackend

logger = logging.getLogger(__name__)


class AgentOSBackend(SearchBackend):
    """Uses Agent-OS's browser automation for search.

    Connects to the Agent-OS HTTP API and uses its browser
    to perform web searches with full JavaScript rendering.
    """

    def __init__(
        self,
        agent_os_url: str = "http://localhost:8001",
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.agent_os_url = agent_os_url
        self.api_key = api_key
        self.timeout = timeout
        self._client = None
        self._client_lock = threading.Lock()
        self._closed = False
        atexit.register(self.close)

    def _get_client(self) -> httpx.Client:
        """Get or create httpx client for Agent-OS communication."""
        with self._client_lock:
            if self._client is None:
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-Client": "Agent-Swarm/1.0",
                }
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                self._client = httpx.Client(
                    base_url=self.agent_os_url,
                    timeout=self.timeout,
                    verify=False,
                    headers=headers,
                )
            return self._client

    def is_available(self) -> bool:
        """Check if Agent-OS server is reachable."""
        try:
            client = self._get_client()
            response = client.get("/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    def close(self):
        """Clean up resources."""
        self._closed = True
        with self._client_lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception as close_err:
                    logger.debug(f"Error closing AgentOSBackend client: {close_err}")
                self._client = None
        logger.debug("AgentOSBackend closed")

    def __del__(self):
        try:
            self.close()
        except Exception:
            logger.debug("AgentOSBackend cleanup in __del__ failed")

    async def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Search using Agent-OS browser automation."""
        if self._closed:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._search_sync, query, max_results)

    def _search_sync(self, query: str, max_results: int = 10) -> list[dict]:
        """Synchronous search via Agent-OS API."""
        try:
            client = self._get_client()
            # Use Agent-OS navigate + get-content pattern
            search_url = f"https://www.bing.com/search?q={query}&count={max_results}"

            # Navigate to search engine
            nav_payload = {
                "command": "navigate",
                "url": search_url,
            }
            nav_response = client.post("/command", json=nav_payload, timeout=45.0)
            if nav_response.status_code != 200:
                logger.warning(f"Agent-OS navigation failed: {nav_response.status_code}")
                return []

            # Get page content
            content_payload = {
                "command": "get-content",
            }
            content_response = client.post("/command", json=content_payload, timeout=30.0)
            if content_response.status_code != 200:
                return []

            data = content_response.json()
            content = data.get("content", "")
            if not content:
                return []

            # Parse results from the rendered page
            return self._parse_rendered_results(content, query, max_results)

        except Exception as e:
            logger.warning(f"Agent-OS browser search failed: {e}")
            return []

    def _parse_rendered_results(self, html: str, query: str, max_results: int) -> list[dict]:
        """Parse search results from browser-rendered HTML."""
        results = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")

            # Try Bing result selectors
            for li in soup.select("li.b_algo"):
                if len(results) >= max_results:
                    break
                title_elem = li.select_one("h2 a")
                title = title_elem.get_text(strip=True) if title_elem else ""
                url = title_elem.get("href", "") if title_elem else ""
                snippet_elem = li.select_one("p, .b_caption p")
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                if title and url and url.startswith('http'):
                    results.append({
                        "title": title, "url": url, "snippet": snippet,
                        "content": "", "relevance_score": 0.75 - (len(results) * 0.05),
                        "source_type": "web", "provider": "agent_os_browser",
                    })

            # Try Google result selectors
            if not results:
                for g_div in soup.select("div.g"):
                    if len(results) >= max_results:
                        break
                    title_elem = g_div.select_one("h3")
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    link_elem = g_div.select_one("a[href]")
                    url = link_elem.get("href", "") if link_elem else ""
                    if url.startswith("/url?q="):
                        url = url.split("/url?q=")[1].split("&")[0]
                    elif not url.startswith("http"):
                        continue
                    snippet_elem = g_div.select_one("div.VwiC3b") or g_div.select_one("span.st")
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    if title and url:
                        results.append({
                            "title": title, "url": url, "snippet": snippet,
                            "content": "", "relevance_score": 0.7 - (len(results) * 0.05),
                            "source_type": "web", "provider": "agent_os_browser",
                        })

        except Exception as e:
            logger.warning(f"Failed to parse rendered results: {e}")
        return results

    async def extract_content(self, url: str) -> Optional[str]:
        """Extract content from a URL using Agent-OS browser."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._extract_content_sync, url)

    def _extract_content_sync(self, url: str) -> Optional[str]:
        """Synchronous content extraction via Agent-OS."""
        try:
            client = self._get_client()
            nav_payload = {"command": "navigate", "url": url}
            nav_response = client.post("/command", json=nav_payload, timeout=45.0)
            if nav_response.status_code != 200:
                return None

            content_payload = {"command": "get-content"}
            content_response = client.post("/command", json=content_payload, timeout=30.0)
            if content_response.status_code != 200:
                return None

            data = content_response.json()
            content = data.get("content", "")
            if content and len(content) > 5000:
                content = content[:5000] + "..."
            return content

        except Exception as e:
            logger.warning(f"Agent-OS content extraction failed for {url}: {e}")
            return None
