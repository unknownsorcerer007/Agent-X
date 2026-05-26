"""
Agent-OS Agent Server — Production Edition
WebSocket + REST API with full auth, validation, rate limiting, and audit logging.
"""
import asyncio
import hashlib
import json
import logging
import re
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Any
from aiohttp import web

import websockets

logger = logging.getLogger("agent-os.server")

AGENT_OS_VERSION = "3.2.0"

# ─── Scope-to-Command Mapping ──────────────────────────────────
COMMAND_SCOPES = {
    # Browser commands require 'browser' scope
    "navigate": ["browser"], "click": ["browser"], "type": ["browser"],
    "screenshot": ["browser"], "get-content": ["browser"],
    "smart-navigate": ["browser"], "back": ["browser"], "forward": ["browser"],
    "reload": ["browser"], "fill-form": ["browser"], "hover": ["browser"],
    "select": ["browser"], "upload": ["browser"], "wait": ["browser"],
    "evaluate-js": ["browser"], "scroll": ["browser"], "scroll-into-view": ["browser"], "right-click": ["browser"],
    "context-action": ["browser"], "double-click": ["browser"], "press": ["browser"],
    "clear-input": ["browser"], "checkbox": ["browser"], "drag-drop": ["browser"],
    "drag-offset": ["browser"], "viewport": ["browser"], "tabs": ["browser"],
    "get-dom": ["browser"], "get-links": ["browser"], "get-images": ["browser"],
    "get-text": ["browser"], "get-attr": ["browser"], "console-logs": ["browser"],
    "smart-find": ["browser"], "smart-find-all": ["browser"],
    "smart-click": ["browser"], "smart-fill": ["browser"],
    "adaptive-find": ["browser"], "adaptive-save": ["browser"],
    "adaptive-stats": ["browser"], "adaptive-cleanup": ["browser"],
    "snapshot": ["browser"], "snapshot-interactive": ["browser"],
    "snapshot-selector": ["browser"],
    # Security commands require 'admin' scope
    "scan-xss": ["admin"], "scan-sqli": ["admin"], "scan-sensitive": ["admin"],
    # Workflow commands require 'workflows' scope
    "workflow": ["workflows"], "workflow-save": ["workflows"],
    "workflow-template": ["workflows"], "workflow-list": ["workflows"],
    "workflow-status": ["workflows"], "workflow-json": ["workflows"],
    # Session commands require 'browser' scope
    "save-session": ["browser"], "restore-session": ["browser"],
    "list-sessions": ["browser"], "delete-session": ["browser"],
    "export-tokens": ["browser"], "load-tokens": ["browser"],
    "save-creds": ["browser"], "auto-login": ["browser"],
    "get-cookies": ["browser"], "set-cookie": ["browser"],
    # Proxy commands require 'browser' scope
    "set-proxy": ["browser"], "get-proxy": ["browser"],
    "emulate-device": ["browser"], "list-devices": ["browser"],
    # Network capture requires 'browser' scope
    "network-start": ["browser"], "network-stop": ["browser"],
    "network-get": ["browser"], "network-apis": ["browser"],
    "network-detail": ["browser"], "network-stats": ["browser"],
    "network-export": ["browser"], "network-clear": ["browser"],
    # Page analysis requires 'browser' scope
    "page-summary": ["browser"], "page-tables": ["browser"],
    "page-seo": ["browser"], "page-structured": ["browser"],
    "page-emails": ["browser"], "page-phones": ["browser"],
    "page-accessibility": ["browser"], "analyze": ["browser"],
    "analyze-search": ["browser"],
    # Scanning commands (route queries) require 'browser' scope
    "route": ["browser"], "route-stats": ["browser"],
    "fetch": ["browser"], "nav-stats": ["browser"],
}
DEFAULT_SCOPE = "browser"


