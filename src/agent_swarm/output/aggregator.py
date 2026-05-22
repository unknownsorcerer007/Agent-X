"""Result aggregation - combines results from multiple agents."""

import logging

from src.agent_swarm.agents.base import AgentResult

logger = logging.getLogger(__name__)


class ResultAggregator:
    """Aggregates and deduplicates results from multiple search agents."""

    def __init__(
        self,
        deduplicate: bool = True,
        min_relevance: float = 0.3,
        max_results: int = 10,
    ):
        self.deduplicate = deduplicate
        self.min_relevance = min_relevance
        self.max_results = max_results

    def aggregate(self, agent_results: list[AgentResult]) -> list[AgentResult]:
        """Aggregate results from multiple agents."""
        valid_results = [
            r for r in agent_results
            if r.status.value == "completed" and r.url
        ]

        logger.info(f"Aggregating {len(valid_results)} valid results from {len(agent_results)} total")

        if not valid_results:
            return []

        if self.deduplicate:
            valid_results = self._deduplicate(valid_results)

        valid_results = self._cross_reference_boost(valid_results)

        valid_results = [
            r for r in valid_results
            if r.relevance_score >= self.min_relevance
        ]

        valid_results.sort(key=lambda x: x.relevance_score, reverse=True)
        return valid_results[:self.max_results]

    def _deduplicate(self, results: list[AgentResult]) -> list[AgentResult]:
        """Remove duplicate results based on URL similarity.

        Uses a dict for O(1) lookup instead of O(n²) linear scan.
        When a duplicate URL is found, the result with the higher
        relevance_score is kept.
        """
        seen: dict[str, int] = {}  # normalized_url → index in unique_results
        unique_results: list[AgentResult] = []

        for result in results:
            normalized_url = self._normalize_url(result.url)
            if normalized_url not in seen:
                seen[normalized_url] = len(unique_results)
                unique_results.append(result)
            else:
                # Duplicate — keep the higher quality result
                idx = seen[normalized_url]
                existing = unique_results[idx]
                if result.relevance_score > existing.relevance_score:
                    # Replace with higher-quality result, but merge content
                    existing.content = result.content if len(result.content) > len(existing.content) else existing.content
                    existing.snippet = result.snippet or existing.snippet
                    existing.relevance_score = result.relevance_score
                elif len(result.content) > len(existing.content):
                    # Keep existing but merge longer content
                    existing.content = result.content
                    existing.snippet = result.snippet or existing.snippet

        logger.info(f"Deduplication: {len(results)} → {len(unique_results)} results")
        return unique_results

    def _normalize_url(self, url: str) -> str:
        """Normalize a URL for deduplication comparison."""
        url = url.lower().strip()
        url = url.rstrip("/")
        if "?" in url:
            base, params = url.split("?", 1)
            essential = []
            for param in params.split("&"):
                key = param.split("=")[0]
                if key not in ("utm_source", "utm_medium", "utm_campaign", "ref", "fbclid", "gclid"):
                    essential.append(param)
            if essential:
                url = base + "?" + "&".join(essential)
            else:
                url = base
        url = url.replace("www.", "")
        url = url.replace("https://", "").replace("http://", "")
        return url

    def _cross_reference_boost(self, results: list[AgentResult]) -> list[AgentResult]:
        """Boost relevance score for results found by multiple agents."""
        url_counts = {}
        for result in results:
            normalized = self._normalize_url(result.url)
            url_counts[normalized] = url_counts.get(normalized, 0) + 1

        for result in results:
            normalized = self._normalize_url(result.url)
            count = url_counts.get(normalized, 1)
            if count > 1:
                boost = (count - 1) * 0.1
                result.relevance_score = min(1.0, result.relevance_score + boost)
                logger.debug(f"Boosted {result.url} by {boost:.2f} (found by {count} agents)")

        return results
