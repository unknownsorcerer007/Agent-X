"""Agents module - parallel search agent system."""

from src.agent_swarm.agents.base import SearchAgent, AgentResult, AgentStatus
from src.agent_swarm.agents.profiles import SearchProfile, SEARCH_PROFILES, get_profile, get_profiles_for_query, get_all_profile_keys
from src.agent_swarm.agents.pool import AgentPool
from src.agent_swarm.agents.strategies import SearchStrategy, SearchPlan, create_search_plan

__all__ = [
    "SearchAgent",
    "AgentResult",
    "AgentStatus",
    "SearchProfile",
    "SEARCH_PROFILES",
    "get_profile",
    "get_profiles_for_query",
    "get_all_profile_keys",
    "AgentPool",
    "SearchStrategy",
    "SearchPlan",
    "create_search_plan",
]
