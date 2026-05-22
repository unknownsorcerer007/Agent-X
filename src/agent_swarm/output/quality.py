"""Quality scoring for search results."""

import logging
import datetime
from typing import Optional

from src.agent_swarm.agents.base import AgentResult

logger = logging.getLogger(__name__)


class QualityScorer:
    """Scores the quality of search results based on multiple factors."""

    TRUSTED_DOMAINS = {
        "wikipedia.org", "reuters.com", "apnews.com", "bbc.com",
        "nature.com", "science.org", "arxiv.org", "github.com",
        "stackoverflow.com", "docs.python.org", "developer.mozilla.org",
        "python.org", "rust-lang.org", "golang.org",
    }

    LOW_QUALITY_DOMAINS = {
        "pinterest.com", "facebook.com", "twitter.com", "tiktok.com",
        "instagram.com", "reddit.com/r/",
    }

    def __init__(self, query: Optional[str] = None):
        self.query = query or ""
        self.query_words = set(self.query.lower().split()) if self.query else set()

    def score(self, result: AgentResult) -> float:
        """Calculate a quality score for a search result."""
        score = 0.5
        score += self._domain_score(result.url)
        score += self._content_length_score(result.content)
        score += self._relevance_score(result.title, result.snippet)
        score += self._freshness_score(result.url)
        return max(0.0, min(1.0, score))

    def _domain_score(self, url: str) -> float:
        """Score based on domain trustworthiness."""
        url_lower = url.lower()
        for domain in self.TRUSTED_DOMAINS:
            if domain in url_lower:
                return 0.15
        for domain in self.LOW_QUALITY_DOMAINS:
            if domain in url_lower:
                return -0.1
        return 0.0

    def _content_length_score(self, content: str) -> float:
        """Score based on content length."""
        if not content:
            return -0.1
        word_count = len(content.split())
        if word_count < 20:
            return -0.1
        elif word_count < 100:
            return 0.0
        elif word_count < 500:
            return 0.05
        else:
            return 0.1

    def _relevance_score(self, title: str, snippet: str) -> float:
        """Score based on query keyword overlap."""
        if not self.query_words:
            return 0.0
        combined = f"{title} {snippet}".lower()
        combined_words = set(combined.split())
        overlap = len(self.query_words & combined_words)
        total = len(self.query_words)
        if total == 0:
            return 0.0
        ratio = overlap / total
        return min(0.2, ratio * 0.2)

    def _freshness_score(self, url: str) -> float:
        """Score based on content freshness."""
        current_year = datetime.datetime.now().year
        for year in [current_year, current_year - 1]:
            if str(year) in url:
                return 0.05
        return 0.0
