"""Tier 2: User's Provider as Brain — Provider-based query router.

Uses the SAME provider the user has configured (OpenAI, Anthropic, Google, etc.)
for query classification. No separate LLM needed — the user's provider IS the brain.

Now powered by UniversalProvider from src.core.llm_provider for:
- Unified LLM access across all providers
- Token saving (compression, caching, smart truncation)
- Automatic fallback chain
- Streaming support

Production features:
- LRU cache for repeated queries (512 entries)
- Retry with exponential backoff (3 attempts)
- Prompt injection protection
- Graceful degradation when no provider configured
- Thread-safe client creation
- Only activates when user has explicitly configured a provider
- Uses UniversalProvider for token-saving LLM calls
"""

import asyncio
import json
import logging
import hashlib
import time
import threading
from typing import TYPE_CHECKING, Optional
from collections import OrderedDict

if TYPE_CHECKING:
    from src.agent_swarm.router.rule_based import QueryClassification

logger = logging.getLogger(__name__)


class LRUCache:
    """Thread-safe LRU cache for query classifications."""

    def __init__(self, maxsize: int = 512):
        self._cache: OrderedDict[str, tuple] = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self.hits += 1
                return self._cache[key]
            self.misses += 1
            return None

    def put(self, key: str, value: tuple):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def clear(self):
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)


def _sanitize_query(query: str) -> str:
    """Sanitize user query to prevent prompt injection in provider calls.

    Strips common injection patterns while preserving the query meaning.
    This is critical because user queries are embedded in the classification
    prompt — a malicious query could try to override the system instructions.
    """
    sanitized = query[:500]  # Truncate extremely long queries
    injection_patterns = [
        "ignore previous instructions",
        "ignore all previous",
        "disregard all",
        "system:",
        "assistant:",
        "you are now",
        "new instructions",
        "override",
        "jailbreak",
    ]
    lower = sanitized.lower()
    for pattern in injection_patterns:
        if pattern in lower:
            sanitized = sanitized[:100] + " [query sanitized for injection prevention]"
            break
    return sanitized


# ─── Provider Detection ────────────────────────────────────────
# Map provider names to their OpenAI-compatible base URLs and default models
# Kept for backward compatibility; primary detection now uses UniversalProvider

PROVIDER_CONFIGS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-haiku-20241022",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.0-flash",
        "env_key": "GOOGLE_API_KEY",
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "default_model": "grok-2-mini",
        "env_key": "XAI_API_KEY",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest",
        "env_key": "MISTRAL_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "env_key": "TOGETHER_API_KEY",
    },
}


def _auto_detect_provider() -> Optional[dict]:
    """Auto-detect which provider the user has configured.

    Delegates to UniversalProvider's auto_detect_provider for expanded
    provider support (Ollama, Azure, Bedrock, etc.). Falls back to
    local PROVIDER_CONFIGS if UniversalProvider import fails.
    """
    # Try UniversalProvider's expanded detection first
    try:
        from src.core.llm_provider import auto_detect_provider as universal_detect
        detected = universal_detect()
        if detected:
            return {
                "provider": detected.get("provider", "custom"),
                "api_key": detected.get("api_key", ""),
                "base_url": detected.get("base_url", ""),
                "model": detected.get("model", ""),
                "default_model": detected.get("model", ""),
            }
    except ImportError:
        logger.debug("UniversalProvider not available, using local provider detection")

    # Fallback to local detection
    for provider_name, config in PROVIDER_CONFIGS.items():
        api_key = _get_env_key(config["env_key"])
        if api_key:
            logger.info(f"Auto-detected user provider: {provider_name} (model: {config['default_model']})")
            return {
                "provider": provider_name,
                "api_key": api_key,
                "base_url": config["base_url"],
                "model": config["default_model"],
                "default_model": config["default_model"],
            }
    return None


def _get_env_key(env_var: str) -> Optional[str]:
    """Safely get API key from environment variable."""
    import os
    key = os.getenv(env_var, "").strip()
    return key if key else None


