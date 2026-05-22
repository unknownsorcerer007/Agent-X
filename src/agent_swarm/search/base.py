"""Abstract base classes for search backends and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum
from urllib.parse import urlparse, parse_qsl, urlencode


class SearchProvider(str, Enum):
    """Available search providers."""
    GOOGLE = "google"
    BING = "bing"
    DUCKDUCKGO = "duckduckgo"
    SEARXNG = "searxng"
    AGENT_OS = "agent_os"
    HTTP = "http"


@dataclass
class SearchRequest:
    """A search request."""
    query: str
    max_results: int = 10
    provider: SearchProvider = SearchProvider.GOOGLE
    extract_content: bool = False
    timeout: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResultItem:
    """A single search result."""
    title: str
    url: str
    snippet: str = ""
    content: str = ""
    relevance_score: float = 0.5
    source_type: str = "web"
    provider: str = ""
    rank: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchBackend(ABC):
    """Abstract base class for search backends."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Execute a search query."""
        pass

    @abstractmethod
    async def extract_content(self, url: str) -> Optional[str]:
        """Extract content from a URL."""
        pass

    def is_available(self) -> bool:
        """Check if this backend is available and properly configured."""
        return True


def combine_results(
    *result_lists: list[dict],
    max_results: int = 10,
    dedup_key: str = "url",
) -> list[dict]:
    """Merge results from multiple search backends with deduplication.

    Results are interleaved by provider order so that higher-priority
    providers appear first, but results from later providers fill in
    gaps.  Duplicates (same normalised URL) are dropped.

    Args:
        *result_lists: Any number of result lists (each a list[dict]).
        max_results: Maximum number of results to return.
        dedup_key: Dict key used for deduplication (default "url").

    Returns:
        A deduplicated, merged list of result dicts.
    """
    seen_urls: set[str] = set()
    combined: list[dict] = []

    def _normalise_url(url: str) -> str:
        """Normalise a URL for dedup – strip trailing slash, fragment, sort query."""
        try:
            parsed = urlparse(url)
            # Lower-case netloc, strip trailing slash on path, drop fragment
            norm = f"{parsed.scheme}://{parsed.netloc.lower()}{parsed.path.rstrip('/') or '/'}"
            # Keep query but sort params for stable comparison
            if parsed.query:
                params = parse_qsl(parsed.query)
                params.sort()
                norm += "?" + urlencode(params)
            return norm
        except Exception:
            return url.lower().rstrip("/")

    for result_list in result_lists:
        for item in result_list:
            raw_val = item.get(dedup_key, "")
            if not raw_val:
                continue
            norm = _normalise_url(raw_val)
            if norm in seen_urls:
                continue
            seen_urls.add(norm)
            combined.append(item)
            if len(combined) >= max_results:
                return combined

    return combined
