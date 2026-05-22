"""Tier 3: Conservative router - always returns NEEDS_WEB."""

from src.agent_swarm.router.rule_based import QueryClassification, QueryCategory


class ConservativeRouter:
    """Tier 3: Conservative default router.

    When both Tier 1 (rule-based) and Tier 2 (provider) are uncertain,
    always classify as NEEDS_WEB. It's safer to over-search than
    miss critical information.
    """

    def classify(self, query: str) -> QueryClassification:
        """Classify query as NEEDS_WEB (conservative default)."""
        return QueryClassification(
            category=QueryCategory.NEEDS_WEB,
            confidence=0.5,
            reason="conservative_fallback",
            source="conservative",
            suggested_agents=["generalist"],
            search_queries=[query],
        )
