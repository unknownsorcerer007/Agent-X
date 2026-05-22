"""Search strategies - how agents plan and execute their searches."""

import logging
from dataclasses import dataclass
from enum import Enum

from src.agent_swarm.agents.profiles import SearchProfile

logger = logging.getLogger(__name__)


class SearchStrategy(str, Enum):
    """Available search strategies."""
    BROAD = "broad"
    FOCUSED = "focused"
    DEEP = "deep"
    QUICK = "quick"
    COMPARISON = "comparison"


@dataclass
class SearchPlan:
    """A plan for how an agent will execute its search."""
    strategy: SearchStrategy
    queries: list[str]
    max_results_per_query: int
    extract_full_content: bool
    follow_links: bool
    timeout: float

    @property
    def estimated_time(self) -> float:
        """Estimate total search time."""
        base = len(self.queries) * 2.0
        if self.extract_full_content:
            base *= 1.5
        if self.follow_links:
            base *= 2.0
        return min(base, self.timeout)


def create_search_plan(
    profile: SearchProfile,
    query: str,
    max_results: int = 10,
    timeout: float = 30.0,
) -> SearchPlan:
    """Create a search plan based on agent profile and query."""
    strategy_map = {
        "quick": SearchStrategy.QUICK,
        "medium": SearchStrategy.FOCUSED,
        "thorough": SearchStrategy.DEEP,
    }
    strategy = strategy_map.get(profile.search_depth, SearchStrategy.FOCUSED)

    queries = _generate_queries(profile, query)

    extract_full = strategy in (SearchStrategy.DEEP, SearchStrategy.COMPARISON)
    follow_links = strategy == SearchStrategy.DEEP

    per_query = max(3, max_results // len(queries)) if queries else max_results

    return SearchPlan(
        strategy=strategy,
        queries=queries,
        max_results_per_query=per_query,
        extract_full_content=extract_full,
        follow_links=follow_links,
        timeout=timeout,
    )


def _generate_queries(profile: SearchProfile, original_query: str) -> list[str]:
    """Generate search queries based on profile's query style."""
    queries = [original_query]

    if profile.query_style == "factual_direct":
        if "latest" not in original_query.lower() and any(
            kw in original_query.lower() for kw in ["news", "update", "release"]
        ):
            queries.append(f"latest {original_query}")

    elif profile.query_style == "specific_targeted":
        queries.append(f"{original_query} price review compare")

    elif profile.query_style == "technical_precise":
        queries.append(f"{original_query} documentation")
        queries.append(f"{original_query} tutorial example")

    elif profile.query_style == "exploratory_detailed":
        queries.append(f"{original_query} detailed analysis")
        queries.append(f"{original_query} research study")

    else:
        if len(original_query.split()) < 4:
            queries.append(f"{original_query} information guide")

    return queries[:3]
