"""Query Router Orchestrator - coordinates the 3-tier routing system.

Production features:
- Uses user's configured provider as the brain (Tier 2)
- Tracks metrics per tier (calls, latency, classifications)
- Thread-safe operation
- Graceful degradation when no provider configured
- Tier 1 + Tier 3 always work even without any provider
"""

import logging
import time
import threading
from typing import Optional
from collections import defaultdict

from src.agent_swarm.router.rule_based import RuleBasedRouter, QueryClassification, QueryCategory
from src.agent_swarm.router.provider_router import ProviderRouter
from src.agent_swarm.router.conservative import ConservativeRouter

logger = logging.getLogger(__name__)


class TierMetrics:
    """Thread-safe metrics tracker for a routing tier."""

    def __init__(self, name: str):
        self.name = name
        self._lock = threading.Lock()
        self._calls = 0
        self._classifications = defaultdict(int)  # category → count
        self._total_latency_ms = 0.0
        self._errors = 0

    def record(self, category: QueryCategory, latency_ms: float, error: bool = False):
        with self._lock:
            self._calls += 1
            self._classifications[category.value] += 1
            self._total_latency_ms += latency_ms
            if error:
                self._errors += 1

    @property
    def stats(self) -> dict:
        with self._lock:
            avg_latency = (self._total_latency_ms / self._calls) if self._calls > 0 else 0.0
            return {
                "name": self.name,
                "calls": self._calls,
                "classifications": dict(self._classifications),
                "avg_latency_ms": round(avg_latency, 2),
                "errors": self._errors,
            }


