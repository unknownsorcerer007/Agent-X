"""Base SearchAgent class - the core agent abstraction."""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent execution status."""
    IDLE = "idle"
    SEARCHING = "searching"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentResult:
    """Result from a single search agent."""
    agent_name: str
    agent_profile: str
    query: str
    title: str = ""
    url: str = ""
    snippet: str = ""
    content: str = ""
    relevance_score: float = 0.0
    source_type: str = "web"
    status: AgentStatus = AgentStatus.IDLE
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchAgent:
    """Base class for search agents.

    Each agent has a profile that defines its search behavior,
    preferred sources, and query reformulation strategy.
    """

    def __init__(
        self,
        name: str,
        profile_name: str,
        expertise: str,
        preferred_sources: list[str] = None,
        search_depth: str = "medium",
        query_style: str = "broad_exploratory",
    ):
        self.name = name
        self.profile_name = profile_name
        self.expertise = expertise
        self.preferred_sources = preferred_sources or []
        self.search_depth = search_depth
        self.query_style = query_style
        self.status = AgentStatus.IDLE
        self._last_result: Optional[AgentResult] = None

    def reformulate_query(self, original_query: str) -> str:
        """Reformulate the query based on agent's expertise and style."""
        if self.query_style == "factual_direct":
            return original_query.strip()
        elif self.query_style == "specific_targeted":
            terms = ["price", "buy", "cost", "review", "compare"]
            if not any(t in original_query.lower() for t in terms):
                return f"{original_query} price review"
            return original_query.strip()
        elif self.query_style == "technical_precise":
            terms = ["documentation", "github", "stack overflow", "api", "tutorial"]
            if not any(t in original_query.lower() for t in terms):
                return f"{original_query} documentation tutorial"
            return original_query.strip()
        elif self.query_style == "exploratory_detailed":
            return f"{original_query} detailed analysis research"
        else:
            return original_query.strip()

    def generate_search_queries(self, original_query: str) -> list[str]:
        """Generate multiple search queries for broader coverage."""
        queries = [original_query]
        reformulated = self.reformulate_query(original_query)
        if reformulated != original_query:
            queries.append(reformulated)

        for source in self.preferred_sources[:1]:
            if source != "any" and source not in original_query.lower():
                skip_sites = {"google.com", "bing.com", "duckduckgo.com", "scholar.google.com"}
                if source not in skip_sites:
                    queries.append(f"site:{source} {original_query}")

        return queries[:2]

    async def search(self, query: str, search_backend) -> AgentResult:
        """Execute a search using this agent's profile."""
        start_time = time.time()
        self.status = AgentStatus.SEARCHING

        try:
            queries = self.generate_search_queries(query)
            logger.info(f"Agent '{self.name}' searching with {len(queries)} queries")

            all_results = []
            for q in queries:
                try:
                    results = await search_backend.search(q)
                    all_results.extend(results)
                except Exception as e:
                    logger.warning(f"Agent '{self.name}' search failed for '{q[:30]}...': {e}")
                    continue

            best_result = self._select_best_result(all_results, query)
            self.status = AgentStatus.COMPLETED
            execution_time = time.time() - start_time

            if best_result:
                result = AgentResult(
                    agent_name=self.name,
                    agent_profile=self.profile_name,
                    query=query,
                    title=best_result.get("title", ""),
                    url=best_result.get("url", ""),
                    snippet=best_result.get("snippet", ""),
                    content=best_result.get("content", ""),
                    relevance_score=best_result.get("relevance_score", 0.5),
                    source_type=best_result.get("source_type", "web"),
                    status=AgentStatus.COMPLETED,
                    execution_time=execution_time,
                )
            else:
                result = AgentResult(
                    agent_name=self.name,
                    agent_profile=self.profile_name,
                    query=query,
                    status=AgentStatus.COMPLETED,
                    execution_time=execution_time,
                    error="no_results_found",
                )

            self._last_result = result
            return result

        except Exception as e:
            self.status = AgentStatus.FAILED
            execution_time = time.time() - start_time
            logger.error(f"Agent '{self.name}' failed: {e}")
            return AgentResult(
                agent_name=self.name,
                agent_profile=self.profile_name,
                query=query,
                status=AgentStatus.FAILED,
                error=str(e),
                execution_time=execution_time,
            )

    def _select_best_result(self, results: list[dict], query: str) -> Optional[dict]:
        """Select the best result from search results based on agent profile."""
        if not results:
            return None

        for result in results:
            base_score = result.get("relevance_score", 0.5)
            url = result.get("url", "").lower()
            for source in self.preferred_sources:
                if source in url:
                    base_score += 0.1
                    break
            result["relevance_score"] = min(base_score, 1.0)

        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return results[0]

    def __repr__(self) -> str:
        return f"SearchAgent(name='{self.name}', profile='{self.profile_name}', status={self.status.value})"
