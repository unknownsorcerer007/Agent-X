"""Router module - 3-tier query routing system.

Tier 1: RuleBasedRouter (fast, free, pattern matching)
Tier 2: ProviderRouter using user's provider as brain (only if configured)
Tier 3: ConservativeRouter (always returns NEEDS_WEB as safe fallback)
"""

from src.agent_swarm.router.rule_based import RuleBasedRouter, QueryClassification, QueryCategory
from src.agent_swarm.router.provider_router import ProviderRouter
from src.agent_swarm.router.conservative import ConservativeRouter
from src.agent_swarm.router.orchestrator import QueryRouter

__all__ = [
    "QueryRouter",
    "QueryClassification",
    "QueryCategory",
    "RuleBasedRouter",
    "ProviderRouter",
    "ConservativeRouter",
]
