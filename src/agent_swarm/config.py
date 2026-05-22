"""Agent Swarm configuration - integrated into Agent-OS config system.

Uses the user's configured provider as the brain — no separate LLM needed.
Auto-detects user's provider from environment variables.
All configuration via environment variables with safe defaults.
"""

import os
import json
import logging
from typing import Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _safe_json_loads(value: str, default=None):
    """Safely parse JSON from environment variables with error handling."""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Failed to parse JSON from env var value: {value[:50]}...")
        return default if default is not None else []


def _detect_user_provider() -> tuple:
    """Auto-detect which provider the user has configured from env vars.

    Returns (api_key, base_url, model, provider_name) tuple.
    Checks common provider env vars in order of preference.
    If no provider found, returns empty strings (Tier 2 disabled).
    """
    # Check explicit SWARM_PROVIDER_* vars first
    swarm_key = os.getenv("SWARM_PROVIDER_API_KEY", "").strip()
    swarm_url = os.getenv("SWARM_PROVIDER_BASE_URL", "").strip()
    swarm_model = os.getenv("SWARM_PROVIDER_MODEL", "").strip()
    if swarm_key:
        return swarm_key, swarm_url, swarm_model, "custom"

    # Check common provider env vars
    provider_checks = [
        ("OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4o-mini", "openai"),
        ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1", "claude-3-5-haiku-20241022", "anthropic"),
        ("GOOGLE_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash", "google"),
        ("XAI_API_KEY", "https://api.x.ai/v1", "grok-2-mini", "xai"),
        ("MISTRAL_API_KEY", "https://api.mistral.ai/v1", "mistral-small-latest", "mistral"),
        ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1", "deepseek-chat", "deepseek"),
        ("GROQ_API_KEY", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "groq"),
        ("TOGETHER_API_KEY", "https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "together"),
    ]

    for env_var, base_url, model, provider_name in provider_checks:
        key = os.getenv(env_var, "").strip()
        if key:
            logger.info(f"Auto-detected user provider: {provider_name} (model: {model})")
            return key, base_url, model, provider_name

    # No provider configured — Tier 2 will be disabled (Tier 1 + Tier 3 still work)
    logger.info("No user provider detected — Tier 2 classification disabled. Tier 1 + Tier 3 will handle routing.")
    return "", "", "", ""


class RouterConfig(BaseModel):
    """Query router configuration.

    User's provider = brain. No separate LLM needed.
    If no provider configured, Tier 2 is simply skipped.
    """
    confidence_threshold: float = Field(default=0.7, description="Min confidence for rule-based routing")
    enable_provider_fallback: bool = Field(default=True, description="Enable Tier 2 user provider fallback")
    provider_api_key: Optional[str] = Field(default="", description="User's provider API key (auto-detected from env)")
    provider_base_url: str = Field(default="", description="User's provider API base URL (auto-detected from env)")
    provider_model: str = Field(default="", description="User's provider model name (auto-detected from env)")
    provider_name: Optional[str] = Field(default="", description="Provider name (openai, anthropic, google, etc.)")
    provider_max_tokens: int = Field(default=150, description="Max tokens for provider classification")
    provider_timeout: float = Field(default=8.0, description="Provider request timeout in seconds")


class SwarmAgentConfig(BaseModel):
    """Search agent configuration."""
    max_workers: int = Field(default=50, description="Max parallel agents")
    default_agents: list[str] = Field(default=["generalist"], description="Default agent profiles")
    search_timeout: float = Field(default=30.0, description="Search timeout per agent in seconds")
    max_retries: int = Field(default=2, description="Max retries for failed searches")
    max_total_agents: int = Field(default=50, description="Maximum total agents that can be spawned")


class SearchBackendConfig(BaseModel):
    """Search backend configuration."""
    agent_os_url: Optional[str] = Field(default=None, description="Agent-OS server URL")
    agent_os_api_key: Optional[str] = Field(default=None, description="Agent-OS API key")
    use_browser: bool = Field(default=False, description="Use Agent-OS browser backend")
    chrome_impersonate: str = Field(default="chrome146", description="curl_cffi impersonation target")
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        description="User-Agent string"
    )


class SwarmOutputConfig(BaseModel):
    """Output configuration."""
    format: str = Field(default="json", description="Output format: json, markdown, or both")
    max_results: int = Field(default=10, description="Max results per query")
    deduplicate: bool = Field(default=True, description="Deduplicate results")
    min_relevance_score: float = Field(default=0.3, description="Min relevance score to include")


class SwarmConfig(BaseModel):
    """Main Agent Swarm configuration."""
    enabled: bool = Field(default=True, description="Enable/disable agent swarm")
    router: RouterConfig = Field(default_factory=RouterConfig)
    agents: SwarmAgentConfig = Field(default_factory=SwarmAgentConfig)
    search: SearchBackendConfig = Field(default_factory=SearchBackendConfig)
    output: SwarmOutputConfig = Field(default_factory=SwarmOutputConfig)

    @classmethod
    def from_env(cls) -> "SwarmConfig":
        """Load configuration from environment variables.

        Auto-detects user's provider — no separate LLM service needed.
        If no provider configured, Tier 2 is disabled (Tier 1 + Tier 3 still work).
        """
        # Auto-detect user's provider from env vars
        api_key, base_url, model, provider = _detect_user_provider()

        # Allow explicit overrides
        router_conf = RouterConfig(
            confidence_threshold=float(os.getenv("SWARM_ROUTER_THRESHOLD", "0.7")),
            enable_provider_fallback=os.getenv("SWARM_PROVIDER_ENABLED", "true").lower() == "true",
            provider_api_key=api_key,
            provider_base_url=base_url,
            provider_model=model,
            provider_name=provider,
        )
        agent_conf = SwarmAgentConfig(
            max_workers=int(os.getenv("SWARM_MAX_WORKERS", "50")),
            default_agents=_safe_json_loads(os.getenv("SWARM_DEFAULT_AGENTS", '["generalist"]'), ["generalist"]),
        )
        search_conf = SearchBackendConfig(
            agent_os_url=os.getenv("SWARM_AGENT_OS_URL"),
            agent_os_api_key=os.getenv("SWARM_AGENT_OS_API_KEY"),
            use_browser=os.getenv("SWARM_USE_BROWSER", "false").lower() == "true",
        )
        output_conf = SwarmOutputConfig(
            format=os.getenv("SWARM_OUTPUT_FORMAT", "json"),
            max_results=int(os.getenv("SWARM_MAX_RESULTS", "10")),
        )
        return cls(
            enabled=os.getenv("SWARM_ENABLED", "true").lower() == "true",
            router=router_conf,
            agents=agent_conf,
            search=search_conf,
            output=output_conf,
        )


# Global config instance
swarm_config = SwarmConfig.from_env()


def get_config() -> SwarmConfig:
    """Get the global swarm configuration instance."""
    return swarm_config


def reload_config() -> SwarmConfig:
    """Reload configuration from environment variables."""
    global swarm_config
    swarm_config = SwarmConfig.from_env()
    logger.info("Swarm config reloaded from environment variables")
    return swarm_config