class AgentServer:
    """
    Dual-protocol agent server:
    - WebSocket (port 8000): For real-time agent communication
    - HTTP REST (port 8001): For curl/simple integrations

    Production features:
    - API key + JWT authentication
    - Per-user rate limiting via Redis
    - Input validation and sanitization
    - Usage tracking and audit logging
    - Structured error responses
    """

    def __init__(self, config, browser, session_manager, persistent_manager=None,
                 auth_middleware=None, api_key_manager=None, user_manager=None,
                 redis_client=None):
        self.config = config
        self.browser = browser
        self.session_manager = session_manager
        self.persistent_manager = persistent_manager
        self.auth_middleware = auth_middleware
        self.api_key_manager = api_key_manager
        self.user_manager = user_manager
        self.redis = redis_client
        self._ws_clients: Dict[str, websockets.WebSocketServerProtocol] = {}
        self._ws_server = None
        self._http_app = None
        self._http_runner = None
        self._start_time = time.time()

        # Smart Wait + Auto Heal + Auto Retry + Recording + Multi-Agent engines (lazy init)
        self._smart_wait = None
        self._auto_heal = None
        self._auto_retry = None
        self._recorder = None
        self._replay = None
        self._analyzer = None
        self._agent_hub = None
        self._proxy_manager = None
        self._smart_nav = None
        self._web_query_router = None
        self._web_router = None  # Web-Need Router (lazy init)
        self._login_handoff = None  # Login Handoff Manager (lazy init)

        # Locks for thread-safe lazy initialization (double-check locking)
        self._smart_wait_lock = asyncio.Lock()
        self._auto_heal_lock = asyncio.Lock()
        self._auto_retry_lock = asyncio.Lock()
        self._recorder_lock = asyncio.Lock()
        self._replay_lock = asyncio.Lock()
        self._analyzer_lock = asyncio.Lock()
        self._agent_hub_lock = asyncio.Lock()
        self._proxy_manager_lock = asyncio.Lock()
        self._smart_nav_lock = asyncio.Lock()
        self._web_query_router_lock = asyncio.Lock()
        self._web_router_lock = asyncio.Lock()
        self._login_handoff_lock = asyncio.Lock()
        self._adaptive_scraper = None
        self._adaptive_scraper_lock = asyncio.Lock()
        self._page_analyzer = None
        self._page_analyzer_lock = asyncio.Lock()
        self._captcha_preemptor = None
        self._captcha_preemptor_lock = asyncio.Lock()

        # Agent Swarm (lazy init, thread-safe)
        self._swarm_router = None
        self._swarm_pool = None
        self._swarm_backend = None
        self._swarm_formatter = None
        self._swarm_aggregator = None
        self._swarm_quality_scorer = None
        self._swarm_enabled = config.get("swarm.enabled", False)
        self._swarm_lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None

        # In-memory rate limiting fallback
        self._rate_limits: Dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self._rate_max_requests = config.get("server.rate_limit_max", 60)
        self._rate_window_seconds = config.get("server.rate_limit_window", 60)
        self._rate_cleanup_task = None

        # Per-command timeout (seconds)
        self._command_timeout = config.get("server.command_timeout", 60)

        # WebSocket auth cache (avoid re-authenticating every message)
        self._ws_auth_cache: Dict[str, Dict] = {}  # token prefix → auth_context
        self._ws_auth_cache_ttl = 300  # Re-validate every 5 minutes
        self._ws_auth_cache_times: Dict[str, float] = {}  # token prefix → last_validation_time

        # Dynamically register any missing _cmd_ methods in COMMAND_SCOPES
        for attr_name in dir(self):
            if attr_name.startswith("_cmd_") and callable(getattr(self, attr_name)):
                cmd_name = attr_name[5:].replace("_", "-")
                if cmd_name not in COMMAND_SCOPES:
                    # Assign appropriate scope based on command name
                    if any(prefix in cmd_name for prefix in ("hub-", "workflow-", "record-", "replay-")):
                        COMMAND_SCOPES[cmd_name] = ["workflows"]
                    elif any(prefix in cmd_name for prefix in ("scan-", "add-extension")):
                        COMMAND_SCOPES[cmd_name] = ["admin"]
                    else:
                        COMMAND_SCOPES[cmd_name] = ["browser"]

    async def start(self):
        """Start both WebSocket and HTTP servers."""
        ws_host = self.config.get("server.host", "0.0.0.0")
        ws_port = self.config.get("server.ws_port", 8000)
        http_port = self.config.get("server.http_port", 8001)

        # Start WebSocket server
        self._ws_server = await websockets.serve(
            self._ws_handler, ws_host, ws_port,
            ping_interval=30, ping_timeout=10,
            max_size=10 * 1024 * 1024,  # 10MB max message
        )
        logger.info(f"WebSocket server listening on ws://{ws_host}:{ws_port}")

        # Start HTTP server with auth middleware
        self._http_app = web.Application(
            middlewares=self._get_middlewares(),
            client_max_size=self.config.get("server.max_request_body_kb", 1024) * 1024,
        )
        self._setup_routes()
        self._http_runner = web.AppRunner(self._http_app)
        await self._http_runner.setup()
        site = web.TCPSite(self._http_runner, ws_host, http_port)
        await site.start()
        logger.info(f"HTTP server listening on http://{ws_host}:{http_port}")

        # Start rate limit cleanup task (for in-memory fallback)
        self._rate_cleanup_task = asyncio.create_task(self._rate_limit_cleanup_loop())

    async def stop(self):
        """Stop both servers."""
        if self._rate_cleanup_task:
            self._rate_cleanup_task.cancel()
        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()
        if self._http_runner:
            await self._http_runner.cleanup()
        logger.info("Agent servers stopped")

    def _get_middlewares(self):
        """Build middleware chain."""
        middlewares = [self._cors_middleware]

        # Add auth middleware if configured
        if self.auth_middleware:
            from src.auth.middleware import create_auth_middleware
            middlewares.insert(0, create_auth_middleware(self.auth_middleware))

        # Add request timing middleware
        middlewares.append(self._timing_middleware)

        return middlewares

    def _validate_token_legacy(self, token: str) -> bool:
        """Legacy token validation (backward compat). Uses constant-time comparison."""
        if not token:
            return False
        import hmac as _hmac
        allowed = self.config.get("server.allowed_tokens", [])
        if allowed:
            for allowed_token in allowed:
                if _hmac.compare_digest(token, allowed_token):
                    return True
            return False
        configured = self.config.get("server.agent_token")
        if configured:
            return _hmac.compare_digest(token, configured)
        return False

    async def _authenticate_ws(self, token: str) -> Optional[dict]:
        """
        Authenticate WebSocket connection.
        Tries: API key → JWT → legacy token.
        Returns auth context dict or None.
        """
        # Try API key
        if self.api_key_manager and token.startswith("aos_"):
            auth = await self.api_key_manager.authenticate(token)
            if auth:
                return auth

        # Try JWT
        if self.auth_middleware and not token.startswith("aos_"):
            payload = self.auth_middleware.jwt.verify_token(token, token_type="access")
            if payload:
                return {
                    "user_id": payload["sub"],
                    "api_key_id": payload.get("key_id"),
                    "scopes": payload.get("scopes", []),
                    "auth_method": "jwt",
                }

        # Legacy token fallback
        if self.config.get("security.allow_legacy_token_auth", True):
            if self._validate_token_legacy(token):
                return {
                    "user_id": "legacy",
                    "api_key_id": None,
                    "scopes": ["browser"],
                    "auth_method": "legacy_token",
                }

        return None

    def _check_rate_limit(self, identifier: str) -> bool:
        """In-memory rate limit check (fallback when Redis unavailable)."""
        now = time.time()
        window = self._rate_window_seconds
        max_req = self._rate_max_requests
        timestamps = self._rate_limits[identifier]
        cutoff = now - window
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        if len(timestamps) >= max_req:
            return False
        timestamps.append(now)
        return True

    async def _rate_limit_cleanup_loop(self):
        """Periodically clean up stale rate limit entries and auth cache."""
        while True:
            try:
                await asyncio.sleep(120)
                now = time.time()
                cutoff = now - self._rate_window_seconds
                stale = [k for k, ts in self._rate_limits.items()
                         if not ts or ts[-1] < cutoff]
                for k in stale:
                    del self._rate_limits[k]
                if len(self._rate_limits) > 50000:
                    sorted_keys = sorted(
                        self._rate_limits.keys(),
                        key=lambda k: self._rate_limits[k][-1] if self._rate_limits[k] else 0
                    )
                    for k in sorted_keys[:10000]:
                        del self._rate_limits[k]

                # Clean up expired WS auth cache entries (prevent memory leak)
                auth_cutoff = now - self._ws_auth_cache_ttl
                expired_auth = [
                    k for k, t in self._ws_auth_cache_times.items()
                    if t < auth_cutoff
                ]
                for k in expired_auth:
                    self._ws_auth_cache.pop(k, None)
                    self._ws_auth_cache_times.pop(k, None)
                if expired_auth:
                    logger.debug(f"Cleaned {len(expired_auth)} expired WS auth cache entries")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Rate limit cleanup error: {e}")

    # Default allowed CORS origins: localhost variants for development.
    # In production, set server.cors_allowed_origins to specific domains.
    _DEFAULT_CORS_ORIGINS = {
        "http://localhost", "http://localhost:3000", "http://localhost:8080",
        "http://localhost:8001", "http://localhost:8002", "http://localhost:5173",
        "http://127.0.0.1", "http://127.0.0.1:3000", "http://127.0.0.1:8080",
        "http://127.0.0.1:8001", "http://127.0.0.1:8002", "http://127.0.0.1:5173",
        "http://0.0.0.0:8001", "http://0.0.0.0:8002",
    }

    def _get_cors_headers(self, request=None) -> Dict[str, str]:
        """Return CORS headers for API responses. Uses configured allowed origins.

        Priority:
        1. Explicit server.cors_allowed_origins list (production)
        2. Explicit server.cors_origin string (single origin)
        3. Default localhost development origins
        """
        allowed_origins = self.config.get("server.cors_allowed_origins", [])
        cors_origin = self.config.get("server.cors_origin", "")

        # If specific origins configured, validate against request Origin
        if allowed_origins and request:
            origin = request.headers.get("Origin", "")
            if origin in allowed_origins:
                cors_origin = origin
            else:
                cors_origin = ""  # Reject — no CORS header set
        elif cors_origin:
            # Single origin configured — use as-is
            pass
        elif request:
            # No explicit config — allow localhost development origins
            origin = request.headers.get("Origin", "")
            if origin in self._DEFAULT_CORS_ORIGINS:
                cors_origin = origin
            # Non-localhost origins without config: no CORS header (secure default)

        headers = {
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
            "Access-Control-Max-Age": "86400",
            "Access-Control-Expose-Headers": "X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset",
        }
        if cors_origin:
            headers["Access-Control-Allow-Origin"] = cors_origin
        return headers

    def _setup_routes(self):
        """Setup HTTP routes."""
        async def _cors_preflight(request: web.Request) -> web.Response:
            return web.Response(headers=self._get_cors_headers())

        self._http_app.router.add_route("OPTIONS", "/{path:.*}", _cors_preflight)

        # Public endpoints (no auth)
        self._http_app.router.add_get("/status", self._handle_status)
        self._http_app.router.add_get("/health", self._handle_health)
        self._http_app.router.add_get("/commands", self._handle_commands_list)

        # Web-Need Router endpoint (no auth — zero-cost, lightweight)
        self._http_app.router.add_post("/route", self._handle_route)

        # Auth endpoints
        self._http_app.router.add_post("/auth/register", self._handle_register)
        self._http_app.router.add_post("/auth/login", self._handle_login)
        self._http_app.router.add_post("/auth/refresh", self._handle_refresh)
        self._http_app.router.add_post("/auth/api-keys", self._handle_create_api_key)
        self._http_app.router.add_get("/auth/api-keys", self._handle_list_api_keys)
        self._http_app.router.add_delete("/auth/api-keys/{key_prefix}", self._handle_revoke_api_key)

        # Authenticated command endpoint
        self._http_app.router.add_post("/command", self._handle_command)

        # Debug endpoints
        self._http_app.router.add_get("/debug", self._handle_debug)
        self._http_app.router.add_get("/screenshot", self._handle_screenshot)

        # Persistent browser routes
        if self.persistent_manager:
            self._http_app.router.add_get("/persistent/health", self._handle_persistent_health)
            self._http_app.router.add_get("/persistent/users", self._handle_persistent_users)
            self._http_app.router.add_post("/persistent/command", self._handle_persistent_command)

        # Agent Swarm (Search) endpoints
        self._http_app.router.add_get("/swarm/health", self._handle_swarm_health)
        self._http_app.router.add_post("/swarm/search", self._handle_swarm_search)
        self._http_app.router.add_post("/swarm/route", self._handle_swarm_route)
        self._http_app.router.add_get("/swarm/agents", self._handle_swarm_agents)
        self._http_app.router.add_get("/swarm/config", self._handle_swarm_config)
        self._http_app.router.add_put("/swarm/config", self._handle_swarm_config_update)

        # Login Handoff endpoints
        self._http_app.router.add_post("/handoff/start", self._handle_handoff_start)
        self._http_app.router.add_get("/handoff/{handoff_id}", self._handle_handoff_status)
        self._http_app.router.add_post("/handoff/{handoff_id}/complete", self._handle_handoff_complete)
        self._http_app.router.add_post("/handoff/{handoff_id}/cancel", self._handle_handoff_cancel)
        self._http_app.router.add_get("/handoff", self._handle_handoff_list)
        self._http_app.router.add_get("/handoff/history", self._handle_handoff_history)
        self._http_app.router.add_get("/handoff/stats", self._handle_handoff_stats)
        self._http_app.router.add_post("/handoff/detect", self._handle_handoff_detect)

    @web.middleware
    async def _cors_middleware(self, request: web.Request, handler):
        """Add CORS headers to all responses. Validates origin against config."""
        response = await handler(request)
        for key, value in self._get_cors_headers(request).items():
            response.headers[key] = value
        return response

    @web.middleware
    async def _timing_middleware(self, request: web.Request, handler):
        """Add request timing, correlation ID, and structured logging."""
        import uuid
        start = time.time()
        request_id = str(uuid.uuid4())
        request["request_id"] = request_id
        try:
            response = await handler(request)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error(f"Request error: {request.method} {request.path} ({elapsed:.0f}ms) [{request_id}]: {e}")
            return web.json_response(
                {"status": "error", "error": "Internal server error", "request_id": request_id},
                status=500,
                headers=self._get_cors_headers(),
            )
        elapsed = (time.time() - start) * 1000
        response.headers["X-Response-Time"] = f"{elapsed:.0f}ms"
        response.headers["X-Request-ID"] = request_id
        if elapsed > 5000:
            logger.warning(f"Slow request: {request.method} {request.path} ({elapsed:.0f}ms) [{request_id}]")
        return response

    # ─── WebSocket Handler ───────────────────────────────────

    async def _ws_handler(self, websocket, path):
        """Handle WebSocket connections from agents."""
        client_id = f"ws-{id(websocket)}"

        # Validate Origin header to prevent cross-site WebSocket hijacking
        try:
            origin = websocket.request_headers.get("Origin", "")
            if origin:
                allowed_origins = self.config.get("server.cors_allowed_origins", [])
                if allowed_origins and origin not in allowed_origins:
                    logger.warning(f"WebSocket rejected: origin '{origin}' not in allowed list")
                    await websocket.close(code=4003, reason="Origin not allowed")
                    return
                elif not allowed_origins:
                    # Default: only allow localhost origins
                    from urllib.parse import urlparse as _ws_urlparse
                    parsed_origin = _ws_urlparse(origin)
                    if parsed_origin.hostname not in ("localhost", "127.0.0.1", "0.0.0.0", ""):
                        logger.warning(f"WebSocket rejected: non-localhost origin '{origin}'")
                        await websocket.close(code=4003, reason="Origin not allowed")
                        return
        except Exception:
            pass  # Origin check is best-effort

        try:
            first_msg = await asyncio.wait_for(websocket.recv(), timeout=15.0)
            data = json.loads(first_msg)
            token = data.get("token", "")

            auth_context = await self._authenticate_ws(token)
            if not auth_context:
                await websocket.send(json.dumps({
                    "status": "error",
                    "error": "Invalid authentication token"
                }))
                await websocket.close(code=4001)
                return

            self._ws_clients[client_id] = websocket
            logger.info(f"Agent connected via WebSocket: {client_id} (user: {auth_context['user_id']})")
            await websocket.send(json.dumps({
                "status": "authenticated",
                "client_id": client_id,
                "user_id": auth_context["user_id"],
            }))

        except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
            logger.warning(f"WebSocket auth failed: {e}")
            try:
                await websocket.close(code=4001)
            except Exception:
                logger.debug("Failed to close WebSocket after auth failure")
            return

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    token = data.get("token", "")

                    # Re-authenticate each message (with caching)
                    cache_key = hashlib.sha256(token.encode()).hexdigest()[:64]  # SHA-256 hash to prevent key collision
                    last_validated = self._ws_auth_cache_times.get(cache_key, 0)
                    if (time.time() - last_validated) < self._ws_auth_cache_ttl and cache_key in self._ws_auth_cache:
                        auth_context = self._ws_auth_cache[cache_key]
                    else:
                        auth_context = await self._authenticate_ws(token)
                        if auth_context:
                            self._ws_auth_cache[cache_key] = auth_context
                            self._ws_auth_cache_times[cache_key] = time.time()
                    if not auth_context:
                        await websocket.send(json.dumps({
                            "status": "error", "error": "Invalid token"
                        }))
                        continue

                    # Rate limit
                    if self.redis:
                        allowed, _, _ = await self.redis.check_rate_limit(
                            f"ws:{auth_context['user_id']}",
                            auth_context.get("requests_per_minute", self._rate_max_requests),
                            self._rate_window_seconds,
                        )
                        if not allowed:
                            await websocket.send(json.dumps({
                                "status": "error", "error": "Rate limit exceeded"
                            }))
                            continue
                    elif not self._check_rate_limit(f"ws:{auth_context.get('user_id', client_id)}"):
                        await websocket.send(json.dumps({
                            "status": "error", "error": "Rate limit exceeded"
                        }))
                        continue

                    # Validate input
                    try:
                        from src.validation.schemas import validate_command_payload
                        validated_data = validate_command_payload(data)
                    except Exception as ve:
                        await websocket.send(json.dumps({
                            "status": "error", "error": f"Validation error: {str(ve)}"
                        }))
                        continue

                    # Track usage
                    start = time.time()
                    result = await self._process_command(validated_data, auth_context)
                    duration_ms = int((time.time() - start) * 1000)

                    # Log usage
                    if self.user_manager:
                        await self.user_manager.log_usage(
                            user_id=auth_context["user_id"],
                            command=validated_data.get("command", "unknown"),
                            status=result.get("status", "error"),
                            duration_ms=duration_ms,
                            api_key_id=auth_context.get("api_key_id"),
                            client_ip="websocket",
                        )

                    await websocket.send(json.dumps(result))

                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"status": "error", "error": "Invalid JSON"}))
                except Exception as e:
                    logger.error(f"WS error: {e}")
                    await websocket.send(json.dumps({"status": "error", "error": self._sanitize_error_message(str(e))}))
        finally:
            self._ws_clients.pop(client_id, None)
            logger.info(f"Agent disconnected: {client_id}")

    # ─── HTTP Handlers ──────────────────────────────────────

    async def _handle_register(self, request: web.Request) -> web.Response:
        """POST /auth/register — Register a new user."""
        if not self.user_manager:
            return web.json_response(
                {"status": "error", "error": "User management not enabled"},
                status=501, headers=self._get_cors_headers(),
            )
        try:
            data = await request.json()
            email = data.get("email", "").strip()
            username = data.get("username", "").strip()
            password = data.get("password", "")

            if not email or not username or not password:
                return web.json_response(
                    {"status": "error", "error": "email, username, and password required"},
                    status=400, headers=self._get_cors_headers(),
                )

            user = await self.user_manager.create_user(
                email=email, username=username, password=password,
                display_name=data.get("display_name"),
                organization=data.get("organization"),
            )

            # Log audit
            await self.user_manager.log_audit(
                user_id=user["id"], action="user.register",
                success=True, client_ip=request.remote,
            )

            return web.json_response({"status": "success", "user": user},
                                      headers=self._get_cors_headers())
        except ValueError as e:
            return web.json_response(
                {"status": "error", "error": self._sanitize_error_message(str(e))},
                status=400, headers=self._get_cors_headers(),
            )
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return web.json_response(
                {"status": "error", "error": "Registration failed"},
                status=500, headers=self._get_cors_headers(),
            )

    async def _handle_login(self, request: web.Request) -> web.Response:
        """POST /auth/login — Authenticate and get JWT tokens."""
        if not self.user_manager or not self.auth_middleware:
            return web.json_response(
                {"status": "error", "error": "Auth not enabled"},
                status=501, headers=self._get_cors_headers(),
            )
        try:
            data = await request.json()
            login = data.get("username") or data.get("email", "")
            password = data.get("password", "")

            if not login or not password:
                return web.json_response(
                    {"status": "error", "error": "username/email and password required"},
                    status=400, headers=self._get_cors_headers(),
                )

            # Brute-force protection
            client_ip = request.remote or "unknown"
            identifier = f"{client_ip}:{login}"
            if not self.auth_middleware.check_login_attempts(identifier):
                lockout = self.auth_middleware.get_lockout_remaining(identifier)
                return web.json_response(
                    {"status": "error", "error": f"Too many failed attempts. Try again in {lockout} seconds."},
                    status=429, headers=self._get_cors_headers(),
                )

            user = await self.user_manager.authenticate_user(login, password)
            if not user:
                self.auth_middleware.record_login_failure(identifier)
                await self.user_manager.log_audit(
                    user_id=None, action="user.login_failed",
                    success=False, client_ip=request.remote,
                    details={"login": login},
                )
                return web.json_response(
                    {"status": "error", "error": "Invalid credentials"},
                    status=401, headers=self._get_cors_headers(),
                )

            # Successful login
            self.auth_middleware.record_login_success(identifier)

            tokens = self.auth_middleware.jwt.create_token_pair(
                user_id=user["user_id"],
                scopes=user.get("scopes", []),
            )

            await self.user_manager.log_audit(
                user_id=user["user_id"], action="user.login",
                success=True, client_ip=request.remote,
            )

            return web.json_response({
                "status": "success",
                **tokens,
                "user": {
                    "id": user["user_id"],
                    "username": user["username"],
                    "plan": user["plan"],
                },
            }, headers=self._get_cors_headers())

        except Exception as e:
            logger.error(f"Login error: {e}")
            return web.json_response(
                {"status": "error", "error": "Login failed"},
                status=500, headers=self._get_cors_headers(),
            )

    async def _handle_refresh(self, request: web.Request) -> web.Response:
        """POST /auth/refresh — Get new access token from refresh token."""
        if not self.auth_middleware:
            return web.json_response(
                {"status": "error", "error": "Auth not enabled"},
                status=501, headers=self._get_cors_headers(),
            )
        try:
            data = await request.json()
            refresh_token = data.get("refresh_token", "")

            if not refresh_token:
                return web.json_response(
                    {"status": "error", "error": "refresh_token required"},
                    status=400, headers=self._get_cors_headers(),
                )

            new_tokens = self.auth_middleware.jwt.refresh_access_token(refresh_token)
            if not new_tokens:
                return web.json_response(
                    {"status": "error", "error": "Invalid or expired refresh token"},
                    status=401, headers=self._get_cors_headers(),
                )

            return web.json_response(
                {"status": "success", **new_tokens},
                headers=self._get_cors_headers(),
            )
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return web.json_response(
                {"status": "error", "error": "Token refresh failed"},
                status=400, headers=self._get_cors_headers(),
            )

    async def _handle_create_api_key(self, request: web.Request) -> web.Response:
        """POST /auth/api-keys — Create a new API key."""
        if not self.api_key_manager:
            return web.json_response(
                {"status": "error", "error": "API key management not enabled"},
                status=501, headers=self._get_cors_headers(),
            )

        # Must be authenticated via JWT
        auth = request.get("auth_context")
        if not auth:
            return web.json_response(
                {"status": "error", "error": "Authentication required"},
                status=401, headers=self._get_cors_headers(),
            )

        try:
            data = request.get('parsed_body') or await request.json()
            key_data = await self.api_key_manager.create_key(
                user_id=auth["user_id"],
                name=data.get("name", "Unnamed Key"),
                scopes=data.get("scopes"),
                requests_per_minute=data.get("requests_per_minute", 60),
                requests_per_day=data.get("requests_per_day", 10000),
                expires_in_days=data.get("expires_in_days"),
            )

            if self.user_manager:
                await self.user_manager.log_audit(
                    user_id=auth["user_id"], action="api_key.create",
                    success=True, client_ip=request.remote,
                    details={"key_prefix": key_data["key_prefix"], "name": data.get("name")},
                )

            return web.json_response(
                {"status": "success", "api_key": key_data},
                headers=self._get_cors_headers(),
            )
        except Exception as e:
            logger.error(f"API key creation error: {e}")
            return web.json_response(
                {"status": "error", "error": "Failed to create API key"},
                status=400, headers=self._get_cors_headers(),
            )

    async def _handle_list_api_keys(self, request: web.Request) -> web.Response:
        """GET /auth/api-keys — List user's API keys."""
        auth = request.get("auth_context")
        if not auth:
            return web.json_response(
                {"status": "error", "error": "Authentication required"},
                status=401, headers=self._get_cors_headers(),
            )

        if not self.api_key_manager:
            return web.json_response(
                {"status": "error", "error": "API key management not enabled"},
                status=501, headers=self._get_cors_headers(),
            )

        keys = await self.api_key_manager.list_keys(auth["user_id"])
        return web.json_response(
            {"status": "success", "keys": keys, "count": len(keys)},
            headers=self._get_cors_headers(),
        )

    async def _handle_revoke_api_key(self, request: web.Request) -> web.Response:
        """DELETE /auth/api-keys/{key_prefix} — Revoke an API key."""
        auth = request.get("auth_context")
        if not auth:
            return web.json_response(
                {"status": "error", "error": "Authentication required"},
                status=401, headers=self._get_cors_headers(),
            )

        if not self.api_key_manager:
            return web.json_response(
                {"status": "error", "error": "API key management not enabled"},
                status=501, headers=self._get_cors_headers(),
            )

        key_prefix = request.match_info["key_prefix"]
        revoked = await self.api_key_manager.revoke_key(key_prefix, auth["user_id"])

        if revoked and self.user_manager:
            await self.user_manager.log_audit(
                user_id=auth["user_id"], action="api_key.revoke",
                success=True, client_ip=request.remote,
                details={"key_prefix": key_prefix},
            )

        return web.json_response(
            {"status": "success" if revoked else "error",
             "message": "Key revoked" if revoked else "Key not found"},
            status=200 if revoked else 404,
            headers=self._get_cors_headers(),
        )

    async def _handle_command(self, request: web.Request) -> web.Response:
        """Handle HTTP POST /command — main command endpoint."""
        try:
            data = request.get('parsed_body') or await request.json()
        except Exception:
            return web.json_response(
                {"status": "error", "error": "Invalid JSON body"},
                status=400, headers=self._get_cors_headers(),
            )

        # Auth context injected by middleware
        auth_context = request.get("auth_context")
        if not auth_context:
            # Fallback: try legacy token auth
            token = data.get("token", "")
            if self.config.get("security.allow_legacy_token_auth", True):
                if self._validate_token_legacy(token):
                    auth_context = {
                        "user_id": "legacy",
                        "api_key_id": None,
                        "scopes": ["browser"],
                        "auth_method": "legacy_token",
                    }

            if not auth_context:
                return web.json_response(
                    {"status": "error", "error": "Invalid or missing authentication"},
                    status=401, headers=self._get_cors_headers(),
                )

        # Validate and sanitize input
        try:
            from src.validation.schemas import validate_command_payload
            validated_data = validate_command_payload(data)
        except Exception as ve:
            return web.json_response(
                {"status": "error", "error": f"Validation error: {str(ve)}"},
                status=400, headers=self._get_cors_headers(),
            )

        # Execute command
        start = time.time()
        result = await self._process_command(validated_data, auth_context)
        duration_ms = int((time.time() - start) * 1000)

        # Log usage
        if self.user_manager:
            await self.user_manager.log_usage(
                user_id=auth_context["user_id"],
                command=validated_data.get("command", "unknown"),
                status=result.get("status", "error"),
                duration_ms=duration_ms,
                api_key_id=auth_context.get("api_key_id"),
                client_ip=request.remote,
            )

        return web.json_response(result, headers=self._get_cors_headers())

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Handle HTTP GET /status — public endpoint with basic info only."""
        status = {
            "status": "running",
            "version": "3.2.0",
            "uptime_seconds": int(time.time() - self._start_time),
            "browser_active": self.browser.browser is not None,
        }

        # Extended info only for authenticated requests
        auth_context = request.get("auth_context")
        if auth_context:
            status["active_sessions"] = len(self.session_manager.list_active_sessions())
            status["active_ws_clients"] = len(self._ws_clients)
            status["persistent_browser_enabled"] = self.persistent_manager is not None
            status["auth_enabled"] = {
                "api_keys": self.api_key_manager is not None,
                "jwt": self.auth_middleware is not None,
                "legacy_token": self.config.get("security.allow_legacy_token_auth", True),
            }
            if hasattr(self.browser, "tls_stats"):
                status["tls"] = self.browser.tls_stats
            if self.persistent_manager:
                ph = self.persistent_manager.get_health()
                status["persistent_browser"] = ph.get("summary", {})
            if self._web_router:
                status["web_router"] = self._web_router.get_stats()

        return web.json_response(status)

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle HTTP GET /health — deep health check."""
        checks = {"server": "healthy"}

        # Database health
        try:
            from src.infra.database import get_db
            db = get_db()
            db_health = await db.health_check()
            checks["database"] = db_health["status"]
        except Exception:
            checks["database"] = "not_configured"

        # Redis health
        if self.redis:
            redis_health = await self.redis.health_check()
            checks["redis"] = redis_health["status"]
            checks["redis_mode"] = redis_health.get("mode", "unknown")
        else:
            checks["redis"] = "not_configured"

        # Browser health — verify actual browser is responsive
        if self.browser.browser:
            try:
                # Quick check: can we get the current page?
                if self.browser.page:
                    await self.browser.page.title()
                checks["browser"] = "healthy"
            except Exception as e:
                checks["browser"] = f"degraded: {e}"
        else:
            checks["browser"] = "not_running"

        overall = "healthy" if all(
            v in ("healthy", "not_configured") for v in checks.values()
        ) else "degraded"

        return web.json_response({
            "status": overall,
            "checks": checks,
            "timestamp": time.time(),
        })

    async def _handle_commands_list(self, request: web.Request) -> web.Response:
        """Handle HTTP GET /commands — list all available commands."""
        # Same command list as before, truncated for brevity
        commands = self._get_command_definitions()
        return web.json_response(commands)

    async def _handle_debug(self, request: web.Request) -> web.Response:
        """Handle HTTP GET /debug — requires authentication."""
        auth_context = request.get("auth_context")
        if not auth_context:
            return web.json_response(
                {"status": "error", "error": "Authentication required"},
                status=401, headers=self._get_cors_headers(),
            )
        return web.json_response({
            "sessions": self.session_manager.list_active_sessions(),
            "uptime": int(time.time() - self._start_time),
            "ws_clients": len(self._ws_clients),
            "blocked_requests": getattr(self.browser, '_blocked_requests', 0),
            "tabs": list(getattr(self.browser, '_pages', {}).keys()),
        })

    async def _handle_screenshot(self, request: web.Request) -> web.Response:
        """Handle HTTP GET /screenshot — requires authentication."""
        auth_context = request.get("auth_context")
        if not auth_context:
            # Fallback: try legacy token from query param
            token = request.query.get("token", "")
            if token and self.config.get("security.allow_legacy_token_auth", True):
                if self._validate_token_legacy(token):
                    auth_context = {"user_id": "legacy", "auth_method": "legacy_token"}
            if not auth_context:
                return web.json_response(
                    {"status": "error", "error": "Authentication required"},
                    status=401, headers=self._get_cors_headers(),
                )
        try:
            b64 = await self.browser.screenshot()
            return web.Response(body=b64, content_type="text/plain")
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return web.json_response({"error": self._sanitize_error_message(str(e))}, status=500)

    # ─── Persistent Browser Endpoints ────────────────────────

    async def _handle_persistent_health(self, request: web.Request) -> web.Response:
        if not self.persistent_manager:
            return web.json_response({"error": "Persistent browser not enabled"}, status=404)
        return web.json_response(self.persistent_manager.get_health())

    async def _handle_persistent_users(self, request: web.Request) -> web.Response:
        if not self.persistent_manager:
            return web.json_response({"error": "Persistent browser not enabled"}, status=404)
        return web.json_response({"users": self.persistent_manager.list_users()})

    async def _handle_persistent_command(self, request: web.Request) -> web.Response:
        if not self.persistent_manager:
            return web.json_response({"error": "Persistent browser not enabled"}, status=404)
        try:
            data = request.get('parsed_body') or await request.json()
            auth_context = request.get("auth_context")
            if not auth_context:
                return web.json_response({"status": "error", "error": "Authentication required"}, status=401)

            user_id = data.get("user_id") or auth_context.get("user_id")
            command = data.get("command")
            if not command:
                return web.json_response({"status": "error", "error": "Missing 'command'"}, status=400)

            result = await self.persistent_manager.execute_for_user(user_id, command, data)
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Persistent command error: {e}")
            return web.json_response({"status": "error", "error": self._sanitize_error_message(str(e))}, status=400)

    # ─── Error Sanitization ───────────────────────────────────

    # Known error patterns mapped to user-friendly messages
    _KNOWN_ERROR_MAP = {
        "browser has been closed": "Browser session has been lost. Reconnecting…",
        "browser closed": "Browser session has been lost. Reconnecting…",
        "browser crashed": "Browser crashed unexpectedly. Recovering…",
        "target closed": "Browser target was closed. Recovering…",
        "target got disconnected": "Browser connection lost. Recovering…",
        "disconnected": "Browser connection lost. Recovering…",
        "connection closed": "Browser connection was closed. Recovering…",
        "page has been closed": "Browser page was closed. Recovering…",
        "context has been closed": "Browser context was closed. Recovering…",
        "session expired": "Session has expired. Please re-authenticate.",
        "navigation to": "Navigation failed. The page may be unreachable.",
        "net::err": "Network error occurred while loading the page.",
        "timeout": "Operation timed out. The page may be unresponsive.",
        "element is not attached": "Element is no longer available on the page.",
        "waiting for selector": "Could not find the requested element on the page.",
        "no element found": "Could not find the requested element on the page.",
    }

    # Keywords that indicate a browser crash requiring recovery
    _BROWSER_CRASH_KEYWORDS = (
        "browser has been closed",
        "browser crashed",
        "browser closed",
        "target closed",
        "target got disconnected",
        "disconnected",
        "page has been closed",
        "context has been closed",
        "connection closed",
    )

    @staticmethod
    def _is_browser_crash_error(error_str: str) -> bool:
        """Check if an error message indicates a browser crash requiring recovery."""
        lower = error_str.lower()
        return any(kw in lower for kw in AgentServer._BROWSER_CRASH_KEYWORDS)

    @staticmethod
    def _sanitize_error_message(error_str: str) -> str:
        """
        Sanitize error messages before returning to clients.

        - Maps known browser/connection errors to user-friendly messages.
        - Strips file paths, Python tracebacks, memory addresses, and internal state.
        - Returns a generic 'Internal error' for anything unrecognized,
          never leaking implementation details.
        """
        import re

        raw = str(error_str)

        # 1. Check for known error patterns first (match against the original, unsanitized string)
        raw_lower = raw.lower()
        for pattern, friendly in AgentServer._KNOWN_ERROR_MAP.items():
            if pattern in raw_lower:
                return friendly

        # 2. Strip sensitive / internal details from the raw message
        sanitized = raw

        # Remove absolute file paths (Unix and Windows styles)
        sanitized = re.sub(r'(?:/[^\s:"]+| [A-Za-z]:\\[^\s:"]+)', '[path]', sanitized)

        # Remove Python traceback lines (e.g. 'File "x", line N')
        sanitized = re.sub(r'File\s+"[^"]*".*?(?:,\s*line\s*\d+)?', '[traceback]', sanitized, flags=re.IGNORECASE)

        # Remove memory addresses (0x7f..., 0x000...)
        sanitized = re.sub(r'0x[0-9a-fA-F]{4,}', '[addr]', sanitized)

        # Remove Python object repr hints like <module 'x' at ...> or <class 'x'>
        sanitized = re.sub(r'<[^>]+>', '[object]', sanitized)

        # Remove internal variable names / dict keys that look like __dunder__
        sanitized = re.sub(r'__\w+__', '[internal]', sanitized)

        # 3. If after sanitization the message is empty or looks like only redacted tokens
        #    plus minor residue (line numbers, punctuation), return a generic message.
        stripped = sanitized.replace('[path]', '').replace('[traceback]', '').replace('[addr]', '').replace('[object]', '').replace('[internal]', '').strip()
        # Remove leftover residue like ":42", ": line 10", stray punctuation
        stripped_meaningful = re.sub(r'[:\d\s,]', '', stripped)
        if not stripped_meaningful or len(stripped_meaningful) < 3:
            return "Internal error"

        # 4. Truncate to a reasonable length
        return sanitized[:300]

    def _sanitize_error(self, error: str) -> str:
        """Sanitize error messages to prevent internal detail leakage (backward-compat wrapper)."""
        return self._sanitize_error_message(error)

    def _error_response(self, error: str, request: web.Request = None, status: int = 400) -> web.json_response:
        """Return an error response. Debug mode (?debug=1) only allowed when server started with --debug flag."""
        debug = False
        if request is not None:
            debug = (request.query.get("debug", "").strip() in ("1", "true", "yes")
                     and self.config.get("server.debug_mode", False))
        if debug:
            return web.json_response({"status": "error", "error": str(error), "debug": True}, status=status)
        return web.json_response({"status": "error", "error": self._sanitize_error_message(str(error))}, status=status)

    # ─── Agent Swarm Endpoints ─────────────────────────────

    async def _init_swarm(self):
        """Lazily initialize swarm components (thread-safe)."""
        if self._swarm_router is not None:
            return  # Already initialized

        if self._swarm_lock:
            async with self._swarm_lock:
                # Double-check after acquiring lock
                if self._swarm_router is not None:
                    return

                from src.agent_swarm.config import get_config
                swarm_config = get_config()

                from src.agent_swarm.router import QueryRouter
                self._swarm_router = QueryRouter(
                    confidence_threshold=swarm_config.router.confidence_threshold,
                    enable_provider_fallback=swarm_config.router.enable_provider_fallback,
                    provider_api_key=swarm_config.router.provider_api_key,
                    provider_base_url=swarm_config.router.provider_base_url,
                    provider_model=swarm_config.router.provider_model,
                    provider_name=swarm_config.router.provider_name,
                    provider_max_tokens=swarm_config.router.provider_max_tokens,
                    provider_timeout=swarm_config.router.provider_timeout,
                )

                from src.agent_swarm.search.http_backend import HTTPSearchBackend
                self._swarm_backend = HTTPSearchBackend(
                    impersonate=swarm_config.search.chrome_impersonate,
                    user_agent=swarm_config.search.user_agent,
                )

                from src.agent_swarm.agents.pool import AgentPool
                self._swarm_pool = AgentPool(
                    max_workers=swarm_config.agents.max_workers,
                    search_timeout=swarm_config.agents.search_timeout,
                    search_backend=self._swarm_backend,
                )

                from src.agent_swarm.output.formatter import OutputFormatter
                self._swarm_formatter = OutputFormatter(
                    format=swarm_config.output.format,
                    max_results=swarm_config.output.max_results,
                    min_relevance_score=swarm_config.output.min_relevance_score,
                )

                from src.agent_swarm.output.aggregator import ResultAggregator
                self._swarm_aggregator = ResultAggregator(
                    deduplicate=swarm_config.output.deduplicate,
                    min_relevance=swarm_config.output.min_relevance_score,
                    max_results=swarm_config.output.max_results,
                )

                from src.agent_swarm.output.quality import QualityScorer
                self._swarm_quality_scorer = QualityScorer()

                logger.info("Agent Swarm initialized (router, pool, backend, formatter, aggregator, scorer)")
        else:
            # No lock available (shouldn't happen with asyncio), init without lock
            from src.agent_swarm.config import get_config
            swarm_config = get_config()

            from src.agent_swarm.router import QueryRouter
            self._swarm_router = QueryRouter(
                confidence_threshold=swarm_config.router.confidence_threshold,
                enable_provider_fallback=swarm_config.router.enable_provider_fallback,
                provider_api_key=swarm_config.router.provider_api_key,
                provider_base_url=swarm_config.router.provider_base_url,
                provider_model=swarm_config.router.provider_model,
                provider_name=swarm_config.router.provider_name,
            )

            from src.agent_swarm.search.http_backend import HTTPSearchBackend
            self._swarm_backend = HTTPSearchBackend()

            from src.agent_swarm.agents.pool import AgentPool
            self._swarm_pool = AgentPool(
                max_workers=swarm_config.agents.max_workers,
                search_timeout=swarm_config.agents.search_timeout,
                search_backend=self._swarm_backend,
            )

            from src.agent_swarm.output.formatter import OutputFormatter
            self._swarm_formatter = OutputFormatter()

            from src.agent_swarm.output.aggregator import ResultAggregator
            self._swarm_aggregator = ResultAggregator()

            from src.agent_swarm.output.quality import QualityScorer
            self._swarm_quality_scorer = QualityScorer()

    async def _swarm_auth_check(self, request: web.Request) -> Optional[web.Response]:
        """Check authentication for swarm endpoints. Returns error response or None."""
        auth_context = request.get("auth_context")
        if not auth_context:
            # Check for API key in Authorization header or X-API-Key header only
            # Query params removed: API keys in URLs get logged in server logs, browser history, and proxies
            api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
            if not api_key:
                api_key = request.headers.get("X-API-Key", "")
            if not api_key:
                return web.json_response(
                    {"status": "error", "error": "Authentication required. Provide Bearer token in Authorization header or X-API-Key header."},
                    status=401, headers=self._get_cors_headers(),
                )
            # Validate API key
            if self.api_key_manager:
                try:
                    auth = await self.api_key_manager.authenticate(api_key)
                    if not auth:
                        return web.json_response(
                            {"status": "error", "error": "Invalid API key"},
                            status=401, headers=self._get_cors_headers(),
                        )
                except Exception as auth_exc:
                    # Fallback: if async auth fails, try hmac comparison with configured key
                    logger.warning(f"API key manager auth failed, trying hmac fallback: {auth_exc}")
                    configured_key = self.config.get("swarm.api_key")
                    if configured_key:
                        import hmac as _hmac
                        if not _hmac.compare_digest(api_key, configured_key):
                            return web.json_response(
                                {"status": "error", "error": "Invalid API key"},
                                status=401, headers=self._get_cors_headers(),
                            )
                    else:
                        return web.json_response(
                            {"status": "error", "error": "Authentication service error"},
                            status=503, headers=self._get_cors_headers(),
                        )
            elif self.config.get("swarm.api_key"):
                import hmac as _hmac
                if not _hmac.compare_digest(api_key, self.config.get("swarm.api_key")):
                    return web.json_response(
                        {"status": "error", "error": "Invalid API key"},
                        status=401, headers=self._get_cors_headers(),
                    )
        return None

    async def _handle_swarm_health(self, request: web.Request) -> web.Response:
        """GET /swarm/health — Swarm health check (no auth required)."""
        health = {
            "status": "healthy" if self._swarm_enabled else "disabled",
            "enabled": self._swarm_enabled,
            "initialized": self._swarm_router is not None,
        }

        if self._swarm_router is not None:
            health["backend_available"] = self._swarm_backend.is_available() if self._swarm_backend else False
            health["pool_status"] = self._swarm_pool.get_status() if self._swarm_pool else None
            health["provider_available"] = (
                self._swarm_router.tier2.is_available()
                if self._swarm_router and self._swarm_router.tier2
                else False
            )

        return web.json_response(health, headers=self._get_cors_headers())

    async def _handle_swarm_search(self, request: web.Request) -> web.Response:
        """POST /swarm/search — Execute a swarm search query."""
        # Auth check
        auth_err = await self._swarm_auth_check(request)
        if auth_err:
            return auth_err

        # Rate limit check — use authenticated user ID when available, fallback to IP
        auth_context = request.get("auth_context")
        rate_id = (auth_context or {}).get("user_id") or request.remote or "unknown"
        if not self._check_rate_limit(f"swarm:{rate_id}"):
            return web.json_response(
                {"status": "error", "error": "Rate limit exceeded"},
                status=429, headers=self._get_cors_headers(),
            )

        # Parse request body
        try:
            data = request.get('parsed_body') or await request.json()
        except Exception:
            return web.json_response(
                {"status": "error", "error": "Invalid JSON body"},
                status=400, headers=self._get_cors_headers(),
            )

        # Input validation
        query = data.get("query", "").strip()
        if not query:
            return web.json_response(
                {"status": "error", "error": "Missing 'query' parameter"},
                status=400, headers=self._get_cors_headers(),
            )
        if len(query) > 500:
            return web.json_response(
                {"status": "error", "error": "Query too long (max 500 characters)"},
                status=400, headers=self._get_cors_headers(),
            )

        max_results = min(int(data.get("max_results", 10)), 50)
        agent_profiles = data.get("agent_profiles", ["generalist"])
        if not isinstance(agent_profiles, list) or len(agent_profiles) > 50:
            return web.json_response(
                {"status": "error", "error": "agent_profiles must be a list with max 50 entries"},
                status=400, headers=self._get_cors_headers(),
            )

        # Swarm size controls how many agents to spawn (supports up to 50 for swarm mode)
        swarm_size = data.get("swarm_size", 5)
        try:
            swarm_size = int(swarm_size)
        except (TypeError, ValueError):
            return web.json_response(
                {"status": "error", "error": "swarm_size must be an integer"},
                status=400, headers=self._get_cors_headers(),
            )
        if swarm_size < 1 or swarm_size > 50:
            return web.json_response(
                {"status": "error", "error": "swarm_size must be between 1 and 50"},
                status=400, headers=self._get_cors_headers(),
            )

        # Validate profile keys
        from src.agent_swarm.agents.profiles import get_all_profile_keys
        valid_keys = get_all_profile_keys()
        for key in agent_profiles:
            if key not in valid_keys:
                return web.json_response(
                    {"status": "error", "error": f"Invalid agent profile: '{key}'. Valid: {valid_keys}"},
                    status=400, headers=self._get_cors_headers(),
                )

        output_format = data.get("format", "json")
        if output_format not in ("json", "markdown"):
            return web.json_response(
                {"status": "error", "error": "format must be 'json' or 'markdown'"},
                status=400, headers=self._get_cors_headers(),
            )

        # Initialize swarm if needed
        try:
            await self._init_swarm()
        except Exception as e:
            logger.error(f"Swarm init failed: {e}")
            return web.json_response(
                {"status": "error", "error": "Search service initialization failed"},
                status=503, headers=self._get_cors_headers(),
            )

        # Execute search
        start_time = time.time()
        try:
            # Route the query
            classification = self._swarm_router.route(query)

            # Determine which agents to use
            if classification.suggested_agents and agent_profiles == ["generalist"]:
                # Use router-suggested agents if user didn't specify
                profiles_to_use = classification.suggested_agents[:5]
            else:
                profiles_to_use = agent_profiles

            # Dynamic agent spawning for swarm mode: when swarm_size > 5,
            # create temporary clone agents based on the most relevant profiles
            temp_agent_keys = []
            temp_agents_list = []
            if swarm_size > len(profiles_to_use) and self._swarm_pool is not None:
                # Calculate how many extra agents are needed
                extra_needed = swarm_size - len(profiles_to_use)
                # Distribute clones across the base profiles, starting with the most relevant
                clones_per_profile = extra_needed // len(profiles_to_use) if profiles_to_use else 0
                remainder = extra_needed % len(profiles_to_use) if profiles_to_use else 0

                for i, profile_key in enumerate(profiles_to_use):
                    count = clones_per_profile + (1 if i < remainder else 0)
                    if count > 0:
                        clones = self._swarm_pool._spawn_temp_agents(profile_key, count)
                        temp_agents_list.extend(clones)
                        # Track temp keys for cleanup
                        for j, clone in enumerate(clones):
                            temp_key = f"{profile_key}-{self._swarm_pool._clone_counters.get(profile_key, 0) - count + j + 1}"
                            temp_agent_keys.append(temp_key)

                logger.info(
                    f"Swarm mode: spawned {len(temp_agents_list)} temp agents "
                    f"to reach swarm_size={swarm_size}"
                )

            try:
                # Execute parallel search (uses semaphore-limited concurrency)
                agent_results = await self._swarm_pool.search_parallel(
                    query=query,
                    agent_profiles=profiles_to_use,
                    search_backend=self._swarm_backend,
                    max_results=max_results,
                )

                # If temp agents were spawned, also run them and merge results
                if temp_agents_list:
                    from src.agent_swarm.agents.base import AgentResult
                    temp_tasks = []
                    for temp_agent in temp_agents_list:
                        temp_tasks.append(
                            self._swarm_pool._search_with_timeout(
                                temp_agent, query, self._swarm_backend
                            )
                        )
                    try:
                        temp_results = await asyncio.wait_for(
                            asyncio.gather(*temp_tasks, return_exceptions=True),
                            timeout=self._swarm_pool.search_timeout,
                        )
                        for r in temp_results:
                            if isinstance(r, AgentResult):
                                agent_results.append(r)
                            elif isinstance(r, Exception):
                                logger.error(f"Temp agent search error: {r}")
                    except asyncio.TimeoutError:
                        logger.warning("Temp agents timed out")
            finally:
                # Clean up temporary agents after search completes
                if temp_agent_keys and self._swarm_pool is not None:
                    self._swarm_pool._cleanup_temp_agents(temp_agent_keys)

            # Aggregate results
            aggregated = self._swarm_aggregator.aggregate(agent_results)

            # Score quality
            for result in aggregated:
                self._swarm_quality_scorer.query = query
                self._swarm_quality_scorer.query_words = set(query.lower().split())
                quality = self._swarm_quality_scorer.score(result)
                result.metadata["quality_score"] = quality

            # Format output
            execution_time = time.time() - start_time
            output = self._swarm_formatter.format_results(
                query=query,
                category=classification.category.value,
                tier_used=classification.source,
                agent_results=aggregated,
                execution_time=execution_time,
                confidence=classification.confidence,
            )

            if output_format == "markdown":
                return web.Response(
                    text=output.to_markdown(),
                    content_type="text/markdown",
                    headers=self._get_cors_headers(),
                )
            else:
                return web.json_response(
                    output.to_dict(),
                    headers=self._get_cors_headers(),
                )

        except Exception as e:
            logger.error(f"Swarm search error: {e}")
            return web.json_response(
                {"status": "error", "error": self._sanitize_error(str(e))},
                status=500, headers=self._get_cors_headers(),
            )

    async def _handle_swarm_route(self, request: web.Request) -> web.Response:
        """POST /swarm/route — Classify a query without executing search."""
        # Auth check
        auth_err = await self._swarm_auth_check(request)
        if auth_err:
            return auth_err

        try:
            data = request.get("parsed_body") or await request.json()
        except Exception:
            return web.json_response(
                {"status": "error", "error": "Invalid JSON body"},
                status=400, headers=self._get_cors_headers(),
            )

        query = data.get("query", "").strip()
        if not query:
            return web.json_response(
                {"status": "error", "error": "Missing 'query' parameter"},
                status=400, headers=self._get_cors_headers(),
            )
        if len(query) > 500:
            return web.json_response(
                {"status": "error", "error": "Query too long (max 500 characters)"},
                status=400, headers=self._get_cors_headers(),
            )

        # Initialize swarm if needed
        try:
            await self._init_swarm()
        except Exception as e:
            logger.error(f"Swarm init failed: {e}")
            return web.json_response(
                {"status": "error", "error": "Search service initialization failed"},
                status=503, headers=self._get_cors_headers(),
            )

        try:
            classification = self._swarm_router.route(query)
            return web.json_response({
                "status": "success",
                "classification": {
                    "category": classification.category.value,
                    "confidence": classification.confidence,
                    "reason": classification.reason,
                    "source": classification.source,
                    "suggested_agents": classification.suggested_agents,
                    "search_queries": classification.search_queries,
                },
            }, headers=self._get_cors_headers())
        except Exception as e:
            logger.error(f"Swarm route error: {e}")
            return web.json_response(
                {"status": "error", "error": self._sanitize_error(str(e))},
                status=500, headers=self._get_cors_headers(),
            )

    async def _handle_swarm_agents(self, request: web.Request) -> web.Response:
        """GET /swarm/agents — List available agent profiles and their status."""
        # Auth check
        auth_err = await self._swarm_auth_check(request)
        if auth_err:
            return auth_err

        from src.agent_swarm.agents.profiles import SEARCH_PROFILES
        profiles = []
        for key, profile in SEARCH_PROFILES.items():
            profiles.append({
                "key": key,
                "name": profile.name,
                "expertise": profile.expertise,
                "description": profile.description,
                "search_depth": profile.search_depth,
                "query_style": profile.query_style,
                "keywords": profile.keywords,
                "priority": profile.priority,
            })

        pool_status = None
        if self._swarm_pool:
            pool_status = self._swarm_pool.get_status()

        return web.json_response({
            "status": "success",
            "profiles": profiles,
            "pool": pool_status,
        }, headers=self._get_cors_headers())

    async def _handle_swarm_config(self, request: web.Request) -> web.Response:
        """GET /swarm/config — Get current swarm configuration."""
        # Auth check
        auth_err = await self._swarm_auth_check(request)
        if auth_err:
            return auth_err

        from src.agent_swarm.config import get_config
        swarm_config = get_config()

        # Mask sensitive fields
        config_dict = swarm_config.model_dump()
        if config_dict.get("router", {}).get("provider_api_key"):
            config_dict["router"]["provider_api_key"] = "***masked***"
        if config_dict.get("search", {}).get("agent_os_api_key"):
            config_dict["search"]["agent_os_api_key"] = "***masked***"

        return web.json_response({
            "status": "success",
            "config": config_dict,
            "enabled": self._swarm_enabled,
            "initialized": self._swarm_router is not None,
        }, headers=self._get_cors_headers())

    async def _handle_swarm_config_update(self, request: web.Request) -> web.Response:
        """PUT /swarm/config — Update swarm configuration at runtime."""
        # Auth check (requires auth)
        auth_err = await self._swarm_auth_check(request)
        if auth_err:
            return auth_err

        try:
            data = request.get("parsed_body") or await request.json()
        except Exception:
            return web.json_response(
                {"status": "error", "error": "Invalid JSON body"},
                status=400, headers=self._get_cors_headers(),
            )

        # Only allow certain config updates at runtime
        allowed_updates = {
            "confidence_threshold", "enable_provider_fallback",
            "provider_api_key", "provider_base_url", "provider_model",
            "max_results", "max_workers", "search_timeout",
        }

        updated = {}
        if self._swarm_router:
            if "confidence_threshold" in data:
                val = float(data["confidence_threshold"])
                if 0.0 <= val <= 1.0:
                    self._swarm_router.confidence_threshold = val
                    self._swarm_router.tier1.confidence_threshold = val
                    updated["confidence_threshold"] = val

            if "enable_provider_fallback" in data:
                val = bool(data["enable_provider_fallback"])
                self._swarm_router.enable_provider_fallback = val
                updated["enable_provider_fallback"] = val

            if "provider_api_key" in data:
                self._swarm_router.update_provider_config(api_key=data["provider_api_key"])
                updated["provider_api_key"] = "***updated***"

            if "provider_base_url" in data:
                self._swarm_router.update_provider_config(base_url=data["provider_base_url"])
                updated["provider_base_url"] = data["provider_base_url"]

            if "provider_model" in data:
                self._swarm_router.update_provider_config(model=data["provider_model"])
                updated["provider_model"] = data["provider_model"]

            if "provider_name" in data:
                self._swarm_router.update_provider_config(provider=data["provider_name"])
                updated["provider_name"] = data["provider_name"]

        if self._swarm_pool and "max_workers" in data:
            val = int(data["max_workers"])
            if 1 <= val <= 50:
                self._swarm_pool.max_workers = val
                updated["max_workers"] = val

        if self._swarm_pool and "search_timeout" in data:
            val = float(data["search_timeout"])
            if 5.0 <= val <= 120.0:
                self._swarm_pool.search_timeout = val
                updated["search_timeout"] = val

        if self._swarm_formatter and "max_results" in data:
            val = int(data["max_results"])
            if 1 <= val <= 50:
                self._swarm_formatter.max_results = val
                updated["max_results"] = val

        if not updated:
            return web.json_response(
                {"status": "error", "error": f"No valid updates. Allowed fields: {sorted(allowed_updates)}"},
                status=400, headers=self._get_cors_headers(),
            )

        return web.json_response({
            "status": "success",
            "updated": updated,
        }, headers=self._get_cors_headers())

    # ─── Command Processing ─────────────────────────────────

    async def _process_command(self, data: Dict, auth_context: Dict = None) -> Dict[str, Any]:
        """Process any agent command with auth context, scope enforcement, crash recovery, and timeout."""
        command = data.get("command", "").lower()
        if not command:
            return {"status": "error", "error": "Missing 'command'"}

        # Scope enforcement: check if the authenticated user has the required scope
        if auth_context:
            required_scopes = COMMAND_SCOPES.get(command, [DEFAULT_SCOPE])
            user_scopes = auth_context.get("scopes", ["browser"])
            if not any(s in user_scopes for s in required_scopes):
                return {
                    "status": "error",
                    "error": f"Insufficient scope. Required: {required_scopes}, Have: {user_scopes}",
                }

        # Get or create session
        token = data.get("token", auth_context.get("user_id", "unknown") if auth_context else "unknown")
        session = self.session_manager.get_session_by_token(token)
        if not session:
            session = self.session_manager.create_session(token)

        session.commands_executed += 1

        # Execute with per-command timeout
        timeout_seconds = self._command_timeout
        command_task = None
        try:
            command_task = asyncio.create_task(
                self._execute_command(command, data, session)
            )
            result = await asyncio.wait_for(
                asyncio.shield(command_task),
                timeout=timeout_seconds,
            )
            result["session_id"] = session.session_id
            return result
        except asyncio.TimeoutError:
            # Cancel the timed-out task to prevent double-execution
            if command_task and not command_task.done():
                command_task.cancel()
                try:
                    await asyncio.wait_for(command_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
            logger.error(f"Command timed out [{command}] after {timeout_seconds}s")
            # A timeout may have been caused by a browser hang; attempt recovery
            try:
                logger.info("Attempting browser recovery after command timeout…")
                await asyncio.wait_for(self.browser.recover(), timeout=30)
                logger.info("Browser recovered after timeout; retrying command once")
                try:
                    retry_task = asyncio.create_task(
                        self._execute_command(command, data, session)
                    )
                    result = await asyncio.wait_for(
                        retry_task,
                        timeout=timeout_seconds,
                    )
                    result["session_id"] = session.session_id
                    return result
                except asyncio.TimeoutError:
                    if not retry_task.done():
                        retry_task.cancel()
                        try:
                            await asyncio.wait_for(retry_task, timeout=2.0)
                        except Exception:
                            pass
                    logger.error(f"Command retry also timed out [{command}]")
                    return {
                        "status": "error",
                        "error": "Command timed out after recovery",
                        "session_id": session.session_id,
                    }
                except Exception as retry_exc:
                    logger.error(f"Command retry after recovery failed [{command}]: {retry_exc}")
                    return {
                        "status": "error",
                        "error": self._sanitize_error_message(str(retry_exc)),
                        "session_id": session.session_id,
                    }
            except Exception as recover_exc:
                logger.error(f"Browser recovery after timeout failed: {recover_exc}")
            return {
                "status": "error",
                "error": "Command timed out",
                "session_id": session.session_id,
            }
        except Exception as e:
            error_str = str(e)
            logger.error(f"Command error [{command}]: {e}", exc_info=True)

            # Detect browser crash and attempt recovery + single retry
            if self._is_browser_crash_error(error_str):
                try:
                    logger.info(f"Browser crash detected for command [{command}]; attempting recovery…")
                    await asyncio.wait_for(self.browser.recover(), timeout=30)
                    logger.info("Browser recovered; retrying command once")
                    try:
                        retry_task = asyncio.create_task(
                            self._execute_command(command, data, session)
                        )
                        result = await asyncio.wait_for(
                            retry_task,
                            timeout=timeout_seconds,
                        )
                        result["session_id"] = session.session_id
                        return result
                    except asyncio.TimeoutError:
                        if not retry_task.done():
                            retry_task.cancel()
                            try:
                                await asyncio.wait_for(retry_task, timeout=2.0)
                            except Exception:
                                pass
                        return {
                            "status": "error",
                            "error": "Command timed out after crash recovery",
                            "session_id": session.session_id,
                        }
                    except Exception as retry_exc:
                        logger.error(f"Command retry after crash recovery failed [{command}]: {retry_exc}")
                        return {
                            "status": "error",
                            "error": self._sanitize_error_message(str(retry_exc)),
                            "session_id": session.session_id,
                        }
                except Exception as recover_exc:
                    logger.error(f"Browser crash recovery failed: {recover_exc}")
                    return {
                        "status": "error",
                        "error": "Browser recovery failed. Please try again later.",
                        "session_id": session.session_id,
                    }

            # Non-crash error: sanitize before returning to client
            return {
                "status": "error",
                "error": self._sanitize_error_message(error_str),
                "session_id": session.session_id,
            }

    async def _execute_command(self, command: str, data: Dict, session) -> Dict:
        """Route command to appropriate handler."""
        handlers = {
            # Web-Need Router
            "route": self._cmd_route,
            "route-stats": self._cmd_route_stats,
            # Navigation
            "navigate": self._cmd_navigate,
            "fetch": self._cmd_fetch,
            "smart-navigate": self._cmd_smart_navigate,
            "nav-stats": self._cmd_nav_stats,
            "fill-form": self._cmd_fill_form,
            "click": self._cmd_click,
            "type": self._cmd_type,
            "press": self._cmd_press,
            "screenshot": self._cmd_screenshot,
            "get-content": self._cmd_get_content,
            "get-dom": self._cmd_get_dom,
            "scroll": self._cmd_scroll,
            "scroll-into-view": self._cmd_scroll_into_view,
            "hover": self._cmd_hover,
            "select": self._cmd_select,
            "upload": self._cmd_upload,
            "wait": self._cmd_wait,
            "evaluate-js": self._cmd_evaluate_js,
            "back": self._cmd_back,
            "forward": self._cmd_forward,
            "reload": self._cmd_reload,
            "get-links": self._cmd_get_links,
            "get-images": self._cmd_get_images,
            "right-click": self._cmd_right_click,
            "context-action": self._cmd_context_action,
            "drag-drop": self._cmd_drag_drop,
            "drag-offset": self._cmd_drag_offset,
            "double-click": self._cmd_double_click,
            "clear-input": self._cmd_clear_input,
            "checkbox": self._cmd_checkbox,
            "get-text": self._cmd_get_text,
            "get-attr": self._cmd_get_attr,
            "viewport": self._cmd_viewport,
            "add-extension": self._cmd_add_extension,
            "console-logs": self._cmd_console_logs,
            "get-cookies": self._cmd_get_cookies,
            "set-cookie": self._cmd_set_cookie,
            "scan-xss": self._cmd_scan_xss,
            "scan-sqli": self._cmd_scan_sqli,
            "scan-sensitive": self._cmd_scan_sensitive,
            "transcribe": self._cmd_transcribe,
            "auto-login": self._cmd_auto_login,
            "save-creds": self._cmd_save_creds,
            "fill-job": self._cmd_fill_job,
            "tabs": self._cmd_tabs,
            # Smart Element Finder
            "smart-find": self._cmd_smart_find,
            "smart-find-all": self._cmd_smart_find_all,
            "smart-click": self._cmd_smart_click,
            "smart-fill": self._cmd_smart_fill,
            # Workflow Engine
            "workflow": self._cmd_workflow,
            "workflow-template": self._cmd_workflow_template,
            "workflow-json": self._cmd_workflow_json,
            "workflow-save": self._cmd_workflow_save,
            "workflow-list": self._cmd_workflow_list,
            "workflow-status": self._cmd_workflow_status,
            # Network Capture
            "network-start": self._cmd_network_start,
            "network-stop": self._cmd_network_stop,
            "network-get": self._cmd_network_get,
            "network-apis": self._cmd_network_apis,
            "network-detail": self._cmd_network_detail,
            "network-stats": self._cmd_network_stats,
            "network-export": self._cmd_network_export,
            "network-clear": self._cmd_network_clear,
            # Page Analyzer
            "page-summary": self._cmd_page_summary,
            "page-tables": self._cmd_page_tables,
            "page-structured": self._cmd_page_structured,
            "page-emails": self._cmd_page_emails,
            "page-phones": self._cmd_page_phones,
            "page-accessibility": self._cmd_page_accessibility,
            "page-seo": self._cmd_page_seo,
            # AI-Structured Content
            "ai-content": self._cmd_ai_content,
            # Captcha Preemption
            "captcha-assess": self._cmd_captcha_assess,
            "captcha-preflight": self._cmd_captcha_preflight,
            "captcha-monitor-start": self._cmd_captcha_monitor_start,
            "captcha-monitor-stop": self._cmd_captcha_monitor_stop,
            "captcha-health": self._cmd_captcha_health,
            "captcha-shutdown": self._cmd_captcha_shutdown,
            # LLM Provider
            "llm-complete": self._cmd_llm_complete,
            "llm-classify": self._cmd_llm_classify,
            "llm-extract": self._cmd_llm_extract,
            "llm-summarize": self._cmd_llm_summarize,
            "llm-provider-set": self._cmd_llm_provider_set,
            "llm-token-usage": self._cmd_llm_token_usage,
            "llm-cache-clear": self._cmd_llm_cache_clear,
            # AI Structured Output
            "structured-extract": self._cmd_structured_extract,
            "structured-deduplicate": self._cmd_structured_deduplicate,
            "structured-schema": self._cmd_structured_schema,
            "structured-format": self._cmd_structured_format,
            # Proxy
            "set-proxy": self._cmd_set_proxy,
            "get-proxy": self._cmd_get_proxy,
            # TLS Fingerprint HTTP Requests
            "tls-get": self._cmd_tls_get,
            "tls-post": self._cmd_tls_post,
            "tls-stats": self._cmd_tls_stats,
            # High-Level Proxy Rotation
            "proxy-add": self._cmd_proxy_add,
            "proxy-remove": self._cmd_proxy_remove,
            "proxy-list": self._cmd_proxy_list,
            "proxy-get": self._cmd_proxy_get,
            "proxy-rotate": self._cmd_proxy_rotate,
            "proxy-check": self._cmd_proxy_check,
            "proxy-check-all": self._cmd_proxy_check_all,
            "proxy-stats": self._cmd_proxy_stats,
            "proxy-strategy": self._cmd_proxy_strategy,
            "proxy-load-file": self._cmd_proxy_load_file,
            "proxy-load-api": self._cmd_proxy_load_api,
            "proxy-record": self._cmd_proxy_record,
            "proxy-enable": self._cmd_proxy_enable,
            "proxy-disable": self._cmd_proxy_disable,
            "proxy-save": self._cmd_proxy_save,
            "proxy-load": self._cmd_proxy_load,
            # Adaptive Scraper
            "adaptive-find": self._cmd_adaptive_find,
            "adaptive-save": self._cmd_adaptive_save,
            "adaptive-stats": self._cmd_adaptive_stats,
            "adaptive-cleanup": self._cmd_adaptive_cleanup,
            # DOM Snapshot (Token Saving)
            "snapshot": self._cmd_snapshot,
            "snapshot-interactive": self._cmd_snapshot_interactive,
            "snapshot-selector": self._cmd_snapshot_selector,
            # Mobile Emulation
            "emulate-device": self._cmd_emulate_device,
            "list-devices": self._cmd_list_devices,
            # Session Save/Restore
            "save-session": self._cmd_save_session,
            "restore-session": self._cmd_restore_session,
            "list-sessions": self._cmd_list_sessions,
            "delete-session": self._cmd_delete_session,
            "export-tokens": self._cmd_export_tokens,
            "load-tokens": self._cmd_load_tokens,
            # Smart Wait
            "smart-wait": self._cmd_smart_wait,
            "smart-wait-network": self._cmd_smart_wait_network,
            "smart-wait-dom": self._cmd_smart_wait_dom,
            "smart-wait-element": self._cmd_smart_wait_element,
            "smart-wait-page": self._cmd_smart_wait_page,
            "smart-wait-js": self._cmd_smart_wait_js,
            "smart-wait-compose": self._cmd_smart_wait_compose,
            # Auto Heal
            "heal-click": self._cmd_heal_click,
            "heal-fill": self._cmd_heal_fill,
            "heal-wait": self._cmd_heal_wait,
            "heal-hover": self._cmd_heal_hover,
            "heal-double-click": self._cmd_heal_double_click,
            "heal-selector": self._cmd_heal_selector,
            "heal-fingerprint": self._cmd_heal_fingerprint,
            "heal-fingerprint-page": self._cmd_heal_fingerprint_page,
            "heal-stats": self._cmd_heal_stats,
            "heal-clear": self._cmd_heal_clear,
            # Auto Retry
            "retry-execute": self._cmd_retry_execute,
            "retry-navigate": self._cmd_retry_navigate,
            "retry-click": self._cmd_retry_click,
            "retry-fill": self._cmd_retry_fill,
            "retry-api-call": self._cmd_retry_api_call,
            "retry-stats": self._cmd_retry_stats,
            "retry-health": self._cmd_retry_health,
            "retry-circuit-breakers": self._cmd_retry_circuit_breakers,
            "retry-reset-circuit": self._cmd_retry_reset_circuit,
            "retry-reset-all-circuits": self._cmd_retry_reset_all_circuits,
            # Session Recording
            "record-start": self._cmd_record_start,
            "record-stop": self._cmd_record_stop,
            "record-pause": self._cmd_record_pause,
            "record-resume": self._cmd_record_resume,
            "record-annotate": self._cmd_record_annotate,
            "record-status": self._cmd_record_status,
            "record-list": self._cmd_record_list,
            "record-delete": self._cmd_record_delete,
            # Replay
            "replay-load": self._cmd_replay_load,
            "replay-play": self._cmd_replay_play,
            "replay-stop": self._cmd_replay_stop,
            "replay-pause": self._cmd_replay_pause,
            "replay-resume": self._cmd_replay_resume,
            "replay-step": self._cmd_replay_step,
            "replay-jump": self._cmd_replay_jump,
            "replay-position": self._cmd_replay_position,
            "replay-events": self._cmd_replay_events,
            "replay-export-workflow": self._cmd_replay_export_workflow,
            "analyze": self._cmd_analyze,
            "analyze-search": self._cmd_analyze_search,
            # Multi-Agent Hub
            "hub-register": self._cmd_hub_register,
            "hub-unregister": self._cmd_hub_unregister,
            "hub-heartbeat": self._cmd_hub_heartbeat,
            "hub-status": self._cmd_hub_status,
            "hub-agents": self._cmd_hub_agents,
            "hub-lock": self._cmd_hub_lock,
            "hub-unlock": self._cmd_hub_unlock,
            "hub-locks": self._cmd_hub_locks,
            "hub-task-create": self._cmd_hub_task_create,
            "hub-task-claim": self._cmd_hub_task_claim,
            "hub-task-start": self._cmd_hub_task_start,
            "hub-task-complete": self._cmd_hub_task_complete,
            "hub-task-fail": self._cmd_hub_task_fail,
            "hub-task-cancel": self._cmd_hub_task_cancel,
            "hub-tasks": self._cmd_hub_tasks,
            "hub-broadcast": self._cmd_hub_broadcast,
            "hub-events": self._cmd_hub_events,
            "hub-memory-set": self._cmd_hub_memory_set,
            "hub-memory-get": self._cmd_hub_memory_get,
            "hub-memory-delete": self._cmd_hub_memory_delete,
            "hub-memory-list": self._cmd_hub_memory_list,
            "hub-handoff": self._cmd_hub_handoff,
            "hub-audit": self._cmd_hub_audit,
            # Web Query Router
            "classify-query": self._cmd_classify_query,
            "needs-web": self._cmd_needs_web,
            "query-strategy": self._cmd_query_strategy,
            "router-stats": self._cmd_router_stats,
            # Login Handoff
            "detect-login-page": self._cmd_detect_login_page,
            "login-handoff-start": self._cmd_login_handoff_start,
            "login-handoff-status": self._cmd_login_handoff_status,
            "login-handoff-complete": self._cmd_login_handoff_complete,
            "login-handoff-cancel": self._cmd_login_handoff_cancel,
            "login-handoff-list": self._cmd_login_handoff_list,
            "login-handoff-history": self._cmd_login_handoff_history,
            "login-handoff-stats": self._cmd_login_handoff_stats,
            # Status
            "health": self._cmd_health,
        }

        handler = handlers.get(command)
        if not handler:
            return {"status": "error", "error": f"Unknown command: {command}"}

        return await handler(data, session)

    # ─── Lazy-Init Engines ──────────────────────────────────

    async def _get_smart_wait(self):
        if self._smart_wait is not None:
            return self._smart_wait
        async with self._smart_wait_lock:
            if self._smart_wait is not None:
                return self._smart_wait
            from src.tools.smart_wait import SmartWait
            self._smart_wait = SmartWait(self.browser)
            return self._smart_wait

    async def _get_auto_heal(self):
        if self._auto_heal is not None:
            return self._auto_heal
        async with self._auto_heal_lock:
            if self._auto_heal is not None:
                return self._auto_heal
            from src.tools.auto_heal import AutoHeal
            self._auto_heal = AutoHeal(self.browser, smart_wait=await self._get_smart_wait())
            return self._auto_heal

    async def _get_auto_retry(self):
        if self._auto_retry is not None:
            return self._auto_retry
        async with self._auto_retry_lock:
            if self._auto_retry is not None:
                return self._auto_retry
            from src.tools.auto_retry import AutoRetry
            self._auto_retry = AutoRetry(self.browser, smart_wait=await self._get_smart_wait(), auto_heal=await self._get_auto_heal())
            return self._auto_retry

    async def _get_recorder(self):
        if self._recorder is not None:
            return self._recorder
        async with self._recorder_lock:
            if self._recorder is not None:
                return self._recorder
            from src.tools.session_recording import SessionRecorder
            self._recorder = SessionRecorder(self.browser)
            return self._recorder

    async def _get_replay(self):
        if self._replay is not None:
            return self._replay
        async with self._replay_lock:
            if self._replay is not None:
                return self._replay
            from src.tools.session_recording import SessionReplay
            self._replay = SessionReplay(self.browser)
            return self._replay

    async def _get_analyzer(self):
        if self._analyzer is not None:
            return self._analyzer
        async with self._analyzer_lock:
            if self._analyzer is not None:
                return self._analyzer
            from src.tools.session_recording import SessionAnalyzer
            self._analyzer = SessionAnalyzer()
            return self._analyzer

    async def _get_agent_hub(self):
        if self._agent_hub is not None:
            return self._agent_hub
        async with self._agent_hub_lock:
            if self._agent_hub is not None:
                return self._agent_hub
            from src.tools.multi_agent import AgentHub
            self._agent_hub = AgentHub(self.browser, self.session_manager)
            return self._agent_hub

    async def _get_proxy_manager(self):
        if self._proxy_manager is not None:
            return self._proxy_manager
        async with self._proxy_manager_lock:
            if self._proxy_manager is not None:
                return self._proxy_manager
            from src.tools.proxy_rotation import ProxyManager
            self._proxy_manager = ProxyManager()
            return self._proxy_manager

    # ─── Command Handlers (same as before) ──────────────────

    async def _get_web_router(self):
        """Lazy-init WebNeedRouter."""
        if self._web_router is not None:
            return self._web_router
        async with self._web_router_lock:
            if self._web_router is not None:
                return self._web_router
            from src.agents.web_need_router import WebNeedRouter
            self._web_router = WebNeedRouter(self.config._data if hasattr(self.config, '_data') else {})
            return self._web_router

    async def _get_smart_nav(self):
        """Lazy-init SmartNavigator."""
        if self._smart_nav is not None:
            return self._smart_nav
        async with self._smart_nav_lock:
            if self._smart_nav is not None:
                return self._smart_nav
            from src.core.smart_navigator import SmartNavigator
            self._smart_nav = SmartNavigator(self.browser)
            return self._smart_nav

    async def _get_web_query_router(self):
        """Lazy-init WebQueryRouter."""
        if self._web_query_router is not None:
            return self._web_query_router
        async with self._web_query_router_lock:
            if self._web_query_router is not None:
                return self._web_query_router
            from src.tools.web_query_router import WebQueryRouter
            self._web_query_router = WebQueryRouter()
            return self._web_query_router

    async def _get_adaptive_scraper(self):
        """Lazy-init AdaptiveScraper."""
        if self._adaptive_scraper is not None:
            return self._adaptive_scraper
        async with self._adaptive_scraper_lock:
            if self._adaptive_scraper is not None:
                return self._adaptive_scraper
            from src.tools.adaptive_scraper import AdaptiveScraper
            self._adaptive_scraper = AdaptiveScraper(self.browser)
            return self._adaptive_scraper

    async def _get_page_analyzer(self):
        """Lazy-init PageAnalyzer."""
        if self._page_analyzer is not None:
            return self._page_analyzer
        async with self._page_analyzer_lock:
            if self._page_analyzer is not None:
                return self._page_analyzer
            from src.tools.page_analyzer import PageAnalyzer
            self._page_analyzer = PageAnalyzer(self.browser)
            return self._page_analyzer

    async def _get_captcha_preemptor(self):
        """Lazy-init CaptchaPreemptor."""
        if self._captcha_preemptor is not None:
            return self._captcha_preemptor
        async with self._captcha_preemptor_lock:
            if self._captcha_preemptor is not None:
                return self._captcha_preemptor
            from src.security.captcha_preempt import CaptchaPreemptor
            from src.security.captcha_bypass import CaptchaBypass
            self._captcha_preemptor = CaptchaPreemptor(captcha_bypass=CaptchaBypass())
            return self._captcha_preemptor

    async def _get_login_handoff(self):
        """Lazy-init LoginHandoffManager."""
        if self._login_handoff is not None:
            return self._login_handoff
        async with self._login_handoff_lock:
            if self._login_handoff is not None:
                return self._login_handoff
            from src.tools.login_handoff import LoginHandoffManager
            self._login_handoff = LoginHandoffManager(self.browser, config=self.config)
            # Wire up WebSocket notification callback
            self._login_handoff.set_ws_notify(self._notify_handoff_ws)
            # Start background monitoring
            try:
                asyncio.get_running_loop().create_task(self._login_handoff.start())
            except RuntimeError:
                logger.warning("Could not auto-start LoginHandoffManager (no event loop)")
            return self._login_handoff

    async def _notify_handoff_ws(self, event_type: str, data: Dict):
        """Broadcast handoff events to all connected WebSocket clients."""
        if not self._ws_clients:
            return
        message = json.dumps({
            "type": "login_handoff",
            "event": event_type,
            "data": data,
            "timestamp": time.time(),
        })
        dead = []
        for client_id, ws in self._ws_clients.items():
            try:
                await ws.send(message)
            except Exception:
                dead.append(client_id)
        for cid in dead:
            self._ws_clients.pop(cid, None)

    # ─── Web Query Router Commands ────────────────────────────────

    async def _cmd_classify_query(self, data: Dict, session) -> Dict:
        """Classify whether a query needs web/browser access.

        Returns needs_web, confidence, category, reason, suggested_strategy.
        No LLM used — pure rule-based classification.
        """
        query = data.get("query", "")
        if not query:
            return {"status": "error", "error": "Missing 'query' parameter"}

        router = await self._get_web_query_router()
        result = router.classify(query)
        return {"status": "success", **result}

    async def _cmd_needs_web(self, data: Dict, session) -> Dict:
        """Quick check: does this query need web access? Returns boolean.

        Lightweight endpoint for agents that just need a yes/no answer.
        """
        query = data.get("query", "")
        if not query:
            return {"status": "error", "error": "Missing 'query' parameter"}

        router = await self._get_web_query_router()
        result = router.classify(query)
        return {
            "status": "success",
            "needs_web": result["needs_web"],
            "confidence": result["confidence"],
            "category": result["category"],
            "reason": result["reason"],
        }

    async def _cmd_query_strategy(self, data: Dict, session) -> Dict:
        """Get the recommended strategy for handling a query.

        Strategies: use_browser, try_http_first, no_web_needed,
        probably_no_web, uncertain_consider_web
        """
        query = data.get("query", "")
        if not query:
            return {"status": "error", "error": "Missing 'query' parameter"}

        router = await self._get_web_query_router()
        result = router.classify(query)
        return {
            "status": "success",
            "strategy": result["suggested_strategy"],
            "needs_web": result["needs_web"],
            "confidence": result["confidence"],
            "category": result["category"],
            "reason": result["reason"],
        }

    async def _cmd_router_stats(self, data: Dict, session) -> Dict:
        """Get classification statistics from the Web Query Router."""
        router = await self._get_web_query_router()
        return {"status": "success", **router.get_stats()}

    # ─── Web-Need Router Command ────────────────────────────

    async def _handle_route(self, request: web.Request) -> web.Response:
        """POST /route — Decide if a query needs web access. Zero-cost, no auth required."""
        try:
            data = request.get("parsed_body") or await request.json()
        except Exception:
            return web.json_response(
                {"status": "error", "error": "Invalid JSON body"},
                status=400, headers=self._get_cors_headers(),
            )

        query = data.get("query", "").strip()
        if not query:
            return web.json_response(
                {"status": "error", "error": "Missing 'query' field"},
                status=400, headers=self._get_cors_headers(),
            )

        context = data.get("context", "")
        router = await self._get_web_router()
        result = router.route(query, context if context else None)

        return web.json_response(
            {"status": "success", **result.to_dict()},
            headers=self._get_cors_headers(),
        )

    async def _cmd_route(self, data: Dict, session) -> Dict:
        """Command handler for 'route' — decide if query needs web access."""
        query = data.get("query", "").strip()
        if not query:
            return {"status": "error", "error": "Missing 'query'"}

        context = data.get("context", "")
        router = await self._get_web_router()
        result = router.route(query, context if context else None)
        return {"status": "success", **result.to_dict()}

    async def _cmd_route_stats(self, data: Dict, session) -> Dict:
        """Command handler for 'route-stats' — get router statistics."""
        router = await self._get_web_router()
        return {"status": "success", **router.get_stats()}

    async def _cmd_navigate(self, data: Dict, session) -> Dict:
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}

        # Navigate the browser page using browser.navigate() for interactive
        # browsing (fill forms, click, etc.). If the browser crashes or the
        # page is unreachable, fall back to smart_navigator which can use
        # HTTP fetching as a last resort — but ALWAYS try browser first so
        # the browser page is on the correct URL for subsequent commands.
        result = None
        try:
            result = await self.browser.navigate(
                url,
                wait_until=data.get("wait_until", "domcontentloaded"),
                retries=data.get("max_retries", 3),
            )
        except Exception as browser_err:
            logger.warning(f"Browser navigate failed, trying smart_navigator fallback: {browser_err}")

        # If browser.navigate failed or returned an error, try smart_navigator
        # as fallback (HTTP fetch still works even if browser crashed).
        if result is None or (isinstance(result, dict) and result.get("status") != "success"):
            try:
                smart = await self._get_smart_nav()
                smart_result = await smart.navigate(
                    url,
                    prefer_browser=True,
                    max_retries=data.get("max_retries", 3),
                )
                if result is None:
                    result = smart_result
                elif isinstance(result, dict) and isinstance(smart_result, dict):
                    # Merge: keep browser error info but use smart result
                    if smart_result.get("status") == "success":
                        result = smart_result
                        result["fallback"] = "smart_navigator"
            except Exception as smart_err:
                logger.warning(f"Smart navigator fallback also failed: {smart_err}")
                if result is None:
                    result = {"status": "error", "error": f"Navigation failed: {smart_err}"}

        # Auto-detect login pages after navigation
        if isinstance(result, dict) and result.get("status") == "success":
            try:
                handoff = await self._get_login_handoff()
                user_id = ""
                session_id = session.session_id if session else ""
                auto_result = await handoff.check_and_auto_handoff(
                    url=url,
                    page_id="main",
                    user_id=user_id,
                    session_id=session_id,
                )
                if auto_result and auto_result.get("status") == "success":
                    result["login_handoff"] = {
                        "handoff_id": auto_result["handoff_id"],
                        "domain": auto_result["domain"],
                        "page_type": auto_result["page_type"],
                        "message": auto_result["message"],
                        "state": auto_result["state"],
                    }
            except Exception as e:
                logger.debug(f"Auto login detection failed: {e}")
        return result

    async def _cmd_smart_navigate(self, data: Dict, session) -> Dict:
        """Smart navigate with automatic HTTP/browser fallback and retry."""
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}
        smart = await self._get_smart_nav()
        return await smart.navigate(
            url,
            prefer_browser=data.get("prefer_browser", False),
            max_retries=data.get("max_retries", 3),
            ai_format=data.get("ai_format", False),
        )

    async def _cmd_nav_stats(self, data: Dict, session) -> Dict:
        """Return SmartNavigator strategy stats and per-domain success rates."""
        return {"status": "success", "stats": (await self._get_smart_nav()).get_stats()}

    async def _cmd_fetch(self, data: Dict, session) -> Dict:
        """Fetch URL via TLS-spoofed HTTP (no browser, faster)."""
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}

        from src.core.http_client import TLSClient

        client = TLSClient()
        try:
            result = await client.fetch_page(url, extract_text=True)
            return {
                "status": "success" if result.get("ok") else "error",
                "url": result.get("url", url),
                "title": result.get("title", ""),
                "text": result.get("text", ""),
                "word_count": result.get("word_count", 0),
                "http_status": result.get("status", 0),
                "tls_profile": client.profile,
                "curl_cffi": client.available,
            }
        except Exception as exc:
            logger.error("fetch command failed for %s: %s", url, exc)
            return {"status": "error", "error": str(exc)}
        finally:
            await client.close()
    async def _resolve_ref(self, selector: str, session, page_id: str = "main") -> Optional[Any]:
        """Resolve an @eN ref to a Playwright element handle.

        Returns the element handle if found, None otherwise.
        Returns None immediately if selector is not an @eN ref.
        """
        import re as _re
        if not selector or not selector.startswith("@e"):
            return None

        ref_match = _re.match(r"^@e(\d+)$", selector)
        if not ref_match:
            return None

        ref_id = f"e{ref_match.group(1)}"

        if not session or not session.ref_map:
            return None

        entry = session.ref_map.get(ref_id)
        if not entry:
            return None

        backend_node_id = entry.backend_node_id
        if not backend_node_id:
            return None

        # Use CDP to find the element by backend node ID
        page = self.browser._pages.get(page_id, self.browser.page)
        if not page:
            return None

        try:
            cdp = await page.context.new_cdp_session(page)
            try:
                # Get the remote object for this backend node
                result = await cdp.send("DOM.resolveBackendNode", {
                    "backendNodeId": backend_node_id,
                })
                object_id = result.get("object", {}).get("objectId")
                if not object_id:
                    return None

                # Create a Playwright element handle from the remote object
                handle = await page.evaluate_handle(
                    "(objectId) => { return window.__cdp_objects?.[objectId] || null; }",
                    object_id,
                )
                if handle:
                    return handle

                # Fallback: use CDP to focus and then find by active element
                await cdp.send("DOM.focus", {"backendNodeId": backend_node_id})
                handle = await page.evaluate_handle("() => document.activeElement")
                return handle
            finally:
                await cdp.detach()
        except Exception as e:
            logger.debug(f"Ref resolution failed for {selector}: {e}")
            return None

    async def _cmd_fill_form(self, data: Dict, session) -> Dict:
        fields = data.get("fields", {})
        if not fields:
            return {"status": "error", "error": "Missing 'fields'"}

        # Support @eN refs in field keys — resolve to real selectors
        resolved_fields = {}
        for key, value in fields.items():
            if key.startswith("@e"):
                handle = await self._resolve_ref(key, session, data.get("page_id", "main"))
                if handle:
                    try:
                        await handle.fill(str(value))
                        resolved_fields[key] = value  # Mark as done
                    except Exception as e:
                        logger.warning(f"Ref fill_form failed for {key}: {e}")
                    finally:
                        await handle.dispose()
                else:
                    logger.warning(f"Ref {key} not found in fill_form, skipping")
            else:
                resolved_fields[key] = value

        # Fill remaining non-ref fields using the browser's fill_form
        non_ref_fields = {k: v for k, v in resolved_fields.items() if not k.startswith("@e")}
        if non_ref_fields:
            result = await self.browser.fill_form(non_ref_fields, page_id=data.get("page_id", "main"))
        else:
            result = {"status": "success", "filled": list(fields.keys()), "failed": [], "total": len(fields)}

        return result

    async def _cmd_click(self, data: Dict, session) -> Dict:
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}

        # Support @eN refs from snapshot
        if selector.startswith("@e"):
            handle = await self._resolve_ref(selector, session, data.get("page_id", "main"))
            if handle:
                try:
                    await handle.click()
                    return {"status": "success", "selector": selector, "method": "ref_click"}
                except Exception as e:
                    return {"status": "error", "error": f"Ref click failed: {e}"}
                finally:
                    await handle.dispose()
            return {"status": "error", "error": f"Ref {selector} not found or expired. Take a new snapshot."}

        return await self.browser.click(selector, page_id=data.get("page_id", "main"))

    async def _cmd_type(self, data: Dict, session) -> Dict:
        text = data.get("text")
        if not text:
            return {"status": "error", "error": "Missing 'text'"}
        return await self.browser.type_text(text, page_id=data.get("page_id", "main"))

    async def _cmd_press(self, data: Dict, session) -> Dict:
        key = data.get("key")
        if not key:
            return {"status": "error", "error": "Missing 'key'"}
        return await self.browser.press_key(key, page_id=data.get("page_id", "main"))

    async def _cmd_screenshot(self, data: Dict, session) -> Dict:
        fmt = data.get("format", "png")
        quality = data.get("quality", 80)
        b64 = await self.browser.screenshot(
            full_page=data.get("full_page", False),
            page_id=data.get("page_id", "main"),
            format=fmt,
            quality=quality,
        )
        return {"status": "success", "screenshot": b64, "format": fmt}

    async def _cmd_get_content(self, data: Dict, session) -> Dict:
        content = await self.browser.get_content(page_id=data.get("page_id", "main"))
        return {"status": "success", **content}

    async def _cmd_get_dom(self, data: Dict, session) -> Dict:
        dom = await self.browser.get_dom_snapshot(page_id=data.get("page_id", "main"))
        return {"status": "success", "dom_snapshot": dom}

    async def _cmd_scroll(self, data: Dict, session) -> Dict:
        return await self.browser.scroll(
            data.get("direction", "down"),
            data.get("amount", 500),
            page_id=data.get("page_id", "main"),
        )

    async def _cmd_scroll_into_view(self, data: Dict, session) -> Dict:
        """Scroll an element into view. Supports @eN refs from snapshot."""
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}
        if selector.startswith("@e"):
            handle = await self._resolve_ref(selector, session, data.get("page_id", "main"))
            if handle:
                try:
                    await handle.scroll_into_view_if_needed()
                    return {"status": "success", "selector": selector, "method": "ref_scroll_into_view"}
                except Exception as e:
                    return {"status": "error", "error": f"Ref scroll-into-view failed: {e}"}
                finally:
                    await handle.dispose()
            return {"status": "error", "error": f"Ref {selector} not found or expired."}
        page = self.browser._pages.get(data.get("page_id", "main"), self.browser.page)
        try:
            element = await page.wait_for_selector(selector, timeout=5000)
            if element:
                await element.scroll_into_view_if_needed()
                return {"status": "success", "selector": selector}
            return {"status": "error", "error": f"Element not found: {selector}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_hover(self, data: Dict, session) -> Dict:
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}
        # Support @eN refs from snapshot
        if selector.startswith("@e"):
            handle = await self._resolve_ref(selector, session, data.get("page_id", "main"))
            if handle:
                try:
                    await handle.hover()
                    return {"status": "success", "selector": selector, "method": "ref_hover"}
                except Exception as e:
                    return {"status": "error", "error": f"Ref hover failed: {e}"}
                finally:
                    await handle.dispose()
            return {"status": "error", "error": f"Ref {selector} not found or expired."}
        return await self.browser.hover(selector, page_id=data.get("page_id", "main"))

    async def _cmd_select(self, data: Dict, session) -> Dict:
        selector, value = data.get("selector"), data.get("value")
        if not selector or not value:
            return {"status": "error", "error": "Missing 'selector' or 'value'"}
        return await self.browser.select_option(selector, value, page_id=data.get("page_id", "main"))

    async def _cmd_upload(self, data: Dict, session) -> Dict:
        selector, file_path = data.get("selector"), data.get("file_path")
        if not selector or not file_path:
            return {"status": "error", "error": "Missing 'selector' or 'file_path'"}
        return await self.browser.upload_file(selector, file_path, page_id=data.get("page_id", "main"))

    async def _cmd_wait(self, data: Dict, session) -> Dict:
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}
        return await self.browser.wait_for_element(selector, timeout=data.get("timeout", 10000), page_id=data.get("page_id", "main"))

    async def _cmd_evaluate_js(self, data: Dict, session) -> Dict:
        script = data.get("script")
        if not script:
            return {"status": "error", "error": "Missing 'script'"}
        logger.warning(
            "evaluate-js executing arbitrary JavaScript. "
            "This has full page access — use with caution."
        )
        try:
            result = await self.browser.evaluate_js(script, page_id=data.get("page_id", "main"))
            return result
        except Exception as e:
            return {"status": "error", "error": f"Execution failed: {str(e)}"}

    async def _cmd_back(self, data: Dict, session) -> Dict:
        return await self.browser.go_back(page_id=data.get("page_id", "main"))

    async def _cmd_forward(self, data: Dict, session) -> Dict:
        return await self.browser.go_forward(page_id=data.get("page_id", "main"))

    async def _cmd_reload(self, data: Dict, session) -> Dict:
        return await self.browser.reload(page_id=data.get("page_id", "main"))

    async def _cmd_get_links(self, data: Dict, session) -> Dict:
        links = await self.browser.get_all_links(page_id=data.get("page_id", "main"))
        return {"status": "success", "links": links, "count": len(links)}

    async def _cmd_get_images(self, data: Dict, session) -> Dict:
        images = await self.browser.get_all_images(page_id=data.get("page_id", "main"))
        return {"status": "success", "images": images, "count": len(images)}

    async def _cmd_right_click(self, data: Dict, session) -> Dict:
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}
        if selector.startswith("@e"):
            handle = await self._resolve_ref(selector, session, data.get("page_id", "main"))
            if handle:
                try:
                    await handle.click(button="right")
                    return {"status": "success", "selector": selector, "method": "ref_right_click"}
                except Exception as e:
                    return {"status": "error", "error": f"Ref right-click failed: {e}"}
                finally:
                    await handle.dispose()
            return {"status": "error", "error": f"Ref {selector} not found or expired."}
        return await self.browser.right_click(selector, page_id=data.get("page_id", "main"))

    async def _cmd_context_action(self, data: Dict, session) -> Dict:
        selector, action_text = data.get("selector"), data.get("action_text")
        if not selector or not action_text:
            return {"status": "error", "error": "Missing 'selector' or 'action_text'"}
        return await self.browser.context_action(selector, action_text, page_id=data.get("page_id", "main"))

    async def _cmd_drag_drop(self, data: Dict, session) -> Dict:
        source, target = data.get("source"), data.get("target")
        if not source or not target:
            return {"status": "error", "error": "Missing 'source' or 'target'"}
        return await self.browser.drag_and_drop(source, target, page_id=data.get("page_id", "main"))

    async def _cmd_drag_offset(self, data: Dict, session) -> Dict:
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}
        return await self.browser.drag_by_offset(selector, data.get("x", 0), data.get("y", 0), page_id=data.get("page_id", "main"))

    async def _cmd_double_click(self, data: Dict, session) -> Dict:
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}
        if selector.startswith("@e"):
            handle = await self._resolve_ref(selector, session, data.get("page_id", "main"))
            if handle:
                try:
                    await handle.dblclick()
                    return {"status": "success", "selector": selector, "method": "ref_double_click"}
                except Exception as e:
                    return {"status": "error", "error": f"Ref double-click failed: {e}"}
                finally:
                    await handle.dispose()
            return {"status": "error", "error": f"Ref {selector} not found or expired."}
        return await self.browser.double_click(selector, page_id=data.get("page_id", "main"))

    async def _cmd_clear_input(self, data: Dict, session) -> Dict:
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}
        if selector.startswith("@e"):
            handle = await self._resolve_ref(selector, session, data.get("page_id", "main"))
            if handle:
                try:
                    await handle.fill("")
                    return {"status": "success", "selector": selector, "method": "ref_clear"}
                except Exception as e:
                    return {"status": "error", "error": f"Ref clear failed: {e}"}
                finally:
                    await handle.dispose()
            return {"status": "error", "error": f"Ref {selector} not found or expired."}
        return await self.browser.clear_input(selector, page_id=data.get("page_id", "main"))

    async def _cmd_checkbox(self, data: Dict, session) -> Dict:
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}
        if selector.startswith("@e"):
            handle = await self._resolve_ref(selector, session, data.get("page_id", "main"))
            if handle:
                try:
                    checked = data.get("checked", True)
                    is_checked = await handle.is_checked()
                    if is_checked != checked:
                        await handle.click()
                    return {"status": "success", "selector": selector, "checked": checked, "method": "ref_checkbox"}
                except Exception as e:
                    return {"status": "error", "error": f"Ref checkbox failed: {e}"}
                finally:
                    await handle.dispose()
            return {"status": "error", "error": f"Ref {selector} not found or expired."}
        return await self.browser.set_checkbox(selector, data.get("checked", True), page_id=data.get("page_id", "main"))

    async def _cmd_get_text(self, data: Dict, session) -> Dict:
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}
        if selector.startswith("@e"):
            handle = await self._resolve_ref(selector, session, data.get("page_id", "main"))
            if handle:
                try:
                    text = await handle.inner_text()
                    return {"status": "success", "selector": selector, "text": text, "method": "ref_get_text"}
                except Exception as e:
                    return {"status": "error", "error": f"Ref get_text failed: {e}"}
                finally:
                    await handle.dispose()
            return {"status": "error", "error": f"Ref {selector} not found or expired."}
        return await self.browser.get_element_text(selector, page_id=data.get("page_id", "main"))

    async def _cmd_get_attr(self, data: Dict, session) -> Dict:
        selector, attribute = data.get("selector"), data.get("attribute")
        if not selector or not attribute:
            return {"status": "error", "error": "Missing 'selector' or 'attribute'"}
        if selector.startswith("@e"):
            handle = await self._resolve_ref(selector, session, data.get("page_id", "main"))
            if handle:
                try:
                    value = await handle.get_attribute(attribute)
                    return {"status": "success", "selector": selector, "attribute": attribute, "value": value, "method": "ref_get_attr"}
                except Exception as e:
                    return {"status": "error", "error": f"Ref get_attr failed: {e}"}
                finally:
                    await handle.dispose()
            return {"status": "error", "error": f"Ref {selector} not found or expired."}
        return await self.browser.get_element_attribute(selector, attribute, page_id=data.get("page_id", "main"))

    async def _cmd_viewport(self, data: Dict, session) -> Dict:
        return await self.browser.set_viewport(data.get("width", 1920), data.get("height", 1080))

    async def _cmd_add_extension(self, data: Dict, session) -> Dict:
        path = data.get("extension_path")
        if not path:
            return {"status": "error", "error": "Missing 'extension_path'"}
        return await self.browser.add_extension(path)

    async def _cmd_console_logs(self, data: Dict, session) -> Dict:
        return await self.browser.get_console_logs(page_id=data.get("page_id", "main"), clear=data.get("clear", False))

    async def _cmd_get_cookies(self, data: Dict, session) -> Dict:
        return await self.browser.get_cookies()

    async def _cmd_set_cookie(self, data: Dict, session) -> Dict:
        name, value = data.get("name"), data.get("value")
        if not name or not value:
            return {"status": "error", "error": "Missing 'name' or 'value'"}
        return await self.browser.set_cookie(name=name, value=value, domain=data.get("domain"),
                                              path=data.get("path", "/"), secure=data.get("secure"),
                                              http_only=data.get("http_only", False),
                                              same_site=data.get("same_site"))

    async def _cmd_scan_xss(self, data: Dict, session) -> Dict:
        from src.tools.scanner import XSSScanner
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}
        return await XSSScanner(self.browser).scan(url)

    async def _cmd_scan_sqli(self, data: Dict, session) -> Dict:
        from src.tools.scanner import SQLiScanner
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}
        return await SQLiScanner(self.browser).scan(url)

    async def _cmd_scan_sensitive(self, data: Dict, session) -> Dict:
        from src.tools.scanner import SensitiveDataScanner
        return await SensitiveDataScanner().scan_page(self.browser)

    async def _cmd_transcribe(self, data: Dict, session) -> Dict:
        from src.tools.transcriber import Transcriber
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}
        return await Transcriber(self.config).transcribe_from_url(url, data.get("language", "auto"))

    async def _cmd_auto_login(self, data: Dict, session) -> Dict:
        from src.security.auth_handler import AuthHandler
        url, domain = data.get("url"), data.get("domain")
        if not url or not domain:
            return {"status": "error", "error": "Missing 'url' or 'domain'"}
        return await AuthHandler(self.config).auto_login(self.browser, url, domain)

    async def _cmd_save_creds(self, data: Dict, session) -> Dict:
        from src.security.auth_handler import AuthHandler
        domain = data.get("domain")
        if not domain:
            return {"status": "error", "error": "Missing 'domain'"}
        AuthHandler(self.config).save_credentials(domain, {"username": data.get("username", ""), "password": data.get("password", "")})
        return {"status": "success", "message": f"Credentials saved for {domain}"}

    async def _cmd_fill_job(self, data: Dict, session) -> Dict:
        from src.tools.form_filler import FormFiller
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}
        return await FormFiller(self.browser).fill_job_application(url, data.get("profile", {}))

    async def _cmd_tabs(self, data: Dict, session) -> Dict:
        action, tab_id = data.get("action", "list"), data.get("tab_id")
        if action == "list":
            return {"status": "success", "tabs": list(self.browser._pages.keys())}
        elif action == "new":
            tid = tab_id or f"tab-{len(self.browser._pages)}"
            await self.browser.new_tab(tid)
            return {"status": "success", "tab_id": tid}
        elif action == "switch":
            if tab_id:
                return await self.browser.switch_tab(tab_id)
            return {"status": "error", "error": "Missing 'tab_id'"}
        elif action == "close":
            if tab_id:
                if await self.browser.close_tab(tab_id):
                    return {"status": "success", "tab_id": tab_id, "closed": True}
                return {"status": "error", "error": f"Failed to close tab: {tab_id}"}
            return {"status": "error", "error": "Missing 'tab_id'"}
        return {"status": "error", "error": f"Unknown tab action: {action}"}

    # ─── Smart Finder ───────────────────────────────────────

    async def _cmd_smart_find(self, data: Dict, session) -> Dict:
        from src.tools.smart_finder import SmartElementFinder
        desc = data.get("description")
        if not desc:
            return {"status": "error", "error": "Missing 'description'"}
        return await SmartElementFinder(self.browser).find(desc, tag=data.get("tag"), timeout=data.get("timeout", 5000))

    async def _cmd_smart_find_all(self, data: Dict, session) -> Dict:
        from src.tools.smart_finder import SmartElementFinder
        desc = data.get("description")
        if not desc:
            return {"status": "error", "error": "Missing 'description'"}
        return await SmartElementFinder(self.browser).find_all(desc, tag=data.get("tag"))

    async def _cmd_smart_click(self, data: Dict, session) -> Dict:
        from src.tools.smart_finder import SmartElementFinder
        text = data.get("text")
        if not text:
            return {"status": "error", "error": "Missing 'text'"}
        return await SmartElementFinder(self.browser).click_text(text, tag=data.get("tag"), timeout=data.get("timeout", 5000))

    async def _cmd_smart_fill(self, data: Dict, session) -> Dict:
        from src.tools.smart_finder import SmartElementFinder
        label, value = data.get("label"), data.get("value")
        if not label or value is None:
            return {"status": "error", "error": "Missing 'label' or 'value'"}
        return await SmartElementFinder(self.browser).fill_text(label, value, timeout=data.get("timeout", 5000))

    # ─── Workflow ───────────────────────────────────────────

    async def _cmd_workflow(self, data: Dict, session) -> Dict:
        from src.tools.workflow import WorkflowEngine
        steps = data.get("steps")
        if not steps:
            return {"status": "error", "error": "Missing 'steps'"}
        return await WorkflowEngine(self.browser).execute(steps, variables=data.get("variables"), on_error=data.get("on_error", "abort"), retry_count=data.get("retry_count", 0), step_delay_ms=data.get("step_delay_ms", 0))

    async def _cmd_workflow_template(self, data: Dict, session) -> Dict:
        from src.tools.workflow import WorkflowEngine
        name = data.get("template_name")
        if not name:
            return {"status": "error", "error": "Missing 'template_name'"}
        return await WorkflowEngine(self.browser).execute_template(name, data.get("variables"))

    async def _cmd_workflow_json(self, data: Dict, session) -> Dict:
        from src.tools.workflow import WorkflowEngine
        j = data.get("json")
        if not j:
            return {"status": "error", "error": "Missing 'json'"}
        return await WorkflowEngine(self.browser).execute_from_json(j)

    async def _cmd_workflow_save(self, data: Dict, session) -> Dict:
        from src.tools.workflow import WorkflowEngine
        name, steps = data.get("name"), data.get("steps")
        if not name or not steps:
            return {"status": "error", "error": "Missing 'name' or 'steps'"}
        return WorkflowEngine(self.browser).save_template(name, steps, data.get("variables"), data.get("description", ""))

    async def _cmd_workflow_list(self, data: Dict, session) -> Dict:
        from src.tools.workflow import WorkflowEngine
        return {"status": "success", "templates": WorkflowEngine(self.browser).list_templates()}

    async def _cmd_workflow_status(self, data: Dict, session) -> Dict:
        from src.tools.workflow import WorkflowEngine
        wid = data.get("workflow_id")
        if not wid:
            return {"status": "error", "error": "Missing 'workflow_id'"}
        return WorkflowEngine(self.browser).get_status(wid)

    # ─── Network Capture ────────────────────────────────────

    async def _cmd_network_start(self, data: Dict, session) -> Dict:
        from src.tools.network_capture import NetworkCapture
        if not hasattr(self, '_network_capture') or self._network_capture is None:
            self._network_capture = NetworkCapture(self.browser)
        return await self._network_capture.start_capture(page_id=data.get("page_id", "main"), url_pattern=data.get("url_pattern"), resource_types=data.get("resource_types"), methods=data.get("methods"), capture_body=data.get("capture_body", False))

    async def _cmd_network_stop(self, data: Dict, session) -> Dict:
        if not hasattr(self, '_network_capture') or self._network_capture is None:
            return {"status": "error", "error": "Network capture not started"}
        return await self._network_capture.stop_capture(page_id=data.get("page_id", "main"))

    async def _cmd_network_get(self, data: Dict, session) -> Dict:
        if not hasattr(self, '_network_capture') or self._network_capture is None:
            return {"status": "error", "error": "Network capture not started"}
        return await self._network_capture.get_captured(page_id=data.get("page_id", "main"), url_pattern=data.get("url_pattern"), resource_type=data.get("resource_type"), method=data.get("method"), status_code=data.get("status_code"), api_only=data.get("api_only", False), limit=data.get("limit", 100), offset=data.get("offset", 0))

    async def _cmd_network_apis(self, data: Dict, session) -> Dict:
        if not hasattr(self, '_network_capture') or self._network_capture is None:
            return {"status": "error", "error": "Network capture not started"}
        return await self._network_capture.get_apis(page_id=data.get("page_id", "main"))

    async def _cmd_network_detail(self, data: Dict, session) -> Dict:
        rid = data.get("request_id")
        if not rid:
            return {"status": "error", "error": "Missing 'request_id'"}
        if not hasattr(self, '_network_capture') or self._network_capture is None:
            return {"status": "error", "error": "Network capture not started"}
        return await self._network_capture.get_request_detail(rid)

    async def _cmd_network_stats(self, data: Dict, session) -> Dict:
        if not hasattr(self, '_network_capture') or self._network_capture is None:
            return {"status": "error", "error": "Network capture not started"}
        return self._network_capture.get_stats(page_id=data.get("page_id", "main"))

    async def _cmd_network_export(self, data: Dict, session) -> Dict:
        if not hasattr(self, '_network_capture') or self._network_capture is None:
            return {"status": "error", "error": "Network capture not started"}
        fmt = data.get("format", "json")
        if fmt == "har":
            return await self._network_capture.export_har(page_id=data.get("page_id", "main"), filename=data.get("filename"))
        return await self._network_capture.export_json(page_id=data.get("page_id", "main"), filename=data.get("filename"))

    async def _cmd_network_clear(self, data: Dict, session) -> Dict:
        if not hasattr(self, '_network_capture') or self._network_capture is None:
            return {"status": "error", "error": "Network capture not started"}
        return await self._network_capture.clear(page_id=data.get("page_id", "main"))

    # ─── Page Analyzer ─────────────────────────────────────

    async def _cmd_page_summary(self, data: Dict, session) -> Dict:
        analyzer = await self._get_page_analyzer()
        return await analyzer.summarize(page_id=data.get("page_id", "main"))

    async def _cmd_page_tables(self, data: Dict, session) -> Dict:
        analyzer = await self._get_page_analyzer()
        return await analyzer.extract_tables(page_id=data.get("page_id", "main"))

    async def _cmd_page_structured(self, data: Dict, session) -> Dict:
        analyzer = await self._get_page_analyzer()
        return await analyzer.extract_structured_data(page_id=data.get("page_id", "main"))

    async def _cmd_page_emails(self, data: Dict, session) -> Dict:
        analyzer = await self._get_page_analyzer()
        return await analyzer.find_emails(page_id=data.get("page_id", "main"))

    async def _cmd_page_phones(self, data: Dict, session) -> Dict:
        analyzer = await self._get_page_analyzer()
        return await analyzer.find_phone_numbers(page_id=data.get("page_id", "main"))

    async def _cmd_page_accessibility(self, data: Dict, session) -> Dict:
        analyzer = await self._get_page_analyzer()
        return await analyzer.accessibility_check(page_id=data.get("page_id", "main"))

    async def _cmd_page_seo(self, data: Dict, session) -> Dict:
        analyzer = await self._get_page_analyzer()
        return await analyzer.seo_audit(page_id=data.get("page_id", "main"))

    # ─── AI-Structured Content ─────────────────────────────

    async def _cmd_ai_content(self, data: Dict, session) -> Dict:
        """
        Extract AI-structured content from the current page or a URL.

        Two modes:
        1. Current page: pass page_id (extracts from browser DOM)
        2. URL fetch: pass url (smart-navigate + extract in one step)

        Returns symmetrical JSON with:
        - content_type (article, product, listing, etc.)
        - main_text (deduplicated clean text)
        - headings, tables, lists, code_blocks, forms
        - links, images, emails, phones, prices
        - schema_org, open_graph, meta
        - summary (2-3 sentence extractive summary)

        No external AI API needed — pure DOM analysis + heuristics.
        """
        from src.tools.ai_content import AIContentExtractor

        extractor = AIContentExtractor()

        # Mode 1: Extract from current browser page
        page_id = data.get("page_id")
        if page_id or not data.get("url"):
            return await extractor.extract_from_browser(
                self.browser, page_id=page_id or "main"
            )

        # Mode 2: Fetch URL and extract (smart-navigate + extract)
        url = data.get("url")
        if url:
            smart = await self._get_smart_nav()
            nav_result = await smart.navigate(
                url,
                prefer_browser=data.get("prefer_browser", False),
                max_retries=data.get("max_retries", 3),
                ai_format=True,
            )
            # If ai_content already extracted by smart-navigate, return it
            if "ai_content" in nav_result:
                return {
                    "status": "success",
                    "data": nav_result["ai_content"],
                    "strategy_used": nav_result.get("strategy_used"),
                    "response_time_ms": nav_result.get("response_time_ms"),
                }
            # Fallback: if navigation succeeded but no ai_content, extract now
            if nav_result.get("status") == "success":
                return await extractor.extract_from_browser(self.browser, page_id="main")

            return nav_result

        return {"status": "error", "error": "Provide either 'url' or 'page_id'"}

    # ─── Captcha Preemption ─────────────────────────────────
    async def _cmd_captcha_assess(self, data: Dict, session) -> Dict:
        """Assess URL risk for captcha/bot detection before navigation."""
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url' parameter"}
        try:
            preemptor = await self._get_captcha_preemptor()
            result = preemptor.assess_url_risk(url)
            if hasattr(result, '__dict__'):
                result = {k: v for k, v in result.__dict__.items() if not k.startswith('_')}
            elif hasattr(result, '_asdict'):
                result = result._asdict()
            return {"status": "success", "data": result if isinstance(result, dict) else str(result)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_captcha_preflight(self, data: Dict, session) -> Dict:
        """Run pre-flight check for automation artifacts on current page."""
        try:
            page = self.browser.page
            if not page:
                return {"status": "error", "error": "No active browser page"}
            preemptor = await self._get_captcha_preemptor()
            result = await preemptor.preflight_check(page)
            if hasattr(result, '__dict__'):
                result = {k: v for k, v in result.__dict__.items() if not k.startswith('_')}
            elif hasattr(result, '_asdict'):
                result = result._asdict()
            return {"status": "success", "data": result if isinstance(result, dict) else str(result)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_captcha_monitor_start(self, data: Dict, session) -> Dict:
        """Start real-time captcha detection monitoring on current page."""
        try:
            page = self.browser.page
            if not page:
                return {"status": "error", "error": "No active browser page"}
            preemptor = await self._get_captcha_preemptor()
            result = await preemptor.start_monitoring(page)
            return {"status": "success", "data": str(result)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_captcha_monitor_stop(self, data: Dict, session) -> Dict:
        """Stop captcha detection monitoring."""
        try:
            preemptor = await self._get_captcha_preemptor()
            page_id = data.get("page_id", "main")
            result = await preemptor.stop_monitoring(page_id)
            return {"status": "success", "data": result if isinstance(result, dict) else str(result)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_captcha_health(self, data: Dict, session) -> Dict:
        """Check current page health for captcha/bot detection indicators."""
        try:
            page = self.browser.page
            if not page:
                return {"status": "error", "error": "No active browser page"}
            preemptor = await self._get_captcha_preemptor()
            health = await preemptor.check_page_health(page)
            result = health.to_dict() if hasattr(health, 'to_dict') else {"healthy": bool(health)}
            result["status"] = "success"
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_captcha_shutdown(self, data: Dict, session) -> Dict:
        """Emergency shutdown current page — rescue data, disable network, navigate to about:blank."""
        try:
            page = self.browser.page
            if not page:
                return {"status": "error", "error": "No active browser page"}
            preemptor = await self._get_captcha_preemptor()
            result = await preemptor.shutdown_page(page, reason=data.get("reason", "manual"))
            if hasattr(result, '__dict__'):
                result = {k: v for k, v in result.__dict__.items() if not k.startswith('_')}
            elif hasattr(result, '_asdict'):
                result = result._asdict()
            return {"status": "success", "data": result if isinstance(result, dict) else str(result)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── LLM Provider ───────────────────────────────────────
    async def _cmd_llm_complete(self, data: Dict, session) -> Dict:
        """Complete text using LLM with token saving."""
        prompt = data.get("prompt")
        if not prompt:
            return {"status": "error", "error": "Missing 'prompt' parameter"}
        try:
            from src.core.llm_provider import get_llm
            llm = get_llm()
            result = await llm.complete(
                prompt,
                system=data.get("system_prompt", data.get("system", "")),
                max_tokens=data.get("max_tokens", 1000),
                temperature=data.get("temperature", 0.7),
            )
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_llm_classify(self, data: Dict, session) -> Dict:
        """Classify text using LLM with token saving."""
        text = data.get("text")
        categories = data.get("categories", [])
        if not text:
            return {"status": "error", "error": "Missing 'text' parameter"}
        try:
            from src.core.llm_provider import get_llm
            llm = get_llm()
            result = await llm.classify(text, categories)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_llm_extract(self, data: Dict, session) -> Dict:
        """Extract structured data using LLM with token saving."""
        text = data.get("text")
        schema = data.get("schema", {})
        if not text:
            return {"status": "error", "error": "Missing 'text' parameter"}
        try:
            from src.core.llm_provider import get_llm
            llm = get_llm()
            result = await llm.extract(text, schema)
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_llm_summarize(self, data: Dict, session) -> Dict:
        """Summarize text using LLM with token saving."""
        text = data.get("text")
        if not text:
            return {"status": "error", "error": "Missing 'text' parameter"}
        try:
            from src.core.llm_provider import get_llm
            llm = get_llm()
            result = await llm.summarize(
                text,
                max_length=data.get("max_length", 500),
            )
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_llm_provider_set(self, data: Dict, session) -> Dict:
        """Switch LLM provider at runtime."""
        provider = data.get("provider")
        if not provider:
            return {"status": "error", "error": "Missing 'provider' parameter"}
        try:
            from src.core.llm_provider import get_llm
            llm = get_llm()
            llm.set_provider(
                provider_name=provider,
                api_key=data.get("api_key"),
                base_url=data.get("base_url"),
                model=data.get("model"),
            )
            return {"status": "success", "provider": provider, "model": llm.model}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_llm_token_usage(self, data: Dict, session) -> Dict:
        """Get LLM token usage statistics."""
        try:
            from src.core.llm_provider import get_llm
            llm = get_llm()
            return {"status": "success", "data": llm.get_token_usage()}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_llm_cache_clear(self, data: Dict, session) -> Dict:
        """Clear LLM response cache."""
        try:
            from src.core.llm_provider import get_llm
            llm = get_llm()
            llm.cache.clear()
            return {"status": "success", "message": "LLM cache cleared"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── AI Structured Output ────────────────────────────────
    async def _cmd_structured_extract(self, data: Dict, session) -> Dict:
        """Extract and normalize structured data from page or text."""
        try:
            from src.tools.ai_content import AIStructuredOutput
            text = data.get("text")
            url = data.get("url")
            if text:
                from src.tools.ai_content import AIContentExtractor
                extractor = AIContentExtractor()
                content_result = await extractor.extract_from_html(text)
                if content_result.get("status") != "success":
                    return content_result
                ai_content = content_result.get("data")
            elif url:
                nav_result = await self.browser.navigate(url)
                from src.tools.ai_content import AIContentExtractor
                extractor = AIContentExtractor()
                content_result = await extractor.extract_from_browser(self.browser)
                if content_result.get("status") != "success":
                    return content_result
                ai_content = content_result.get("data")
            else:
                from src.tools.ai_content import AIContentExtractor
                extractor = AIContentExtractor()
                content_result = await extractor.extract_from_browser(self.browser)
                if content_result.get("status") != "success":
                    return content_result
                ai_content = content_result.get("data")

            structured = AIStructuredOutput()
            result = structured.process(ai_content)
            return {"status": "success", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_structured_deduplicate(self, data: Dict, session) -> Dict:
        """Deduplicate structured data across pages or within a flat list."""
        try:
            from src.tools.ai_content import CrossPageDeduplicator
            pages = data.get("pages", [])
            flat_data = data.get("data", [])
            if not pages and not flat_data:
                return {"status": "error", "error": "Missing 'pages' or 'data' parameter"}
            # Support flat list input by wrapping in pages
            if not pages and flat_data:
                pages = [flat_data] if not isinstance(flat_data[0], list) else flat_data
            dedup = CrossPageDeduplicator()
            for i, page_data in enumerate(pages):
                dedup.add_page(f"page_{i}", page_data)
            result = dedup.get_deduplicated()
            conflicts = dedup.get_conflicts()
            return {"status": "success", "data": result, "conflicts": conflicts}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_structured_schema(self, data: Dict, session) -> Dict:
        """Generate schema.org structured data from content."""
        try:
            from src.tools.ai_content import AIStructuredOutput
            content = data.get("content", {})
            schema_type = data.get("schema_type", "auto")
            structured = AIStructuredOutput()
            result = structured.generate_schema(content, schema_type=schema_type)
            return {"status": "success", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_structured_format(self, data: Dict, session) -> Dict:
        """Format structured data in various output formats."""
        try:
            from src.tools.ai_content import OutputFormatter
            data_content = data.get("data", {})
            output_format = data.get("format", "json")
            formatter = OutputFormatter()
            if output_format == "json":
                result = formatter.to_json(data_content, compact=not data.get("pretty", True))
            elif output_format == "markdown":
                result = formatter.to_markdown(data_content)
            elif output_format == "csv":
                result = formatter.to_csv(data_content)
            elif output_format == "xml":
                result = formatter.to_xml(data_content)
            elif output_format == "flat_dict":
                result = formatter.to_flat_dict(data_content)
            else:
                return {"status": "error", "error": f"Unknown format: {output_format}"}
            return {"status": "success", "data": result, "format": output_format}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Proxy ─────────────────────────────────────────────

    async def _cmd_set_proxy(self, data: Dict, session) -> Dict:
        url = data.get("proxy_url")
        if not url:
            return {"status": "error", "error": "Missing 'proxy_url'"}
        return await self.browser.set_proxy(url)

    async def _cmd_get_proxy(self, data: Dict, session) -> Dict:
        return await self.browser.get_proxy()

    # ─── TLS Fingerprint HTTP Requests ─────────────────────

    async def _cmd_tls_get(self, data: Dict, session) -> Dict:
        """HTTP GET with real browser TLS fingerprint (no browser needed)."""
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}
        headers = data.get("headers", {})
        profile = data.get("profile")
        timeout = data.get("timeout", 30)
        result = await self.browser.tls_get(url, headers=headers, profile=profile, timeout=timeout)
        if "status" not in result:
            result["status"] = "success" if result.get("status_code", 0) > 0 else "error"
        return result

    async def _cmd_tls_post(self, data: Dict, session) -> Dict:
        """HTTP POST with real browser TLS fingerprint (no browser needed)."""
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}
        headers = data.get("headers", {})
        json_data = data.get("json")
        body = data.get("body")
        profile = data.get("profile")
        timeout = data.get("timeout", 30)
        kwargs = {"headers": headers, "profile": profile, "timeout": timeout}
        if json_data:
            kwargs["json_data"] = json_data
        elif body:
            kwargs["data"] = body.encode() if isinstance(body, str) else body
        result = await self.browser.tls_post(url, **kwargs)
        if "status" not in result:
            result["status"] = "success" if result.get("status_code", 0) > 0 else "error"
        return result

    async def _cmd_tls_stats(self, data: Dict, session) -> Dict:
        """Get TLS proxy and fingerprinting statistics."""
        return {"status": "success", **self.browser.tls_stats}

    # ─── Mobile Emulation ──────────────────────────────────

    async def _cmd_emulate_device(self, data: Dict, session) -> Dict:
        device = data.get("device")
        if not device:
            return {"status": "error", "error": "Missing 'device'"}
        return await self.browser.emulate_device(device)

    async def _cmd_list_devices(self, data: Dict, session) -> Dict:
        return await self.browser.list_devices()

    # ─── Session Save/Restore ──────────────────────────────

    async def _cmd_save_session(self, data: Dict, session) -> Dict:
        return await self.browser.save_session(data.get("name", "default"))

    async def _cmd_restore_session(self, data: Dict, session) -> Dict:
        return await self.browser.restore_session(data.get("name", "default"))

    async def _cmd_list_sessions(self, data: Dict, session) -> Dict:
        return await self.browser.list_sessions()

    async def _cmd_delete_session(self, data: Dict, session) -> Dict:
        name = data.get("name")
        if not name:
            return {"status": "error", "error": "Missing 'name'"}
        return await self.browser.delete_session(name)

    async def _cmd_export_tokens(self, data: Dict, session) -> Dict:
        try:
            tokens = await self.browser.export_tokens()
            return {"status": "success", "tokens": tokens}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_load_tokens(self, data: Dict, session) -> Dict:
        tokens = data.get("tokens")
        if not tokens:
            return {"status": "error", "error": "Missing 'tokens'"}
        try:
            await self.browser.load_tokens(tokens)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Smart Wait ────────────────────────────────────────

    async def _cmd_smart_wait(self, data: Dict, session) -> Dict:
        return await (await self._get_smart_wait()).auto(selector=data.get("selector"), idle_ms=data.get("idle_ms", 500), dom_stable_ms=data.get("dom_stable_ms", 300), timeout_ms=data.get("timeout_ms", 30000), page_id=data.get("page_id", "main"))

    async def _cmd_smart_wait_network(self, data: Dict, session) -> Dict:
        return await (await self._get_smart_wait()).network_idle(idle_ms=data.get("idle_ms", 500), timeout_ms=data.get("timeout_ms", 30000), page_id=data.get("page_id", "main"))

    async def _cmd_smart_wait_dom(self, data: Dict, session) -> Dict:
        return await (await self._get_smart_wait()).dom_stable(stability_ms=data.get("stability_ms", 300), timeout_ms=data.get("timeout_ms", 15000), page_id=data.get("page_id", "main"))

    async def _cmd_smart_wait_element(self, data: Dict, session) -> Dict:
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}
        return await (await self._get_smart_wait()).element_ready(selector=selector, timeout_ms=data.get("timeout_ms", 15000), require_interactable=data.get("require_interactable", True), wait_for_animation=data.get("wait_for_animation", True), page_id=data.get("page_id", "main"))

    async def _cmd_smart_wait_page(self, data: Dict, session) -> Dict:
        return await (await self._get_smart_wait()).page_ready(timeout_ms=data.get("timeout_ms", 30000), require_images=data.get("require_images", True), require_fonts=data.get("require_fonts", True), page_id=data.get("page_id", "main"))

    async def _cmd_smart_wait_js(self, data: Dict, session) -> Dict:
        expr = data.get("expression")
        if not expr:
            return {"status": "error", "error": "Missing 'expression'"}
        return await (await self._get_smart_wait()).js_condition(expression=expr, timeout_ms=data.get("timeout_ms", 10000), poll_ms=data.get("poll_ms"), page_id=data.get("page_id", "main"))

    async def _cmd_smart_wait_compose(self, data: Dict, session) -> Dict:
        conditions = data.get("conditions")
        if not conditions:
            return {"status": "error", "error": "Missing 'conditions'"}
        return await (await self._get_smart_wait()).compose(conditions=conditions, mode=data.get("mode", "all"), timeout_ms=data.get("timeout_ms", 30000), page_id=data.get("page_id", "main"))

    # ─── Auto Heal ─────────────────────────────────────────

    async def _cmd_heal_click(self, data: Dict, session) -> Dict:
        s = data.get("selector")
        if not s:
            return {"status": "error", "error": "Missing 'selector'"}
        return await (await self._get_auto_heal()).click(selector=s, page_id=data.get("page_id", "main"), timeout_ms=data.get("timeout_ms", 5000))

    async def _cmd_heal_fill(self, data: Dict, session) -> Dict:
        s, v = data.get("selector"), data.get("value")
        if not s or v is None:
            return {"status": "error", "error": "Missing 'selector' or 'value'"}
        return await (await self._get_auto_heal()).fill(selector=s, value=v, page_id=data.get("page_id", "main"), timeout_ms=data.get("timeout_ms", 5000))

    async def _cmd_heal_wait(self, data: Dict, session) -> Dict:
        s = data.get("selector")
        if not s:
            return {"status": "error", "error": "Missing 'selector'"}
        return await (await self._get_auto_heal()).wait(selector=s, page_id=data.get("page_id", "main"), timeout_ms=data.get("timeout_ms", 10000))

    async def _cmd_heal_hover(self, data: Dict, session) -> Dict:
        s = data.get("selector")
        if not s:
            return {"status": "error", "error": "Missing 'selector'"}
        return await (await self._get_auto_heal()).hover(selector=s, page_id=data.get("page_id", "main"), timeout_ms=data.get("timeout_ms", 5000))

    async def _cmd_heal_double_click(self, data: Dict, session) -> Dict:
        s = data.get("selector")
        if not s:
            return {"status": "error", "error": "Missing 'selector'"}
        return await (await self._get_auto_heal()).double_click(selector=s, page_id=data.get("page_id", "main"), timeout_ms=data.get("timeout_ms", 5000))

    async def _cmd_heal_selector(self, data: Dict, session) -> Dict:
        s = data.get("selector")
        if not s:
            return {"status": "error", "error": "Missing 'selector'"}
        return await (await self._get_auto_heal()).heal_selector(broken_selector=s, page_id=data.get("page_id", "main"))

    async def _cmd_heal_fingerprint(self, data: Dict, session) -> Dict:
        s = data.get("selector")
        if not s:
            return {"status": "error", "error": "Missing 'selector'"}
        return await (await self._get_auto_heal()).fingerprint(selector=s, page_id=data.get("page_id", "main"))

    async def _cmd_heal_fingerprint_page(self, data: Dict, session) -> Dict:
        return await (await self._get_auto_heal()).fingerprint_page(page_id=data.get("page_id", "main"))

    async def _cmd_heal_stats(self, data: Dict, session) -> Dict:
        return (await self._get_auto_heal()).get_stats()

    async def _cmd_heal_clear(self, data: Dict, session) -> Dict:
        (await self._get_auto_heal()).clear_cache()
        return {"status": "success", "message": "Healing caches cleared"}

    # ─── Auto Retry ────────────────────────────────────────

    async def _cmd_retry_execute(self, data: Dict, session) -> Dict:
        command = data.get("inner_command") or data.get("command_payload", {}).get("command")
        if not command:
            return {"status": "error", "error": "Missing 'inner_command'"}
        payload = data.get("command_payload", data)
        payload["command"] = command
        async def action():
            return await self._execute_command(command, payload, session)
        return await (await self._get_auto_retry()).execute(operation=command, action=action, params=payload, deduplicate=data.get("deduplicate", False))

    async def _cmd_retry_navigate(self, data: Dict, session) -> Dict:
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}
        return await (await self._get_auto_retry()).navigate(url=url, page_id=data.get("page_id", "main"), wait_until=data.get("wait_until", "domcontentloaded"))

    async def _cmd_retry_click(self, data: Dict, session) -> Dict:
        s = data.get("selector")
        if not s:
            return {"status": "error", "error": "Missing 'selector'"}
        return await (await self._get_auto_retry()).click(selector=s, page_id=data.get("page_id", "main"))

    async def _cmd_retry_fill(self, data: Dict, session) -> Dict:
        s, v = data.get("selector"), data.get("value")
        if not s or v is None:
            return {"status": "error", "error": "Missing 'selector' or 'value'"}
        return await (await self._get_auto_retry()).fill(selector=s, value=v, page_id=data.get("page_id", "main"))

    async def _cmd_retry_api_call(self, data: Dict, session) -> Dict:
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}
        return await (await self._get_auto_retry()).api_call(url=url, method=data.get("method", "GET"), headers=data.get("headers"), body=data.get("body"))

    async def _cmd_retry_stats(self, data: Dict, session) -> Dict:
        return (await self._get_auto_retry()).get_stats()

    async def _cmd_retry_health(self, data: Dict, session) -> Dict:
        return {"status": "success", **(await self._get_auto_retry()).get_health()}

    async def _cmd_retry_circuit_breakers(self, data: Dict, session) -> Dict:
        return {"status": "success", "circuit_breakers": (await self._get_auto_retry()).get_circuit_breakers()}

    async def _cmd_retry_reset_circuit(self, data: Dict, session) -> Dict:
        op = data.get("operation")
        if not op:
            return {"status": "error", "error": "Missing 'operation'"}
        return await (await self._get_auto_retry()).reset_circuit_breaker(op)

    async def _cmd_retry_reset_all_circuits(self, data: Dict, session) -> Dict:
        return await (await self._get_auto_retry()).reset_all_circuit_breakers()

    # ─── Session Recording ─────────────────────────────────

    async def _cmd_record_start(self, data: Dict, session) -> Dict:
        return await (await self._get_recorder()).start(name=data.get("name"), screenshot_interval_ms=data.get("screenshot_interval_ms", 2000), screenshot_on_event=data.get("screenshot_on_event", True), capture_network=data.get("capture_network", True), capture_console=data.get("capture_console", True), capture_dom=data.get("capture_dom", True), capture_scroll=data.get("capture_scroll", True), capture_cookies=data.get("capture_cookies", True), tags=data.get("tags"), page_id=data.get("page_id", "main"))

    async def _cmd_record_stop(self, data: Dict, session) -> Dict:
        return await (await self._get_recorder()).stop(save=data.get("save", True))

    async def _cmd_record_pause(self, data: Dict, session) -> Dict:
        return await (await self._get_recorder()).pause()

    async def _cmd_record_resume(self, data: Dict, session) -> Dict:
        return await (await self._get_recorder()).resume()

    async def _cmd_record_annotate(self, data: Dict, session) -> Dict:
        text = data.get("text")
        if not text:
            return {"status": "error", "error": "Missing 'text'"}
        return await (await self._get_recorder()).annotate(text=text, category=data.get("category", "note"), page_id=data.get("page_id", "main"))

    async def _cmd_record_status(self, data: Dict, session) -> Dict:
        rec = await self._get_recorder()
        if not rec.is_recording():
            return {"status": "not_recording"}
        r = rec.get_recording()
        return {"status": "recording", "recording_id": r.recording_id if r else None, "name": r.name if r else None, "event_count": len(r.events) if r else 0}

    async def _cmd_record_list(self, data: Dict, session) -> Dict:
        from src.tools.session_recording import SessionRecorder
        return {"status": "success", "recordings": SessionRecorder.list_recordings()}

    async def _cmd_record_delete(self, data: Dict, session) -> Dict:
        rid = data.get("recording_id")
        if not rid:
            return {"status": "error", "error": "Missing 'recording_id'"}
        from src.tools.session_recording import SessionRecorder
        return {"status": "success", "deleted": SessionRecorder.delete_recording(rid)}

    # ─── Replay ────────────────────────────────────────────

    async def _cmd_replay_load(self, data: Dict, session) -> Dict:
        rid = data.get("recording_id")
        if not rid:
            return {"status": "error", "error": "Missing 'recording_id'"}
        return await (await self._get_replay()).load(rid)

    async def _cmd_replay_play(self, data: Dict, session) -> Dict:
        return await (await self._get_replay()).play(speed=data.get("speed", 1.0), from_event=data.get("from_event", 0), to_event=data.get("to_event"), skip_types=data.get("skip_types"), verify_screenshots=data.get("verify_screenshots", False))

    async def _cmd_replay_stop(self, data: Dict, session) -> Dict:
        return await (await self._get_replay()).stop()

    async def _cmd_replay_pause(self, data: Dict, session) -> Dict:
        return await (await self._get_replay()).pause()

    async def _cmd_replay_resume(self, data: Dict, session) -> Dict:
        return await (await self._get_replay()).resume()

    async def _cmd_replay_step(self, data: Dict, session) -> Dict:
        return await (await self._get_replay()).step()

    async def _cmd_replay_jump(self, data: Dict, session) -> Dict:
        return await (await self._get_replay()).jump_to(event_index=data.get("event_index"), elapsed_ms=data.get("elapsed_ms"))

    async def _cmd_replay_position(self, data: Dict, session) -> Dict:
        return await (await self._get_replay()).get_position()

    async def _cmd_replay_events(self, data: Dict, session) -> Dict:
        return await (await self._get_replay()).get_event_list(offset=data.get("offset", 0), limit=data.get("limit", 50), event_type=data.get("event_type"))

    async def _cmd_replay_export_workflow(self, data: Dict, session) -> Dict:
        return await (await self._get_replay()).export_as_workflow(include_navigations=data.get("include_navigations", True))

    async def _cmd_analyze(self, data: Dict, session) -> Dict:
        rid = data.get("recording_id")
        if not rid:
            return {"status": "error", "error": "Missing 'recording_id'"}
        return await (await self._get_analyzer()).analyze(rid)

    async def _cmd_analyze_search(self, data: Dict, session) -> Dict:
        rid = data.get("recording_id")
        if not rid:
            return {"status": "error", "error": "Missing 'recording_id'"}
        return await (await self._get_analyzer()).search(rid, event_type=data.get("event_type"), query=data.get("query"), from_ms=data.get("from_ms"), to_ms=data.get("to_ms"), limit=data.get("limit", 100))

    # ─── Multi-Agent Hub ───────────────────────────────────

    async def _cmd_hub_register(self, data: Dict, session) -> Dict:
        return await (await self._get_agent_hub()).register_agent(agent_id=data.get("agent_id"), name=data.get("name"), role=data.get("role", "operator"), capabilities=data.get("capabilities"), metadata=data.get("metadata"))

    async def _cmd_hub_unregister(self, data: Dict, session) -> Dict:
        aid = data.get("agent_id")
        if not aid:
            return {"status": "error", "error": "Missing 'agent_id'"}
        return await (await self._get_agent_hub()).unregister_agent(aid)

    async def _cmd_hub_heartbeat(self, data: Dict, session) -> Dict:
        aid = data.get("agent_id")
        if not aid:
            return {"status": "error", "error": "Missing 'agent_id'"}
        return await (await self._get_agent_hub()).heartbeat(aid)

    async def _cmd_hub_status(self, data: Dict, session) -> Dict:
        return (await self._get_agent_hub()).get_status()

    async def _cmd_hub_agents(self, data: Dict, session) -> Dict:
        return (await self._get_agent_hub()).get_agents(alive_only=data.get("alive_only", True))

    async def _cmd_hub_lock(self, data: Dict, session) -> Dict:
        aid, res = data.get("agent_id"), data.get("resource")
        if not aid or not res:
            return {"status": "error", "error": "Missing 'agent_id' or 'resource'"}
        return await (await self._get_agent_hub()).acquire_lock(agent_id=aid, resource=res, lock_type=data.get("lock_type", "exclusive"), ttl_seconds=data.get("ttl_seconds"), timeout_ms=data.get("timeout_ms", 5000))

    async def _cmd_hub_unlock(self, data: Dict, session) -> Dict:
        aid, lid = data.get("agent_id"), data.get("lock_id")
        if not aid or not lid:
            return {"status": "error", "error": "Missing 'agent_id' or 'lock_id'"}
        return await (await self._get_agent_hub()).release_lock(aid, lid)

    async def _cmd_hub_locks(self, data: Dict, session) -> Dict:
        return (await self._get_agent_hub()).get_locks(resource=data.get("resource"), agent_id=data.get("agent_id"))

    async def _cmd_hub_task_create(self, data: Dict, session) -> Dict:
        title = data.get("title")
        if not title:
            return {"status": "error", "error": "Missing 'title'"}
        return await (await self._get_agent_hub()).create_task(title=title, description=data.get("description", ""), assigned_to=data.get("assigned_to"), assigned_by=data.get("assigned_by"), priority=data.get("priority", 0), tags=data.get("tags"), dependencies=data.get("dependencies"), max_retries=data.get("max_retries", 0))

    async def _cmd_hub_task_claim(self, data: Dict, session) -> Dict:
        aid = data.get("agent_id")
        if not aid:
            return {"status": "error", "error": "Missing 'agent_id'"}
        return await (await self._get_agent_hub()).claim_task(aid, task_id=data.get("task_id"), tags=data.get("tags"))

    async def _cmd_hub_task_start(self, data: Dict, session) -> Dict:
        aid, tid = data.get("agent_id"), data.get("task_id")
        if not aid or not tid:
            return {"status": "error", "error": "Missing 'agent_id' or 'task_id'"}
        return await (await self._get_agent_hub()).start_task(aid, tid)

    async def _cmd_hub_task_complete(self, data: Dict, session) -> Dict:
        aid, tid = data.get("agent_id"), data.get("task_id")
        if not aid or not tid:
            return {"status": "error", "error": "Missing 'agent_id' or 'task_id'"}
        return await (await self._get_agent_hub()).complete_task(aid, tid, result=data.get("result"))

    async def _cmd_hub_task_fail(self, data: Dict, session) -> Dict:
        aid, tid = data.get("agent_id"), data.get("task_id")
        if not aid or not tid:
            return {"status": "error", "error": "Missing 'agent_id' or 'task_id'"}
        return await (await self._get_agent_hub()).fail_task(aid, tid, error=data.get("error", ""))

    async def _cmd_hub_task_cancel(self, data: Dict, session) -> Dict:
        tid = data.get("task_id")
        if not tid:
            return {"status": "error", "error": "Missing 'task_id'"}
        return await (await self._get_agent_hub()).cancel_task(tid, cancelled_by=data.get("cancelled_by"))

    async def _cmd_hub_tasks(self, data: Dict, session) -> Dict:
        return await (await self._get_agent_hub()).get_tasks(status=data.get("status"), assigned_to=data.get("assigned_to"), tags=data.get("tags"), limit=data.get("limit", 50))

    async def _cmd_hub_broadcast(self, data: Dict, session) -> Dict:
        sid = data.get("sender_id") or data.get("agent_id")
        topic = data.get("topic")
        if not sid or not topic:
            return {"status": "error", "error": "Missing 'agent_id'/'sender_id' or 'topic'"}
        return await (await self._get_agent_hub()).broadcast(sender_id=sid, topic=topic, payload=data.get("payload", data.get("message", {})), ttl_seconds=data.get("ttl_seconds"))

    async def _cmd_hub_events(self, data: Dict, session) -> Dict:
        aid = data.get("agent_id")
        if not aid:
            return {"status": "error", "error": "Missing 'agent_id'"}
        return (await self._get_agent_hub()).get_events(agent_id=aid, topic=data.get("topic"), since_seconds=data.get("since_seconds"), limit=data.get("limit", 50))

    async def _cmd_hub_memory_set(self, data: Dict, session) -> Dict:
        aid, key = data.get("agent_id"), data.get("key")
        if not aid or not key:
            return {"status": "error", "error": "Missing 'agent_id' or 'key'"}
        return await (await self._get_agent_hub()).memory_set(agent_id=aid, key=key, value=data.get("value"), ttl_seconds=data.get("ttl_seconds", 0), access=data.get("access", "shared"))

    async def _cmd_hub_memory_get(self, data: Dict, session) -> Dict:
        aid, key = data.get("agent_id"), data.get("key")
        if not aid or not key:
            return {"status": "error", "error": "Missing 'agent_id' or 'key'"}
        return await (await self._get_agent_hub()).memory_get(aid, key)

    async def _cmd_hub_memory_delete(self, data: Dict, session) -> Dict:
        aid, key = data.get("agent_id"), data.get("key")
        if not aid or not key:
            return {"status": "error", "error": "Missing 'agent_id' or 'key'"}
        return await (await self._get_agent_hub()).memory_delete(aid, key)

    async def _cmd_hub_memory_list(self, data: Dict, session) -> Dict:
        return await (await self._get_agent_hub()).memory_list(prefix=data.get("prefix"), agent_id=data.get("agent_id"))

    async def _cmd_hub_handoff(self, data: Dict, session) -> Dict:
        fid, tid = data.get("from_agent_id"), data.get("to_agent_id")
        if not fid or not tid:
            return {"status": "error", "error": "Missing 'from_agent_id' or 'to_agent_id'"}
        return await (await self._get_agent_hub()).handoff(from_agent_id=fid, to_agent_id=tid, resource=data.get("resource", "page:main"), context=data.get("context"))

    async def _cmd_hub_audit(self, data: Dict, session) -> Dict:
        return await (await self._get_agent_hub()).get_audit(agent_id=data.get("agent_id"), action=data.get("action"), since_seconds=data.get("since_seconds"), limit=data.get("limit", 100))

    # ─── Proxy Rotation ────────────────────────────────────

    async def _cmd_proxy_add(self, data: Dict, session) -> Dict:
        url = data.get("url")
        if not url:
            return {"status": "error", "error": "Missing 'url'"}
        return await (await self._get_proxy_manager()).add_proxy(url=url, country=data.get("country", ""), region=data.get("region", ""), tags=data.get("tags", []), weight=data.get("weight", 1.0), max_requests_per_minute=data.get("max_requests_per_minute", 0))

    async def _cmd_proxy_remove(self, data: Dict, session) -> Dict:
        pid = data.get("proxy_id")
        if not pid:
            return {"status": "error", "error": "Missing 'proxy_id'"}
        return await (await self._get_proxy_manager()).remove_proxy(pid)

    async def _cmd_proxy_load_file(self, data: Dict, session) -> Dict:
        fp = data.get("filepath")
        if not fp:
            return {"status": "error", "error": "Missing 'filepath'"}
        return await (await self._get_proxy_manager()).load_proxies(fp, proxy_type=data.get("proxy_type", "http"))

    async def _cmd_proxy_load_api(self, data: Dict, session) -> Dict:
        api_url = data.get("api_url")
        if not api_url:
            return {"status": "error", "error": "Missing 'api_url'"}
        return await (await self._get_proxy_manager()).load_from_api(api_url, api_key=data.get("api_key"))

    async def _cmd_proxy_get(self, data: Dict, session) -> Dict:
        return await (await self._get_proxy_manager()).get_proxy(domain=data.get("domain"), session_id=data.get("session_id"), country=data.get("country"), tags=data.get("tags"), with_failover=data.get("with_failover", True))

    async def _cmd_proxy_record(self, data: Dict, session) -> Dict:
        pid = data.get("proxy_id")
        if not pid:
            return {"status": "error", "error": "Missing 'proxy_id'"}
        return await (await self._get_proxy_manager()).record_result(proxy_id=pid, success=data.get("success", True), latency_ms=data.get("latency_ms", 0), status_code=data.get("status_code", 0), error=data.get("error", ""))

    async def _cmd_proxy_check(self, data: Dict, session) -> Dict:
        pid = data.get("proxy_id")
        if not pid:
            return {"status": "error", "error": "Missing 'proxy_id'"}
        return await (await self._get_proxy_manager()).check_proxy(pid)

    async def _cmd_proxy_check_all(self, data: Dict, session) -> Dict:
        return await (await self._get_proxy_manager()).check_all()

    async def _cmd_proxy_list(self, data: Dict, session) -> Dict:
        return await (await self._get_proxy_manager()).list_proxies(status=data.get("status"), country=data.get("country"))

    async def _cmd_proxy_enable(self, data: Dict, session) -> Dict:
        pid = data.get("proxy_id")
        if not pid:
            return {"status": "error", "error": "Missing 'proxy_id'"}
        return await (await self._get_proxy_manager()).enable_proxy(pid)

    async def _cmd_proxy_disable(self, data: Dict, session) -> Dict:
        pid = data.get("proxy_id")
        if not pid:
            return {"status": "error", "error": "Missing 'proxy_id'"}
        return await (await self._get_proxy_manager()).disable_proxy(pid)

    async def _cmd_proxy_strategy(self, data: Dict, session) -> Dict:
        strategy = data.get("strategy")
        if not strategy:
            return {"status": "error", "error": "Missing 'strategy'"}
        return await (await self._get_proxy_manager()).set_strategy(strategy)

    async def _cmd_proxy_stats(self, data: Dict, session) -> Dict:
        return (await self._get_proxy_manager()).get_stats()

    async def _cmd_proxy_rotate(self, data: Dict, session) -> Dict:
        """Rotate to the next proxy in the pool."""
        try:
            manager = await self._get_proxy_manager()
            proxy = await manager.get_proxy()
            if proxy:
                return {"status": "success", "proxy": proxy.to_dict()}
            return {"status": "error", "error": "No proxy available"}
        except Exception as e:
            logger.error(f"Proxy rotate error: {e}")
            return {"status": "error", "error": self._sanitize_error_message(str(e))}

    async def _cmd_proxy_save(self, data: Dict, session) -> Dict:
        return await (await self._get_proxy_manager()).save(filename=data.get("filename", "proxies.json"))

    async def _cmd_proxy_load(self, data: Dict, session) -> Dict:
        return await (await self._get_proxy_manager()).load(filename=data.get("filename", "proxies.json"))

    # ─── Adaptive Scraper Commands ───────────────────────────

    async def _cmd_adaptive_find(self, data: Dict, session) -> Dict:
        """Find an element adaptively — survives page structure changes.

        First tries normal selector. If it fails, loads stored fingerprint
        and uses similarity scoring to relocate the element.

        Params:
            selector: CSS/XPath selector (required)
            identifier: Custom name for this element (optional, defaults to selector)
            page_id: Browser tab ID (default: "main")
            auto_save: Save fingerprints automatically (default: true)
            threshold: Minimum similarity score 0-100 (default: 40)
        """
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}
        scraper = await self._get_adaptive_scraper()
        return await scraper.find_element(
            selector=selector,
            identifier=data.get("identifier"),
            page_id=data.get("page_id", "main"),
            auto_save=data.get("auto_save", True),
            threshold=data.get("threshold", 40.0),
        )

    async def _cmd_adaptive_save(self, data: Dict, session) -> Dict:
        """Save an element's fingerprint for future adaptive relocation.

        Params:
            selector: CSS/XPath selector (required)
            identifier: Name to save under (required)
            page_id: Browser tab ID (default: "main")
        """
        selector = data.get("selector")
        identifier = data.get("identifier")
        if not selector or not identifier:
            return {"status": "error", "error": "Missing 'selector' or 'identifier'"}
        scraper = await self._get_adaptive_scraper()
        return await scraper.save_element(
            selector=selector,
            identifier=identifier,
            page_id=data.get("page_id", "main"),
        )

    async def _cmd_adaptive_stats(self, data: Dict, session) -> Dict:
        """Get adaptive scraper statistics — domains, fingerprints, storage."""
        scraper = await self._get_adaptive_scraper()
        return {"status": "success", **scraper.get_stats()}

    async def _cmd_adaptive_cleanup(self, data: Dict, session) -> Dict:
        """Clean up expired fingerprints older than max_age_days.

        Params:
            max_age_days: Max age in days (default: 30)
        """
        scraper = await self._get_adaptive_scraper()
        return scraper.cleanup(max_age_days=data.get("max_age_days", 30))

    # ─── DOM Snapshot (Token Saving) ─────────────────────────

    async def _cmd_snapshot(self, data: Dict, session) -> Dict:
        """Get a compact accessibility tree snapshot of the page.

        Instead of raw HTML (50,000+ chars), returns a semantic tree
        (2,000-5,000 chars) that captures page structure. Use @eN refs
        to interact with elements in subsequent commands.

        Params:
            compact: Remove empty structural elements (default: true)
            depth: Limit tree depth (optional)
            urls: Include href URLs for links (default: false)
        """
        from src.tools.dom_snapshot import SnapshotOptions, take_snapshot, RefMap, estimate_token_savings
        page = self.browser.page
        if not page:
            return {"status": "error", "error": "No active page"}

        ref_map = RefMap()
        options = SnapshotOptions(
            compact=data.get("compact", True),
            depth=data.get("depth"),
            urls=data.get("urls", False),
        )

        try:
            snapshot_text = await take_snapshot(page, options, ref_map)
            html_len = len(await page.content())
            savings = estimate_token_savings(html_len, len(snapshot_text))

            # Store ref_map in session for @eN ref resolution in click/fill/type
            if session:
                session.ref_map = ref_map

            return {
                "status": "success",
                "snapshot": snapshot_text,
                "refs": ref_map.to_dict(),
                "ref_count": len(ref_map._entries),
                "token_savings": savings,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_snapshot_interactive(self, data: Dict, session) -> Dict:
        """Get interactive elements only — buttons, links, inputs.

        Best for LLM consumption: minimal tokens, all clickable things.
        Returns @eN refs that can be used in click/fill/type commands.

        Params:
            compact: Remove empty structural elements (default: true)
            depth: Limit tree depth (optional)
        """
        from src.tools.dom_snapshot import snapshot_interactive, estimate_token_savings
        page = self.browser.page
        if not page:
            return {"status": "error", "error": "No active page"}

        try:
            snapshot_text, ref_map = await snapshot_interactive(
                page,
                compact=data.get("compact", True),
                depth=data.get("depth"),
            )
            html_len = len(await page.content())
            savings = estimate_token_savings(html_len, len(snapshot_text))

            # Store ref_map in session for @eN ref resolution
            if session:
                session.ref_map = ref_map

            return {
                "status": "success",
                "snapshot": snapshot_text,
                "refs": ref_map.to_dict(),
                "ref_count": len(ref_map._entries),
                "token_savings": savings,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _cmd_snapshot_selector(self, data: Dict, session) -> Dict:
        """Get snapshot scoped to a CSS selector.

        Params:
            selector: CSS selector to scope to (required)
            compact: Remove empty structural elements (default: true)
        """
        from src.tools.dom_snapshot import snapshot_selector, estimate_token_savings
        selector = data.get("selector")
        if not selector:
            return {"status": "error", "error": "Missing 'selector'"}

        page = self.browser.page
        if not page:
            return {"status": "error", "error": "No active page"}

        try:
            snapshot_text, ref_map = await snapshot_selector(
                page, selector,
                compact=data.get("compact", True),
            )
            html_len = len(await page.content())
            savings = estimate_token_savings(html_len, len(snapshot_text))

            # Store ref_map in session for @eN ref resolution
            if session:
                session.ref_map = ref_map

            return {
                "status": "success",
                "snapshot": snapshot_text,
                "refs": ref_map.to_dict(),
                "ref_count": len(ref_map._entries),
                "token_savings": savings,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Login Handoff Commands ───────────────────────────────

    async def _cmd_detect_login_page(self, data: Dict, session) -> Dict:
        """Detect if the current page is a login/signup page.

        Uses both URL patterns and DOM analysis for maximum accuracy.
        Returns is_login_page, page_type, confidence, url, domain.
        """
        page_id = data.get("page_id", "main")
        handoff = await self._get_login_handoff()
        result = await handoff.detect_login_page(page_id=page_id)
        return {"status": "success", **result}

    async def _cmd_login_handoff_start(self, data: Dict, session) -> Dict:
        """Start a login handoff — pause AI, give control to user.

        When the AI agent encounters a login page, this command pauses
        automation and waits for the human user to complete login.
        The user's credentials never pass through the AI — they type
        directly into the real website in the browser.

        Params:
            url: (optional) Login page URL (auto-detected if empty)
            page_id: Browser tab ID (default: "main")
            timeout_seconds: How long to wait for user (default: 300)
        """
        handoff = await self._get_login_handoff()
        return await handoff.start_handoff(
            url=data.get("url", ""),
            page_id=data.get("page_id", "main"),
            user_id=data.get("user_id", ""),
            session_id=session.session_id if session else "",
            timeout_seconds=data.get("timeout_seconds", 300),
            auto_detected=False,
        )

    async def _cmd_login_handoff_status(self, data: Dict, session) -> Dict:
        """Get the status of a login handoff session.

        Params:
            handoff_id: The handoff session ID
        """
        handoff_id = data.get("handoff_id", "")
        if not handoff_id:
            return {"status": "error", "error": "Missing 'handoff_id'"}
        handoff = await self._get_login_handoff()
        return await handoff.get_handoff_status(handoff_id)

    async def _cmd_login_handoff_complete(self, data: Dict, session) -> Dict:
        """Mark a login handoff as completed by the user.

        Called when the user has finished logging in. This saves
        the session cookies and returns control to the AI agent.

        Params:
            handoff_id: The handoff session ID
        """
        handoff_id = data.get("handoff_id", "")
        if not handoff_id:
            return {"status": "error", "error": "Missing 'handoff_id'"}
        handoff = await self._get_login_handoff()
        return await handoff.complete_handoff(
            handoff_id=handoff_id,
            user_id=data.get("user_id", ""),
        )

    async def _cmd_login_handoff_cancel(self, data: Dict, session) -> Dict:
        """Cancel an active login handoff session.

        Params:
            handoff_id: The handoff session ID
            reason: Optional reason for cancellation
        """
        handoff_id = data.get("handoff_id", "")
        if not handoff_id:
            return {"status": "error", "error": "Missing 'handoff_id'"}
        handoff = await self._get_login_handoff()
        return await handoff.cancel_handoff(
            handoff_id=handoff_id,
            reason=data.get("reason", ""),
        )

    async def _cmd_login_handoff_list(self, data: Dict, session) -> Dict:
        """List all handoff sessions, optionally filtered by state.

        Params:
            state: (optional) Filter by state (e.g. "waiting_for_user")
            user_id: (optional) Filter by user ID
        """
        handoff = await self._get_login_handoff()
        return await handoff.list_handoffs(
            state_filter=data.get("state"),
            user_id=data.get("user_id"),
        )

    async def _cmd_login_handoff_history(self, data: Dict, session) -> Dict:
        """Get completed handoff history.

        Params:
            limit: Maximum entries to return (default: 50)
        """
        handoff = await self._get_login_handoff()
        return await handoff.get_handoff_history(limit=data.get("limit", 50))

    async def _cmd_login_handoff_stats(self, data: Dict, session) -> Dict:
        """Get handoff statistics (success rate, per-domain stats)."""
        handoff = await self._get_login_handoff()
        return {"status": "success", **handoff.get_stats()}

    # ─── Health Check (command-level) ─────────────────────────

    async def _cmd_health(self, data: Dict, session) -> Dict:
        """Deep health check — server, browser, database, redis, sessions."""
        checks = {"server": "healthy"}
        uptime = time.time() - self._start_time

        # Database health
        try:
            from src.infra.database import get_db
            db = get_db()
            db_health = await db.health_check()
            checks["database"] = db_health["status"]
        except Exception:
            checks["database"] = "not_configured"

        # Redis health
        if self.redis:
            redis_health = await self.redis.health_check()
            checks["redis"] = redis_health["status"]
            checks["redis_mode"] = redis_health.get("mode", "unknown")
        else:
            checks["redis"] = "not_configured"

        # Browser health
        if self.browser.browser:
            try:
                if self.browser.page:
                    await self.browser.page.title()
                checks["browser"] = "healthy"
            except Exception as e:
                checks["browser"] = f"degraded: {e}"
        else:
            checks["browser"] = "not_running"

        # Sessions
        active_sessions = len(self.session_manager._sessions) if hasattr(self.session_manager, '_sessions') else 0
        ws_clients = len(self._ws_clients)

        overall = "healthy" if all(
            v in ("healthy", "not_configured") for v in checks.values()
        ) else "degraded"

        return {
            "status": overall,
            "version": AGENT_OS_VERSION,
            "uptime_seconds": round(uptime, 1),
            "checks": checks,
            "sessions": {
                "active": active_sessions,
                "ws_clients": ws_clients,
            },
            "browser_engine": "patchright",
            "timestamp": time.time(),
        }

    # ─── Login Handoff REST API Handlers ──────────────────────

    async def _handle_handoff_start(self, request: web.Request) -> web.Response:
        """POST /handoff/start — Start a login handoff session.

        Body: {"page_id": "main", "timeout_seconds": 300, "url": ""}
        """
        try:
            data = request.get("parsed_body") or await request.json()
        except Exception:
            return web.json_response(
                {"status": "error", "error": "Invalid JSON body"},
                status=400, headers=self._get_cors_headers(),
            )

        auth_context = request.get("auth_context")
        user_id = auth_context.get("user_id", "") if auth_context else ""
        handoff = await self._get_login_handoff()
        result = await handoff.start_handoff(
            url=data.get("url", ""),
            page_id=data.get("page_id", "main"),
            user_id=user_id,
            session_id="",
            timeout_seconds=data.get("timeout_seconds", 300),
            auto_detected=False,
        )
        status_code = 200 if result.get("status") == "success" else 400
        return web.json_response(result, status=status_code, headers=self._get_cors_headers())

    async def _handle_handoff_status(self, request: web.Request) -> web.Response:
        """GET /handoff/{handoff_id} — Get handoff session status."""
        handoff_id = request.match_info.get("handoff_id", "")
        if not handoff_id:
            return web.json_response(
                {"status": "error", "error": "Missing handoff_id"},
                status=400, headers=self._get_cors_headers(),
            )
        handoff = await self._get_login_handoff()
        result = await handoff.get_handoff_status(handoff_id)
        return web.json_response(result, headers=self._get_cors_headers())

    async def _handle_handoff_complete(self, request: web.Request) -> web.Response:
        """POST /handoff/{handoff_id}/complete — Mark handoff as completed."""
        handoff_id = request.match_info.get("handoff_id", "")
        if not handoff_id:
            return web.json_response(
                {"status": "error", "error": "Missing handoff_id"},
                status=400, headers=self._get_cors_headers(),
            )
        auth_context = request.get("auth_context")
        user_id = auth_context.get("user_id", "") if auth_context else ""
        handoff = await self._get_login_handoff()
        result = await handoff.complete_handoff(handoff_id, user_id=user_id)
        return web.json_response(result, headers=self._get_cors_headers())

    async def _handle_handoff_cancel(self, request: web.Request) -> web.Response:
        """POST /handoff/{handoff_id}/cancel — Cancel a handoff session."""
        handoff_id = request.match_info.get("handoff_id", "")
        if not handoff_id:
            return web.json_response(
                {"status": "error", "error": "Missing handoff_id"},
                status=400, headers=self._get_cors_headers(),
            )
        try:
            data = request.get("parsed_body") or await request.json()
        except Exception:
            data = {}
        handoff = await self._get_login_handoff()
        result = await handoff.cancel_handoff(handoff_id, reason=data.get("reason", ""))
        return web.json_response(result, headers=self._get_cors_headers())

    async def _handle_handoff_list(self, request: web.Request) -> web.Response:
        """GET /handoff — List all handoff sessions."""
        state_filter = request.query.get("state")
        user_id = request.query.get("user_id")
        handoff = await self._get_login_handoff()
        result = await handoff.list_handoffs(state_filter=state_filter, user_id=user_id)
        return web.json_response(result, headers=self._get_cors_headers())

    async def _handle_handoff_history(self, request: web.Request) -> web.Response:
        """GET /handoff/history — Get completed handoff history."""
        limit = int(request.query.get("limit", "50"))
        handoff = await self._get_login_handoff()
        result = await handoff.get_handoff_history(limit=limit)
        return web.json_response(result, headers=self._get_cors_headers())

    async def _handle_handoff_stats(self, request: web.Request) -> web.Response:
        """GET /handoff/stats — Get handoff statistics."""
        handoff = await self._get_login_handoff()
        return web.json_response(
            {"status": "success", **handoff.get_stats()},
            headers=self._get_cors_headers(),
        )

    async def _handle_handoff_detect(self, request: web.Request) -> web.Response:
        """POST /handoff/detect — Detect if current page is a login page."""
        # Auth check — consistent with other handoff endpoints
        auth_context = request.get("auth_context")
        if not auth_context:
            return web.json_response(
                {"status": "error", "error": "Authentication required"},
                status=401, headers=self._get_cors_headers(),
            )
        try:
            data = request.get("parsed_body") or await request.json()
        except Exception:
            data = {}
        handoff = await self._get_login_handoff()
        result = await handoff.detect_login_page(page_id=data.get("page_id", "main"))
        return web.json_response(
            {"status": "success", **result},
            headers=self._get_cors_headers(),
        )

    # ─── Command Definitions (for /commands endpoint) ──────

    def _get_command_definitions(self) -> dict:
        """Return command definitions. Kept as dict for /commands endpoint."""
        return {
            "navigate": {"params": {"url": "string"}, "description": "Navigate to a URL (auto-selects HTTP or browser)"},
            "fetch": {"params": {"url": "string"}, "description": "Fetch URL via TLS-spoofed HTTP (no browser, faster)"},
            "smart-navigate": {"params": {"url": "string", "prefer_browser": "bool", "max_retries": "int"}, "description": "Smart navigate with automatic fallback and retry"},
            "nav-stats": {"params": {}, "description": "Get SmartNavigator strategy stats and per-domain success rates"},
            "click": {"params": {"selector": "string"}, "description": "Click an element"},
            "type": {"params": {"text": "string"}, "description": "Type text into focused element"},
            "screenshot": {"params": {"full_page": "bool"}, "description": "Take a screenshot"},
            "get-content": {"params": {}, "description": "Get page HTML and text"},
            "get-dom": {"params": {}, "description": "Get structured DOM snapshot"},
            "fill-form": {"params": {"fields": "dict"}, "description": "Fill form fields"},
            "scroll": {"params": {"direction": "up|down", "amount": "int"}, "description": "Scroll the page"},
            "smart-click": {"params": {"text": "string"}, "description": "Click element by visible text"},
            "workflow": {"params": {"steps": "list"}, "description": "Execute multi-step workflow"},
            "tabs": {"params": {"action": "list|new|close|switch"}, "description": "Manage browser tabs"},
            "adaptive-find": {"params": {"selector": "string", "identifier": "string", "threshold": "int"}, "description": "Find element adaptively — survives page structure changes"},
            "adaptive-save": {"params": {"selector": "string", "identifier": "string"}, "description": "Save element fingerprint for future adaptive relocation"},
            "adaptive-stats": {"params": {}, "description": "Get adaptive scraper statistics"},
            "adaptive-cleanup": {"params": {"max_age_days": "int"}, "description": "Clean up expired fingerprints"},
            "detect-login-page": {"params": {"page_id": "string"}, "description": "Detect if current page is a login/signup page"},
            "login-handoff-start": {"params": {"url": "string", "page_id": "string", "timeout_seconds": "int"}, "description": "Start login handoff — pause AI, give browser control to user for login"},
            "login-handoff-status": {"params": {"handoff_id": "string"}, "description": "Get status of a login handoff session"},
            "login-handoff-complete": {"params": {"handoff_id": "string"}, "description": "Mark handoff as completed — user finished login, AI resumes control"},
            "login-handoff-cancel": {"params": {"handoff_id": "string", "reason": "string"}, "description": "Cancel an active login handoff session"},
            "login-handoff-list": {"params": {"state": "string", "user_id": "string"}, "description": "List all handoff sessions"},
            "login-handoff-history": {"params": {"limit": "int"}, "description": "Get completed handoff history"},
            "login-handoff-stats": {"params": {}, "description": "Get handoff statistics (success rate, per-domain stats)"},
            "captcha-assess": {"params": {"url": "string"}, "description": "Assess URL risk for captcha/bot detection before navigation"},
            "captcha-preflight": {"params": {}, "description": "Run pre-flight check for automation artifacts on current page"},
            "captcha-monitor-start": {"params": {"mode": "aggressive|moderate|passive"}, "description": "Start real-time captcha detection monitoring"},
            "captcha-monitor-stop": {"params": {}, "description": "Stop captcha detection monitoring"},
            "captcha-health": {"params": {}, "description": "Check page health for captcha/bot detection indicators"},
            "captcha-shutdown": {"params": {"reason": "string"}, "description": "Emergency shutdown page — rescue data, disable network, navigate to about:blank"},
            "llm-complete": {"params": {"prompt": "string", "system_prompt": "string", "max_tokens": "int", "temperature": "float"}, "description": "Complete text using LLM with token saving"},
            "llm-classify": {"params": {"text": "string", "categories": "list"}, "description": "Classify text using LLM with token saving"},
            "llm-extract": {"params": {"text": "string", "schema": "dict"}, "description": "Extract structured data using LLM with token saving"},
            "llm-summarize": {"params": {"text": "string", "max_length": "int", "style": "concise|detailed"}, "description": "Summarize text using LLM with token saving"},
            "llm-provider-set": {"params": {"provider": "string", "api_key": "string", "base_url": "string", "model": "string"}, "description": "Switch LLM provider at runtime"},
            "llm-token-usage": {"params": {}, "description": "Get LLM token usage statistics"},
            "llm-cache-clear": {"params": {}, "description": "Clear LLM response cache"},
            "structured-extract": {"params": {"text": "string", "url": "string"}, "description": "Extract and normalize structured data from page or text"},
            "structured-deduplicate": {"params": {"pages": "list"}, "description": "Deduplicate structured data across pages"},
            "structured-schema": {"params": {"content": "dict", "schema_type": "string"}, "description": "Generate schema.org structured data"},
            "structured-format": {"params": {"data": "dict", "format": "json|markdown|csv|xml|flat_dict"}, "description": "Format structured data in various output formats"},
        }
