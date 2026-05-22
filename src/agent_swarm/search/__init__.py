"""Search module - search backends and content extraction."""

from src.agent_swarm.search.base import SearchBackend, SearchResultItem, SearchProvider, SearchRequest, combine_results
from src.agent_swarm.search.http_backend import HTTPSearchBackend
from src.agent_swarm.search.agent_os_backend import AgentOSBackend
from src.agent_swarm.search.extractors import ContentExtractor, ExtractedContent

__all__ = [
    "SearchBackend",
    "SearchResultItem",
    "SearchProvider",
    "SearchRequest",
    "combine_results",
    "HTTPSearchBackend",
    "AgentOSBackend",
    "ContentExtractor",
    "ExtractedContent",
]