class ProviderRouter:
    """Tier 2: Uses the user's configured provider as the brain for ambiguous query classification.

    IMPORTANT: This is NOT a separate LLM. It uses the SAME provider the user
    has already configured. If the user selected OpenAI, OpenAI is the brain.
    If they selected Anthropic, Claude is the brain. No extra LLM needed.

    Now delegates LLM calls to UniversalProvider for token-saving benefits:
    - Prompt compression
    - Response caching (exact + similarity matching)
    - Smart truncation
    - Fallback chain
    - Token budget tracking

    The router only activates when:
    1. User has an API key configured (via env vars or explicit config), OR
    2. User has explicitly set a provider via SWARM_PROVIDER_* env vars

    If no provider is available, Tier 2 is gracefully skipped and the system
    falls through to Tier 3 (conservative web search fallback).

    Production features:
    - LRU cache (512 entries) for repeated queries
    - Retry with exponential backoff (3 attempts)
    - Prompt injection protection
    - Thread-safe client creation
    - Auto-detection of user's configured provider from env vars
    - UniversalProvider integration for token saving
    """

    # Classification categories for the swarm router
    CLASSIFICATION_CATEGORIES = [
        "needs_web",
        "needs_knowledge",
        "needs_calculation",
        "needs_code",
        "ambiguous",
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        max_tokens: int = 150,
        timeout: float = 8.0,
        max_retries: int = 3,
        cache_size: int = 512,
    ):
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = None
        self._client_lock = threading.Lock()
        self.provider = provider

        # Determine provider configuration
        self.base_url = base_url
        self.model = model

        if not self.api_key or not self.base_url:
            # Try explicit env vars first (SWARM_PROVIDER_*)
            import os
            swarm_key = os.getenv("SWARM_PROVIDER_API_KEY", "").strip()
            swarm_url = os.getenv("SWARM_PROVIDER_BASE_URL", "").strip()
            swarm_model = os.getenv("SWARM_PROVIDER_MODEL", "").strip()

            if swarm_key:
                self.api_key = swarm_key
                self.base_url = swarm_url or self.base_url
                self.model = swarm_model or self.model
                logger.info(f"Using explicitly configured SWARM_PROVIDER (url: {self.base_url})")
            else:
                # Auto-detect from user's configured provider
                detected = _auto_detect_provider()
                if detected:
                    if not self.api_key:
                        self.api_key = detected["api_key"]
                    if not self.base_url:
                        self.base_url = detected["base_url"]
                    if not self.model:
                        self.model = detected["model"]
                    if not self.provider:
                        self.provider = detected["provider"]
                    logger.info(
                        f"Auto-detected provider: {detected['provider']} "
                        f"(model: {detected.get('default_model', detected.get('model', 'unknown'))})"
                    )

        # If we still don't have credentials, Tier 2 will be unavailable
        # (this is fine — Tier 1 + Tier 3 handle everything)
        if not self.api_key:
            logger.info(
                "No provider configured — Tier 2 classification disabled. "
                "Tier 1 (rule-based) + Tier 3 (conservative) will handle all routing."
            )

        # Initialize UniversalProvider for token-saving LLM calls
        self._universal_provider = None
        try:
            from src.core.llm_provider import UniversalProvider, TokenBudget
            self._universal_provider = UniversalProvider(
                provider=self.provider,
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model,
                max_retries=max_retries,
                timeout=timeout,
                budget=TokenBudget(max_total_tokens=500_000),
                cache_size=cache_size,
                compression_aggression=0.3,  # Light compression for classification prompts
            )
            if self._universal_provider.is_available:
                logger.info("ProviderRouter using UniversalProvider for token-saving classification")
        except ImportError:
            logger.debug("UniversalProvider not available, using direct OpenAI client")

        # Initialize local cache (still used for sync classify method)
        self._cache = LRUCache(maxsize=cache_size)

        # Classification metrics
        self._total_calls = 0
        self._cache_hits = 0
        self._failures = 0

    def is_available(self) -> bool:
        """Check if user's provider is available for Tier 2 classification.

        Available only when user has explicitly configured an API key.
        We never auto-install or require a separate provider service.
        """
        # Check UniversalProvider first
        if self._universal_provider and self._universal_provider.is_available:
            return True

        # Fall back to direct client check
        if not self.api_key or not self.api_key.strip():
            return False
        if not self.base_url or not self.base_url.strip():
            return False
        return True

    def _get_client(self):
        """Get or create OpenAI-compatible client (thread-safe).

        Uses the openai library which is compatible with most providers
        (OpenAI, Anthropic via proxy, Google, Groq, Together, etc.)

        This is now a fallback — UniversalProvider is preferred.
        """
        if self._client is not None:
            return self._client

        with self._client_lock:
            # Double-check after acquiring lock
            if self._client is not None:
                return self._client
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout,
                )
                return self._client
            except ImportError:
                logger.warning("openai package not installed — Tier 2 provider classification unavailable")
                return None
            except Exception as e:
                logger.warning(f"Failed to create provider client: {e}")
                return None

    def classify(self, query: str) -> Optional["QueryClassification"]:  # type: ignore[name-defined]
        """Classify a query using the user's configured provider.

        With caching, retries, and injection protection.
        Returns QueryClassification or None if provider is unavailable.

        Tries UniversalProvider first (async via event loop), then
        falls back to direct OpenAI client for backward compatibility.
        """
        if not self.is_available():
            return None

        # Check cache first
        cache_key = hashlib.sha256(query.encode()).hexdigest()[:16]
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            logger.debug(f"Provider router cache hit for query: '{query[:40]}...'")
            return cached[0]

        # Sanitize query for injection protection
        safe_query = _sanitize_query(query)

        self._total_calls += 1

        # Try UniversalProvider (async) first
        if self._universal_provider and self._universal_provider.is_available:
            result = self._classify_via_universal(safe_query)
            if result is not None:
                self._cache.put(cache_key, (result,))
                return result

        # Fallback to direct OpenAI client
        client = self._get_client()
        if client is None:
            return None

        # Retry with exponential backoff
        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = self._call_provider(client, safe_query)
                if result is not None:
                    # Cache the result
                    self._cache.put(cache_key, (result,))
                    return result
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s
                    logger.debug(f"Provider retry {attempt + 1}/{self.max_retries} after error: {e}")
                    import time as _time
                    _time.sleep(wait_time)  # classify() is sync — use blocking sleep

        self._failures += 1
        logger.warning(f"Provider classification failed after {self.max_retries} retries: {last_error}")
        return None

    def _classify_via_universal(self, query: str) -> Optional["QueryClassification"]:  # type: ignore[name-defined]
        """Classify using UniversalProvider with token saving.

        Runs the async UniversalProvider.classify() in a sync context
        by trying to use the existing event loop or creating a new one.
        """
        from src.agent_swarm.router.rule_based import QueryCategory, QueryClassification

        try:
            # Try to run in existing event loop
            loop = asyncio.get_running_loop()
            # We're inside an async context — schedule the coroutine
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self._universal_provider.classify(
                        query, self.CLASSIFICATION_CATEGORIES
                    )
                )
                result = future.result(timeout=self.timeout + 5)
        except RuntimeError:
            # No running event loop — safe to use asyncio.run()
            try:
                result = asyncio.run(
                    self._universal_provider.classify(
                        query, self.CLASSIFICATION_CATEGORIES
                    )
                )
            except Exception as e:
                logger.debug(f"UniversalProvider classify failed: {e}")
                return None
        except Exception as e:
            logger.debug(f"UniversalProvider classify failed: {e}")
            return None

        if result.get("status") != "success":
            logger.debug(f"UniversalProvider returned error: {result.get('error')}")
            return None

        # Convert UniversalProvider result to QueryClassification
        category_str = result.get("category", "ambiguous")
        try:
            category = QueryCategory(category_str)
        except ValueError:
            category = QueryCategory.AMBIGUOUS

        return QueryClassification(
            category=category,
            confidence=float(result.get("confidence", 0.5)),
            reason=result.get("reasoning", "universal_provider_classification"),
            source="provider_router",
        )

    async def async_classify(self, query: str) -> Optional["QueryClassification"]:  # type: ignore[name-defined]
        """Async version of classify — preferred when in async context.

        Uses UniversalProvider directly for optimal token saving.
        Falls back to direct client if UniversalProvider is unavailable.
        """
        if not self.is_available():
            return None

        # Check cache first
        cache_key = hashlib.sha256(query.encode()).hexdigest()[:16]
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            logger.debug(f"Provider router cache hit for query: '{query[:40]}...'")
            return cached[0]

        # Sanitize query
        safe_query = _sanitize_query(query)
        self._total_calls += 1

        # Use UniversalProvider directly (async-native)
        if self._universal_provider and self._universal_provider.is_available:
            from src.agent_swarm.router.rule_based import QueryCategory, QueryClassification

            try:
                result = await self._universal_provider.classify(
                    safe_query, self.CLASSIFICATION_CATEGORIES
                )

                if result.get("status") == "success":
                    category_str = result.get("category", "ambiguous")
                    try:
                        category = QueryCategory(category_str)
                    except ValueError:
                        category = QueryCategory.AMBIGUOUS

                    classification = QueryClassification(
                        category=category,
                        confidence=float(result.get("confidence", 0.5)),
                        reason=result.get("reasoning", "universal_provider_classification"),
                        source="provider_router",
                    )
                    self._cache.put(cache_key, (classification,))
                    return classification
            except Exception as e:
                logger.debug(f"UniversalProvider async classify failed: {e}")

        # Fallback: run sync _call_provider in executor
        client = self._get_client()
        if client is None:
            return None

        loop = asyncio.get_running_loop()
        last_error = None

        for attempt in range(self.max_retries):
            try:
                result = await loop.run_in_executor(
                    None, self._call_provider, client, safe_query
                )
                if result is not None:
                    self._cache.put(cache_key, (result,))
                    return result
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = 0.5 * (2 ** attempt)
                    await asyncio.sleep(wait_time)

        self._failures += 1
        logger.warning(f"Provider classification failed after {self.max_retries} retries: {last_error}")
        return None

    def _call_provider(self, client, query: str) -> Optional["QueryClassification"]:  # type: ignore[name-defined]
        """Make a single provider classification call using user's provider.

        This is the legacy fallback when UniversalProvider is unavailable.
        """
        from src.agent_swarm.router.rule_based import QueryCategory, QueryClassification

        prompt = f"""Classify this search query into exactly one category:

Query: "{query}"

Categories:
- needs_web: Requires current/live web data (news, prices, weather, latest info, stock market, sports scores, social media)
- needs_knowledge: Can be answered from general knowledge (definitions, history, explanations, who invented, what causes)
- needs_calculation: Requires math/computation (arithmetic, unit conversion, formula calculation, percentages)
- needs_code: About writing/generating/debugging code (implement function, create API, write Dockerfile, debug error)

Respond with ONLY a JSON object:
{{"category": "needs_web", "confidence": 0.9, "reason": "requires current data"}}"""

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a query classifier. Classify the user's query into exactly one category. Respond with JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=self.max_tokens,
            temperature=0.1,
        )

        content = response.choices[0].message.content.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```" in content:
            parts = content.split("```")
            if len(parts) >= 2:
                content = parts[1]
                if content.strip().startswith("json"):
                    content = content.strip()[4:].strip()
                else:
                    content = content.strip()

        result = json.loads(content.strip())

        category_str = result.get("category", "ambiguous")
        try:
            category = QueryCategory(category_str)
        except ValueError:
            category = QueryCategory.AMBIGUOUS

        return QueryClassification(
            category=category,
            confidence=float(result.get("confidence", 0.5)),
            reason=result.get("reason", "provider_classification"),
            source="provider_router",
        )

    @property
    def stats(self) -> dict:
        """Return router statistics."""
        base_stats = {
            "total_calls": self._total_calls,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": (self._cache_hits / max(self._total_calls, 1)) * 100,
            "failures": self._failures,
            "cache_size": self._cache.size,
            "model": self.model,
            "base_url": self.base_url,
            "provider": self.provider,
            "available": self.is_available(),
            "using_universal_provider": self._universal_provider is not None and self._universal_provider.is_available,
        }

        # Add UniversalProvider token stats if available
        if self._universal_provider:
            token_stats = self._universal_provider.get_token_usage()
            base_stats["token_budget"] = token_stats.get("budget", {})
            base_stats["token_cache"] = token_stats.get("cache", {})

        return base_stats

    def clear_cache(self):
        """Clear the classification cache."""
        self._cache.clear()
        if self._universal_provider:
            self._universal_provider.cache.clear()

    def reset_client(self):
        """Force recreation of the provider client on next call."""
        with self._client_lock:
            self._client = None
        if self._universal_provider:
            self._universal_provider._reset_clients()


__all__ = ["ProviderRouter"]
