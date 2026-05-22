"""Advanced deduplication utilities."""

import re
import hashlib
import logging
from difflib import SequenceMatcher

from src.agent_swarm.agents.base import AgentResult

logger = logging.getLogger(__name__)


class Deduplicator:
    """Advanced deduplication using content similarity and URL matching."""

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold

    def deduplicate(self, results: list[AgentResult]) -> list[AgentResult]:
        """Remove duplicate and near-duplicate results.

        Dedup rules (in priority order):
        1. Same/similar URL → duplicate (regardless of title)
        2. Very similar title AND same domain → duplicate
        3. Very similar content (>0.9) AND same domain → duplicate

        Titles from DIFFERENT domains are never considered duplicates,
        because different sources covering the same topic is not duplication.
        """
        if len(results) <= 1:
            return results

        unique = [results[0]]

        for result in results[1:]:
            is_duplicate = False
            for existing in unique:
                # Rule 1: URL similarity always trumps
                if self._urls_similar(result.url, existing.url):
                    is_duplicate = True
                    break

                # Rule 2 & 3: Title/content similarity only counts on same domain
                result_domain = self._extract_domain(self._normalize_url(result.url))
                existing_domain = self._extract_domain(self._normalize_url(existing.url))
                same_domain = bool(result_domain and existing_domain and result_domain == existing_domain)

                if same_domain:
                    if self._texts_similar(result.title, existing.title, self.similarity_threshold):
                        is_duplicate = True
                        break
                    if result.content and existing.content:
                        if self._texts_similar(result.content[:500], existing.content[:500], 0.9):
                            is_duplicate = True
                            break
            if not is_duplicate:
                unique.append(result)

        return unique

    def _urls_similar(self, url1: str, url2: str) -> bool:
        """Check if two URLs are similar enough to be considered duplicates."""
        norm1 = self._normalize_url(url1)
        norm2 = self._normalize_url(url2)
        if norm1 == norm2:
            return True
        # Domain boundary check: extract domains and compare
        domain1 = self._extract_domain(norm1)
        domain2 = self._extract_domain(norm2)
        if domain1 and domain2 and domain1 != domain2:
            return False
        # Only allow substring match if the shorter URL is a path prefix of the longer
        if norm1 in norm2:
            # Ensure norm1 is a proper path prefix, not a partial domain match
            remainder = norm2[len(norm1):]
            if remainder and not remainder.startswith("/") and not remainder.startswith("?") and not remainder.startswith("#"):
                return False
            return True
        if norm2 in norm1:
            remainder = norm1[len(norm2):]
            if remainder and not remainder.startswith("/") and not remainder.startswith("?") and not remainder.startswith("#"):
                return False
            return True
        return False

    def _extract_domain(self, normalized_url: str) -> str:
        """Extract the domain from a normalized URL."""
        parts = normalized_url.split("/")
        return parts[0] if parts else ""

    def _texts_similar(self, text1: str, text2: str, threshold: float) -> bool:
        """Check if two texts are similar using sequence matching."""
        if not text1 or not text2:
            return False
        ratio = SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
        return ratio >= threshold

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison."""
        url = url.lower().strip()
        url = url.rstrip("/")
        url = re.sub(r"https?://(www\.)?", "", url)
        url = re.sub(r"[?&](utm_[^&=]+|ref|fbclid|gclid)=[^&]*", "", url)
        return url

    def content_hash(self, text: str) -> str:
        """Generate a hash for content fingerprinting."""
        normalized = re.sub(r"\s+", " ", text.lower().strip())
        return hashlib.md5(normalized.encode()).hexdigest()
