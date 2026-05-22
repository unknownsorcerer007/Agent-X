"""Output formatting - converts search results to structured formats."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field, asdict

from src.agent_swarm.agents.base import AgentResult

logger = logging.getLogger(__name__)


@dataclass
class SearchOutput:
    """Structured output from a search operation."""
    query: str
    category: str
    tier_used: str
    agents_used: list[str]
    results: list[dict]
    total_results: int
    confidence: float
    execution_time: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sources: list[str] = field(default_factory=list)
    summary: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(asdict(self), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Convert to Markdown format."""
        lines = [
            f"# Search Results: {self.query}",
            "",
            f"**Category:** {self.category} | **Confidence:** {self.confidence:.2f} | **Tier:** {self.tier_used}",
            f"**Agents:** {', '.join(self.agents_used)} | **Results:** {self.total_results}",
            f"**Time:** {self.execution_time:.2f}s | **Timestamp:** {self.timestamp}",
            "",
        ]
        if self.summary:
            lines.extend(["## Summary", "", f"{self.summary}", ""])
        lines.append("## Results")
        lines.append("")
        for i, result in enumerate(self.results, 1):
            title = result.get("title", "No Title")
            url = result.get("url", "")
            snippet = result.get("snippet", "")
            agent = result.get("agent_name", "")
            score = result.get("relevance_score", 0)
            lines.append(f"### {i}. {title}")
            lines.append("")
            lines.append(f"- **URL:** {url}")
            lines.append(f"- **Agent:** {agent}")
            lines.append(f"- **Relevance:** {score:.2f}")
            if snippet:
                lines.append(f"- **Snippet:** {snippet}")
            lines.append("")
        if self.sources:
            lines.append("## Sources")
            lines.append("")
            for source in self.sources:
                lines.append(f"- {source}")
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)


class OutputFormatter:
    """Formats search results into structured output."""

    def __init__(
        self,
        format: str = "json",
        max_results: int = 10,
        min_relevance_score: float = 0.3,
    ):
        self.format = format
        self.max_results = max_results
        self.min_relevance_score = min_relevance_score

    def format_results(
        self,
        query: str,
        category: str,
        tier_used: str,
        agent_results: list[AgentResult],
        execution_time: float,
        confidence: float = 0.5,
        summary: Optional[str] = None,
    ) -> SearchOutput:
        """Format agent results into structured output."""
        results = []
        agents_used = set()
        sources = set()

        for ar in agent_results:
            if ar.status.value != "completed":
                continue
            agents_used.add(ar.agent_name)
            result_dict = {
                "agent_name": ar.agent_name,
                "agent_profile": ar.agent_profile,
                "query": ar.query,
                "title": ar.title,
                "url": ar.url,
                "snippet": ar.snippet,
                "content": ar.content[:1000] if ar.content else "",
                "relevance_score": ar.relevance_score,
                "source_type": ar.source_type,
                "execution_time": ar.execution_time,
            }
            if ar.relevance_score >= self.min_relevance_score:
                results.append(result_dict)
                if ar.url:
                    sources.add(ar.url)

        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        results = results[:self.max_results]

        return SearchOutput(
            query=query,
            category=category,
            tier_used=tier_used,
            agents_used=list(agents_used),
            results=results,
            total_results=len(results),
            confidence=confidence,
            execution_time=execution_time,
            timestamp=datetime.now(timezone.utc).isoformat(),
            sources=list(sources),
            summary=summary,
        )
