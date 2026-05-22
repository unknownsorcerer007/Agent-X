"""Agent Swarm - Parallel web search agent system integrated into Agent-OS.

Provides:
- Query routing (3-tier: rule-based → provider fallback → conservative)
- Parallel search agents (news_hound, deep_researcher, price_checker, tech_scanner, generalist)
- Multiple search backends (HTTP/Bing/DDG, Agent-OS browser)
- Structured output with quality scoring and deduplication
"""

from src.agent_swarm.router import QueryRouter, QueryClassification, QueryCategory
from src.agent_swarm.agents import SearchAgent, AgentResult, AgentStatus, AgentPool
from src.agent_swarm.search import (
    SearchBackend,
    HTTPSearchBackend,
    AgentOSBackend,
    ContentExtractor,
)
from src.agent_swarm.output import OutputFormatter, ResultAggregator, QualityScorer, Deduplicator
from src.agent_swarm.config import SwarmConfig

__all__ = [
    "QueryRouter",
    "QueryClassification",
    "QueryCategory",
    "SearchAgent",
    "AgentResult",
    "AgentStatus",
    "AgentPool",
    "SearchBackend",
    "HTTPSearchBackend",
    "AgentOSBackend",
    "ContentExtractor",
    "OutputFormatter",
    "ResultAggregator",
    "QualityScorer",
    "Deduplicator",
    "SwarmConfig",
]