class QueryRouter:
    """3-tier hybrid query router.

    Tier 1: Rule-based (fast, free, zero latency)
        - Pattern matching with comprehensive regex patterns
        - Always available, no external dependency
        - Handles 80%+ of queries correctly

    Tier 2: User's Provider as Brain (only if user configured a provider)
        - Uses the SAME provider the user has (OpenAI, Anthropic, Google, etc.)
        - NOT a separate LLM — user's provider IS the brain
        - Only activates when user has an API key configured
        - Handles ambiguous queries that Tier 1 can't classify confidently

    Tier 3: Conservative default (always returns NEEDS_WEB)
        - Always available, zero dependency
        - Safe fallback: better to over-search than miss critical info

    The router cascades through tiers based on confidence threshold.
    If Tier 1 is confident enough, Tier 2 and 3 are skipped.
    If Tier 1 is uncertain, Tier 2 is tried (if available).
    If Tier 2 is also uncertain, Tier 3 provides a safe default.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        enable_provider_fallback: bool = True,
        provider_api_key: Optional[str] = None,
        provider_base_url: Optional[str] = None,
        provider_model: Optional[str] = None,
        provider_name: Optional[str] = None,
        provider_max_tokens: int = 150,
        provider_timeout: float = 8.0,
    ):
        self.confidence_threshold = confidence_threshold
        self.enable_provider_fallback = enable_provider_fallback

        # Tier 1: Rule-based (always available)
        self.tier1 = RuleBasedRouter(confidence_threshold=confidence_threshold)
        self._tier1_metrics = TierMetrics("rule_based")

        # Tier 2: User's provider as brain (only if they have one configured)
        self.tier2 = None
        if enable_provider_fallback:
            self.tier2 = ProviderRouter(
                api_key=provider_api_key,
                base_url=provider_base_url,
                model=provider_model,
                provider=provider_name,
                max_tokens=provider_max_tokens,
                timeout=provider_timeout,
            )
        self._tier2_metrics = TierMetrics("user_provider")

        # Tier 3: Conservative (always available)
        self.tier3 = ConservativeRouter()
        self._tier3_metrics = TierMetrics("conservative")

        # Overall metrics
        self._total_queries = 0
        self._total_latency_ms = 0.0

        # Log provider availability
        if self.tier2:
            available = self.tier2.is_available()
            if available:
                provider_name = getattr(self.tier2, 'provider', 'unknown') or 'unknown'
                logger.info(
                    f"Tier 2 available: provider={provider_name}, "
                    f"model={self.tier2.model}, base_url={self.tier2.base_url}"
                )
            else:
                logger.info(
                    "Tier 2 not available (no user provider configured). "
                    "Tier 1 + Tier 3 will handle all routing."
                )

    def route(self, query: str) -> QueryClassification:
        """Route a query through the 3-tier system.

        Returns a QueryClassification with the best available category,
        confidence, suggested agents, and search queries.
        """
        start_time = time.monotonic()
        self._total_queries += 1

        # ─── Tier 1: Rule-based (always runs, fast & free) ───
        tier1_start = time.monotonic()
        tier1_result = self.tier1.classify(query)
        tier1_latency = (time.monotonic() - tier1_start) * 1000
        self._tier1_metrics.record(tier1_result.category, tier1_latency)

        logger.debug(
            f"Tier 1: category={tier1_result.category.value}, "
            f"confidence={tier1_result.confidence:.2f}, latency={tier1_latency:.1f}ms"
        )

        if tier1_result.confidence >= self.confidence_threshold:
            total_latency = (time.monotonic() - start_time) * 1000
            self._total_latency_ms += total_latency
            logger.info(
                f"Tier 1 classified as {tier1_result.category.value} "
                f"(confidence: {tier1_result.confidence:.2f}, latency: {total_latency:.1f}ms)"
            )
            return tier1_result

        # ─── Tier 2: User's provider as brain (only if enabled and available) ───
        if self.tier2 and self.tier2.is_available():
            tier2_start = time.monotonic()
            try:
                tier2_result = self.tier2.classify(query)
                tier2_latency = (time.monotonic() - tier2_start) * 1000

                if tier2_result is not None:
                    self._tier2_metrics.record(tier2_result.category, tier2_latency)
                    logger.debug(
                        f"Tier 2: category={tier2_result.category.value}, "
                        f"confidence={tier2_result.confidence:.2f}, latency={tier2_latency:.1f}ms"
                    )

                    if tier2_result.confidence >= self.confidence_threshold:
                        total_latency = (time.monotonic() - start_time) * 1000
                        self._total_latency_ms += total_latency
                        # Merge Tier 1 agents if Tier 2 didn't provide any
                        if not tier2_result.suggested_agents:
                            tier2_result.suggested_agents = tier1_result.suggested_agents or ["generalist"]
                        if not tier2_result.search_queries:
                            tier2_result.search_queries = tier1_result.search_queries or [query]
                        logger.info(
                            f"Tier 2 classified as {tier2_result.category.value} "
                            f"(confidence: {tier2_result.confidence:.2f}, latency: {total_latency:.1f}ms)"
                        )
                        return tier2_result
                else:
                    self._tier2_metrics.record(tier1_result.category, tier2_latency, error=True)
                    logger.debug("Tier 2 returned None (provider unavailable or error)")
            except Exception as e:
                tier2_latency = (time.monotonic() - tier2_start) * 1000
                self._tier2_metrics.record(tier1_result.category, tier2_latency, error=True)
                logger.warning(f"Tier 2 exception: {e}")

        # ─── Tier 3: Conservative default (always returns NEEDS_WEB) ───
        tier3_start = time.monotonic()
        tier3_result = self.tier3.classify(query)
        tier3_latency = (time.monotonic() - tier3_start) * 1000
        self._tier3_metrics.record(tier3_result.category, tier3_latency)

        total_latency = (time.monotonic() - start_time) * 1000
        self._total_latency_ms += total_latency

        # Use Tier 1's suggested agents and search queries for Tier 3 result
        tier3_result.suggested_agents = tier1_result.suggested_agents or ["generalist"]
        tier3_result.search_queries = tier1_result.search_queries or [query]

        logger.info(
            f"Tier 3 fallback: NEEDS_WEB "
            f"(latency: {total_latency:.1f}ms)"
        )
        return tier3_result

    def update_provider_config(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        """Update user's provider configuration at runtime.

        This is called when user changes their provider in the UI.
        The new provider becomes the brain for Tier 2 classification.
        """
        if self.tier2 is None:
            self.tier2 = ProviderRouter()

        if api_key is not None:
            self.tier2.api_key = api_key
            self.tier2.reset_client()
        if base_url is not None:
            self.tier2.base_url = base_url
            self.tier2.reset_client()
        if model is not None:
            self.tier2.model = model
            self.tier2.reset_client()
        if provider is not None:
            self.tier2.provider = provider
            self.tier2.reset_client()

        # Clear cache when config changes
        self.tier2.clear_cache()

        logger.info(
            f"User provider config updated: provider={provider or self.tier2.provider}, "
            f"model={self.tier2.model}, base_url={self.tier2.base_url}"
        )

    @property
    def metrics(self) -> dict:
        """Return comprehensive routing metrics."""
        return {
            "total_queries": self._total_queries,
            "avg_total_latency_ms": round(
                self._total_latency_ms / max(self._total_queries, 1), 2
            ),
            "confidence_threshold": self.confidence_threshold,
            "tier1": self._tier1_metrics.stats,
            "tier2": self._tier2_metrics.stats,
            "tier3": self._tier3_metrics.stats,
            "provider_available": self.tier2.is_available() if self.tier2 else False,
            "provider_info": self.tier2.stats if self.tier2 else {},
        }


__all__ = ["QueryRouter", "QueryClassification", "QueryCategory"]
