"""
Agent-X Compatibility Layer
Provides graceful fallbacks for missing optional dependencies.
This ensures the system works even when some packages are not installed.
"""
import logging
import sys

# Pre-emptively redirect any 'playwright' imports to 'patchright' to avoid library conflicts
try:
    import patchright
    sys.modules['playwright'] = patchright
    try:
        import patchright.async_api
        sys.modules['playwright.async_api'] = patchright.async_api
    except ImportError:
        pass
    try:
        import patchright.sync_api
        sys.modules['playwright.sync_api'] = patchright.sync_api
    except ImportError:
        pass
except ImportError:
    pass

from typing import Any, Optional

logger = logging.getLogger("agent-x.compat")

# Track which packages are missing (for diagnostics)
_MISSING_PACKAGES = set()

def _warn_missing(package: str, feature: str = None) -> None:
    """Log a warning about a missing optional package."""
    _MISSING_PACKAGES.add(package)
    msg = f"Optional package '{package}' is not installed"
    if feature:
        msg += f" — {feature} will be unavailable"
    logger.debug(msg)


def get_missing_packages() -> list:
    """Return list of missing optional packages detected so far."""
    return sorted(_MISSING_PACKAGES)


# ─── aiohttp ──────────────────────────────────────────────────
try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    _warn_missing("aiohttp", "HTTP REST API server")

    # Stub for aiohttp.web
    class _FakeAiohttpWeb:
        class Application:
            def __init__(self, *args, **kwargs):
                self._routes = []
            def router(self):
                return self
            def add_get(self, path, handler):
                self._routes.append(("GET", path))
            def add_post(self, path, handler):
                self._routes.append(("POST", path))
            def add_delete(self, path, handler):
                self._routes.append(("DELETE", path))
        class Request:
            pass
        class Response:
            def __init__(self, body=None, status=200, content_type=None):
                self.body = body
                self.status = status
                self.content_type = content_type
        @staticmethod
        def json_response(data, status=200):
            return _FakeAiohttpWeb.Response(data, status, "application/json")
        @staticmethod
        def Response(body=None, status=200, content_type=None):
            return _FakeAiohttpWeb.Response(body, status, content_type)

    web = _FakeAiohttpWeb()
    sys.modules["aiohttp.web"] = web


# ─── sqlalchemy ───────────────────────────────────────────────
try:
    from sqlalchemy import event, text, select, update, or_, delete
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import DeclarativeBase
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    _warn_missing("sqlalchemy", "Database persistence (will use in-memory)")

    class DeclarativeBase:
        """Stub for SQLAlchemy DeclarativeBase."""
        metadata = None


# ─── redis ────────────────────────────────────────────────────
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    _warn_missing("redis", "Redis caching (will use in-memory)")

    class _FakeRedis:
        """Stub for redis.asyncio.Redis."""
        async def get(self, key): return None
        async def set(self, key, value, ex=None): pass
        async def delete(self, *keys): pass
        async def ping(self): return True
        async def close(self): pass

    redis = _FakeRedis()


# ─── PyJWT ────────────────────────────────────────────────────
try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    _warn_missing("PyJWT", "JWT authentication (will use legacy tokens only)")


# ─── openai ───────────────────────────────────────────────────
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    _warn_missing("openai", "OpenAI LLM integration")


# ─── anthropic ────────────────────────────────────────────────
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    _warn_missing("anthropic", "Anthropic Claude integration")


# ─── mcp ──────────────────────────────────────────────────────
try:
    import mcp
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    _warn_missing("mcp", "Model Context Protocol connector")


# ─── structlog ────────────────────────────────────────────────
try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    _warn_missing("structlog", "Structured JSON logging (will use standard logging)")


# ─── ddddocr ──────────────────────────────────────────────────
try:
    import ddddocr
    DDDDOCR_AVAILABLE = True
except ImportError:
    DDDDOCR_AVAILABLE = False
    _warn_missing("ddddocr", "CAPTCHA OCR solving")


# ─── cloudscraper ─────────────────────────────────────────────
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False
    _warn_missing("cloudscraper", "Cloudflare JS challenge solver")


# ─── trafilatura ──────────────────────────────────────────────
try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    _warn_missing("trafilatura", "Article text extraction")


# ─── readability ──────────────────────────────────────────────
try:
    from readability import Document
    READABILITY_AVAILABLE = True
except ImportError:
    READABILITY_AVAILABLE = False
    _warn_missing("readability-lxml", "HTML content extraction")


# ─── DrissionPage ─────────────────────────────────────────────
try:
    from DrissionPage import ChromiumPage
    DRISSIONPAGE_AVAILABLE = True
except ImportError:
    DRISSIONPAGE_AVAILABLE = False
    _warn_missing("DrissionPage", "Alternative browser engine")


# ─── patchright ───────────────────────────────────────────────
try:
    from patchright.async_api import async_playwright
    PATCHRIGHT_AVAILABLE = True
    PLAYWRIGHT_AVAILABLE = True  # Mapped via namespace alias
except ImportError:
    PATCHRIGHT_AVAILABLE = False
    PLAYWRIGHT_AVAILABLE = False
    _warn_missing("patchright", "Primary browser engine (CRITICAL - install required)")


# ─── whisper ──────────────────────────────────────────────────
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    _warn_missing("whisper", "Audio transcription")


# ─── boto3 ────────────────────────────────────────────────────
try:
    import boto3
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    _warn_missing("boto3", "AWS Bedrock integration")


def check_all():
    """Print a summary of all missing optional packages."""
    missing = get_missing_packages()
    if missing:
        logger.info(f"Missing optional packages ({len(missing)}): {', '.join(missing)}")
        logger.info("Core functionality works; some features are unavailable.")
    else:
        logger.info("All optional packages are installed.")
    return missing
