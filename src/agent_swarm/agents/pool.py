"""Agent Pool Manager - orchestrates parallel search across multiple agents."""

import asyncio
import time
import logging
from typing import Optional, Callable

from src.agent_swarm.agents.base import SearchAgent, AgentResult, AgentStatus
from src.agent_swarm.agents.profiles import SEARCH_PROFILES, get_profile

logger = logging.getLogger(__name__)


class AgentPool:
    """Manages a pool of search agents for parallel web search.

    Inspired by MiroFish's concurrent.futures pattern for parallel execution.
    Each agent searches independently, results are aggregated at the end.

    Supports up to 50 concurrent agents with semaphore-based concurrency limiting,
    dynamic agent spawning for swarm mode, error recovery, and progress tracking.
    """

    # Maximum number of agents the pool can scale to
    MAX_SWARM_SIZE = 50

    def __init__(self, max_workers: int = 5, search_timeout: float = 30.0, search_backend=None):
        self.max_workers = min(max_workers, self.MAX_SWARM_SIZE)
        self.search_timeout = search_timeout
        self._agents: dict[str, SearchAgent] = {}
        self._initialize_agents()

        # Semaphore-based concurrency limiter to prevent resource exhaustion
        self._semaphore = asyncio.Semaphore(self.max_workers)

        # Shared search backend for connection pooling (avoids creating new backends per agent)
        self._shared_search_backend = search_backend

        # Track temporary (cloned) agents spawned for swarm mode
        self._temp_agents: dict[str, SearchAgent] = {}

        # Track currently busy agents for swarm status reporting
        self._busy_agents: set[str] = set()

        # Last search results summary for swarm status
        self._last_search_summary: Optional[dict] = None

        # Track clone counter per profile for unique naming
        self._clone_counters: dict[str, int] = {}

    def _initialize_agents(self):
        """Create SearchAgent instances from all defined profiles."""
        for key, profile in SEARCH_PROFILES.items():
            self._agents[key] = SearchAgent(
                name=profile.name,
                profile_name=profile.key,
                expertise=profile.expertise,
                preferred_sources=profile.preferred_sources,
                search_depth=profile.search_depth,
                query_style=profile.query_style,
            )

    def get_agent(self, profile_key: str) -> Optional[SearchAgent]:
        """Get a search agent by profile key."""
        return self._agents.get(profile_key)

    def _spawn_temp_agents(self, base_profile_key: str, count: int) -> list[SearchAgent]:
        """Spawn temporary clone agents based on a profile.

        Creates N SearchAgent clones with modified names (e.g., "generalist-2",
        "news_hound-2"). These clones are tracked in _temp_agents but NOT added
        to self._agents — they are cleaned up after the search completes.

        Args:
            base_profile_key: The profile key to clone from.
            count: Number of clone agents to create.

        Returns:
            List of newly created SearchAgent instances.
        """
        profile = get_profile(base_profile_key)
        if profile is None:
            logger.warning(f"Cannot spawn temp agents: unknown profile '{base_profile_key}'")
            return []

        # Initialize clone counter for this profile if needed
        if base_profile_key not in self._clone_counters:
            self._clone_counters[base_profile_key] = 0

        clones = []
        for i in range(count):
            self._clone_counters[base_profile_key] += 1
            clone_num = self._clone_counters[base_profile_key]
            clone_key = f"{base_profile_key}-{clone_num}"
            clone_name = f"{profile.name}-{clone_num}"

            clone = SearchAgent(
                name=clone_name,
                profile_name=base_profile_key,  # Keep base profile for routing logic
                expertise=profile.expertise,
                preferred_sources=list(profile.preferred_sources),  # Copy to avoid mutation
                search_depth=profile.search_depth,
                query_style=profile.query_style,
            )

            self._temp_agents[clone_key] = clone
            clones.append(clone)
            logger.debug(f"Spawned temp agent: {clone_name} (clone #{clone_num} of {base_profile_key})")

        logger.info(f"Spawned {count} temp agents from profile '{base_profile_key}'")
        return clones

    def _cleanup_temp_agents(self, temp_agent_keys: list[str]):
        """Remove temporary agents after search completes.

        Args:
            temp_agent_keys: Keys of temporary agents to remove.
        """
        for key in temp_agent_keys:
            agent = self._temp_agents.pop(key, None)
            if agent:
                agent.status = AgentStatus.IDLE
                agent._last_result = None
        logger.debug(f"Cleaned up {len(temp_agent_keys)} temp agents")

    async def _retry_with_fallback(
        self,
        query: str,
        agent_profiles: list[str],
        search_backend,
        max_results: int,
        failed_results: list[AgentResult],
        total_agents: int,
        _progress_callback: Optional[Callable[[str], None]] = None,
    ) -> list[AgentResult]:
        """Retry search with different agent profiles when >50% of agents fail.

        Automatically selects alternative profiles and re-executes the search,
        avoiding the profiles that already failed.

        Args:
            query: The search query.
            agent_profiles: Original agent profile keys used.
            search_backend: Search backend instance.
            max_results: Maximum results to return.
            failed_results: List of AgentResult failures from the first attempt.
            total_agents: Total number of agents in the original search.
            _progress_callback: Optional progress callback.

        Returns:
            List of AgentResult from the retry attempt, or empty list if retry fails.
        """
        # Determine which profiles failed
        failed_profiles = set()
        for r in failed_results:
            if r.status == AgentStatus.FAILED:
                failed_profiles.add(r.agent_profile)

        logger.info(
            f"Retry triggered: {len(failed_results)}/{total_agents} agents failed. "
            f"Failed profiles: {failed_profiles}"
        )

        if _progress_callback:
            _progress_callback(f"Retrying with fallback profiles (avoiding {len(failed_profiles)} failed)")

        # Select fallback profiles: prefer profiles not yet used, then generalist as last resort
        all_keys = set(SEARCH_PROFILES.keys())
        unused_keys = all_keys - set(agent_profiles) - failed_profiles
        fallback_profiles = list(unused_keys)

        if not fallback_profiles:
            # All profiles exhausted; try generalist as last resort
            if "generalist" not in failed_profiles:
                fallback_profiles = ["generalist"]
            else:
                logger.warning("All agent profiles failed, no fallback available")
                return []

        # Limit fallback to the number of failed agents
        fallback_profiles = fallback_profiles[:len(failed_results)]

        logger.info(f"Retrying with fallback profiles: {fallback_profiles}")

        retry_results = await self.search_parallel(
            query=query,
            agent_profiles=fallback_profiles,
            search_backend=search_backend,
            max_results=max_results,
            _progress_callback=_progress_callback,
        )

        return retry_results

    async def search_parallel(
        self,
        query: str,
        agent_profiles: list[str],
        search_backend,
        max_results: int = 10,
        _progress_callback: Optional[Callable[[str], None]] = None,
    ) -> list[AgentResult]:
        """Execute parallel search across multiple agents.

        Uses a semaphore to limit concurrent searches to max_workers, preventing
        resource exhaustion when many agents are active. Supports progress tracking
        via an optional callback and automatic error recovery.

        Args:
            query: The search query string.
            agent_profiles: List of agent profile keys to use.
            search_backend: Search backend instance (uses shared backend if None).
            max_results: Maximum number of results to return.
            _progress_callback: Optional callback invoked with progress updates
                (e.g., "3/5 agents completed").

        Returns:
            List of AgentResult from successful agent searches.
        """
        # Use shared backend if no backend provided (connection pooling)
        backend = search_backend or self._shared_search_backend

        start_time = time.time()

        agents = []
        for key in agent_profiles:
            agent = self._agents.get(key)
            if agent:
                agents.append(agent)
            else:
                logger.warning(f"Unknown agent profile: {key}, skipping")

        if not agents:
            agents = [self._agents["generalist"]]
            logger.info("No valid agent profiles, using generalist")

        logger.info(f"Starting parallel search with {len(agents)} agents: {[a.name for a in agents]}")

        # Track busy agents
        for agent in agents:
            self._busy_agents.add(agent.name)

        total_agents = len(agents)
        completed_count = 0

        async def _run_with_semaphore(agent: SearchAgent) -> AgentResult:
            """Run a single agent search, respecting the concurrency semaphore."""
            nonlocal completed_count
            async with self._semaphore:
                result = await self._search_with_timeout(agent, query, backend)
                completed_count += 1
                # Update busy tracking
                self._busy_agents.discard(agent.name)
                # Report progress
                if _progress_callback:
                    _progress_callback(f"{completed_count}/{total_agents} agents completed")
                return result

        tasks = []
        for agent in agents:
            task = asyncio.create_task(_run_with_semaphore(agent))
            tasks.append(task)

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.search_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Parallel search timed out after {self.search_timeout}s")
            results = []
            # Clear all busy agents on timeout
            for agent in agents:
                self._busy_agents.discard(agent.name)

        agent_results = []
        failed_results = []
        for result in results:
            if isinstance(result, AgentResult):
                agent_results.append(result)
                if result.status == AgentStatus.FAILED:
                    failed_results.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Agent search error: {result}")

        # Error recovery: if >50% of agents failed, retry with fallback profiles
        if total_agents > 0 and len(failed_results) > total_agents // 2:
            logger.warning(
                f"High failure rate: {len(failed_results)}/{total_agents} agents failed. "
                f"Triggering fallback retry..."
            )
            retry_results = await self._retry_with_fallback(
                query=query,
                agent_profiles=agent_profiles,
                search_backend=backend,
                max_results=max_results,
                failed_results=failed_results,
                total_agents=total_agents,
                _progress_callback=_progress_callback,
            )
            # Merge retry results, replacing failed ones
            successful_results = [r for r in agent_results if r.status != AgentStatus.FAILED]
            agent_results = successful_results + retry_results

        total_time = time.time() - start_time
        logger.info(
            f"Parallel search completed: {len(agent_results)} results in {total_time:.2f}s "
            f"using {len(agents)} agents"
        )

        # Store last search summary for swarm status
        self._last_search_summary = {
            "query": query,
            "total_agents": total_agents,
            "successful_results": len([r for r in agent_results if r.status != AgentStatus.FAILED]),
            "failed_results": len(failed_results),
            "execution_time": total_time,
            "timestamp": time.time(),
        }

        return agent_results

    async def _search_with_timeout(
        self, agent: SearchAgent, query: str, search_backend
    ) -> AgentResult:
        """Execute a single agent search with timeout."""
        try:
            result = await asyncio.wait_for(
                agent.search(query, search_backend),
                timeout=self.search_timeout,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Agent '{agent.name}' timed out")
            return AgentResult(
                agent_name=agent.name,
                agent_profile=agent.profile_name,
                query=query,
                status=AgentStatus.FAILED,
                error="timeout",
            )
        except Exception as e:
            logger.error(f"Agent '{agent.name}' error: {e}")
            return AgentResult(
                agent_name=agent.name,
                agent_profile=agent.profile_name,
                query=query,
                status=AgentStatus.FAILED,
                error=str(e),
            )

    def search_parallel_sync(
        self,
        query: str,
        agent_profiles: list[str],
        search_backend,
        max_results: int = 10,
    ) -> list[AgentResult]:
        """Synchronous wrapper for parallel search.

        Properly handles being called from within an already-running event loop
        by scheduling the coroutine as a task on the existing loop rather than
        spawning a separate thread with a new event loop.
        """
        coro = self.search_parallel(query, agent_profiles, search_backend, max_results)
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # We're inside a running event loop — schedule as a task
                # and use a Future to bridge the result back synchronously
                future = asyncio.ensure_future(coro)
                # Run the event loop until the future completes
                # This works when called from within an async context that can yield
                try:
                    return future.result(timeout=self.search_timeout + 5)
                except asyncio.TimeoutError:
                    logger.warning("Synchronous wrapper timed out waiting for async result")
                    return []
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            # No running loop at all — create one
            return asyncio.run(coro)

    def get_status(self) -> dict:
        """Get current status of all agents in the pool."""
        return {
            "max_workers": self.max_workers,
            "agents": {
                key: {
                    "name": agent.name,
                    "profile": agent.profile_name,
                    "status": agent.status.value,
                    "expertise": agent.expertise,
                }
                for key, agent in self._agents.items()
            },
        }

    def get_swarm_status(self) -> dict:
        """Get detailed info about the current swarm state.

        Returns a dict with:
        - max_workers: Configured max concurrent workers
        - total_registered_agents: Number of permanent agents
        - total_temp_agents: Number of currently active temp agents
        - available_agents: Agents currently in IDLE state
        - busy_agents: Agents currently searching/extracting
        - semaphore_value: Current semaphore availability
        - last_search_summary: Summary of the most recent search (if any)
        """
        all_agents = {**self._agents, **self._temp_agents}

        available = []
        busy = []
        for key, agent in all_agents.items():
            info = {
                "key": key,
                "name": agent.name,
                "profile": agent.profile_name,
                "status": agent.status.value,
                "expertise": agent.expertise,
            }
            if agent.status in (AgentStatus.IDLE, AgentStatus.COMPLETED):
                available.append(info)
            else:
                busy.append(info)

        # Semaphore value indicates how many more concurrent searches can start
        semaphore_val = self._semaphore._value if hasattr(self._semaphore, '_value') else "unknown"

        return {
            "max_workers": self.max_workers,
            "total_registered_agents": len(self._agents),
            "total_temp_agents": len(self._temp_agents),
            "available_agents": available,
            "available_count": len(available),
            "busy_agents": busy,
            "busy_count": len(busy),
            "busy_agent_names": list(self._busy_agents),
            "semaphore_available": semaphore_val,
            "last_search_summary": self._last_search_summary,
            "shared_backend_enabled": self._shared_search_backend is not None,
        }

    def reset_agents(self):
        """Reset all agent statuses to IDLE."""
        for agent in self._agents.values():
            agent.status = AgentStatus.IDLE
            agent._last_result = None
        for agent in self._temp_agents.values():
            agent.status = AgentStatus.IDLE
            agent._last_result = None
        self._busy_agents.clear()

    def close(self):
        """Clean up pool resources."""
        self.reset_agents()
        self._temp_agents.clear()
        self._last_search_summary = None
        logger.debug("AgentPool closed")
