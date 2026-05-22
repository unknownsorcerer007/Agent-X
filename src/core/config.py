"""
Agent-OS Configuration Management — Production Edition
Handles all settings, with database/Redis/JWT config support.
JWT is used for API authentication (REST + WebSocket), not frontend.
"""
import os
import yaml
import secrets
import hashlib
import hmac
import copy
from pathlib import Path
from typing import Optional, Dict, Any

DEFAULT_CONFIG = {
    "server": {
        "host": os.environ.get("AGENT_OS_HOST", "127.0.0.1"),
        "ws_port": 8000,
        "http_port": 8001,
        "debug_port": 8002,
        "max_connections": 100,
        "cors_origin": "",
        "cors_allowed_origins": [],
        "agent_token": None,
        "allowed_tokens": [],
        "rate_limit_max": 60,
        "rate_limit_window": 60,
        "request_timeout_seconds": 120,
        "max_request_body_kb": 1024,
    },
    "database": {
        "enabled": False,
        "dsn": "postgresql+asyncpg://agent_os:agent_os@localhost:5432/agent_os",
        "pool_size": 20,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 3600,
    },
    "redis": {
        "enabled": False,
        "url": "redis://localhost:6379/0",
        "fallback_on_failure": True,
    },
    "jwt": {
        "secret_key": None,  # Auto-generated if not set
        "algorithm": "HS256",
        "access_token_expire_minutes": 15,
        "refresh_token_expire_days": 30,
        "issuer": "agent-os",
    },
    "browser": {
        "headless": True,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "viewport": {"width": 1920, "height": 1080},
        "max_ram_mb": 500,
        "page_timeout_ms": 30000,
        "proxy": None,
        "device": "desktop_1080",
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "tls_proxy_enabled": False,  # Disabled for browser — Patchright handles TLS natively
        "tls_proxy_port": 8081,
        "proxy_rotation_enabled": True,
        "proxy_rotation_strategy": "weighted",
        "proxy_file": None,
        "proxy_api_url": None,
        "proxy_api_key": None,
    },
    "session": {
        "timeout_minutes": 15,
        "auto_wipe": True,
        "max_concurrent": 3
    },
    "security": {
        "captcha_bypass": True,
        "human_mimicry": True,
        "block_bot_queries": True,
        "session_encryption": True,
        "enable_api_key_auth": True,
        "enable_jwt_auth": True,
        "allow_legacy_token_auth": True,
        "max_login_attempts": 5,
        "lockout_duration_minutes": 15,
    },
    "scanner": {
        "max_requests_per_second": 5,
        "max_concurrent_scans": 2,
        "allowed_domains": []
    },
    "persistent": {
        "enabled": False,
        "max_instances": 5,
        "max_contexts_per_instance": 50,
        "health_check_interval_seconds": 30,
        "idle_timeout_minutes": 60,
        "memory_cap_mb": 4000,
        "auto_restart": True,
    },
    "swarm": {
        "enabled": True,
        "max_workers": 50,
        "router_threshold": 0.7,
        "output_format": "json",
        "max_results": 10,
    },
    "captcha_preempt": {
        "enabled": True,
        "mode": "moderate",  # aggressive, moderate, passive
        "shutdown_timeout_ms": 2000,
        "data_rescue": True,
        "monitor_interval_ms": 500,
        "preflight_check": True,
    },
    "llm_provider": {
        "enabled": True,
        "provider": "auto",  # auto, openai, anthropic, google, xai, mistral, deepseek, groq, together, ollama, azure, bedrock
        "model": None,
        "api_key": None,
        "base_url": None,
        "max_retries": 3,
        "timeout": 30.0,
        "cache_size": 1024,
        "compression_aggression": 0.5,  # 0.0 (none) to 1.0 (maximum)
    },
    "token_budget": {
        "enabled": True,
        "max_total_tokens": 1_000_000,
        "warning_threshold": 0.8,  # Warn at 80% usage
        "auto_truncate": True,
        "save_cache_hits": True,
        "save_compression": True,
    },
    "ai_structured_output": {
        "enabled": True,
        "auto_normalize": True,
        "auto_deduplicate": True,
        "generate_schema": True,
        "cross_page_dedup": True,
        "merge_threshold": 0.85,  # Similarity threshold for near-duplicate merging
        "output_format": "json",  # json, markdown, csv, xml, flat_dict
    },
    "transcription": {
        "model": "tiny",
        "language": "auto"
    },
    "logging": {
        "level": "INFO",
        "json_logs": False,
        "service_name": "agent-os",
    },
}


class Config:
    """Manages Agent-OS configuration with YAML persistence."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path or os.path.expanduser("~/.agent-os/config.yaml"))
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = self._load_or_create()

    def _load_or_create(self) -> Dict[str, Any]:
        """Load existing config or create default."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    loaded = yaml.safe_load(f) or {}
                return self._deep_merge(DEFAULT_CONFIG, loaded)
            except (yaml.YAMLError, yaml.parser.ParserError, yaml.scanner.ScannerError, ValueError):
                # Corrupt YAML — fall back to defaults
                return copy.deepcopy(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge override into base dict. Override values win."""
        result = copy.deepcopy(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def save(self, config: Optional[Dict] = None):
        """Save configuration to disk."""
        with open(self.config_path, "w") as f:
            yaml.dump(config or self.config, f, default_flow_style=False)

    _SENTINEL = object()

    def get(self, dotted_key: str, default=None):
        """Get config value by dotted path (e.g., 'browser.max_ram_mb').

        Uses a sentinel-based approach so that keys whose value is an empty
        dict (or any other falsy value) are correctly distinguished from
        missing keys.
        """
        keys = dotted_key.split(".")
        val = self.config
        for k in keys:
            if isinstance(val, dict):
                if k not in val:
                    return default
                val = val[k]
            else:
                return default
        return val

    def set(self, dotted_key: str, value: Any, save: bool = False):
        """Set config value by dotted path. Only saves to disk if save=True."""
        keys = dotted_key.split(".")
        target = self.config
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value
        if save:
            self.save()

    def generate_agent_token(self, agent_name: str, save: bool = True) -> str:
        """Generate a secure agent token and store it in config.
        
        Args:
            agent_name: Name prefix for the token.
            save: If True, persist the token to the YAML config file.
        
        Returns:
            The generated token string.
        """
        random_suffix = secrets.token_hex(16)
        token = f"{agent_name}-{random_suffix}"
        self.set("server.agent_token", token)
        if save:
            self.save()
        return token

    def hash_token(self, token: str) -> str:
        """Hash token for secure storage."""
        return hashlib.sha256(token.encode()).hexdigest()

    def verify_token(self, provided_token: str, stored_hash: str) -> bool:
        """Constant-time token verification to prevent timing attacks."""
        provided_hash = self.hash_token(provided_token)
        return hmac.compare_digest(provided_hash, stored_hash)
