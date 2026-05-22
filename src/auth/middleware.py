"""
Agent-OS Auth Middleware
Integrates JWT + API key authentication into aiohttp server.
Provides per-user rate limiting, scope checking, and audit logging.
"""
import logging
import time
from collections import defaultdict
from functools import wraps
from typing import Dict, Optional

from aiohttp import web

from src.auth.jwt_handler import JWTHandler
from src.auth.api_key_manager import APIKeyManager

logger = logging.getLogger("agent-os.auth.middleware")


class AuthMiddleware:
    """
    Authentication and authorization middleware for aiohttp.

    Supports three auth methods:
    1. Bearer JWT token (Authorization: Bearer <token>)
    2. API key (token field in JSON body, or X-API-Key header)
    3. Legacy token (token field in JSON body, for backward compatibility)

    Provides:
    - Per-user rate limiting via Redis
    - Scope-based authorization
    - Request context injection (user_id, api_key_id, scopes)
    - Audit logging
    - Brute-force protection on login endpoints
    """

    def __init__(self, jwt_handler: JWTHandler, api_key_manager: APIKeyManager,
                 redis_client=None, legacy_tokens: list = None):
        self.jwt = jwt_handler
        self.api_keys = api_key_manager
        self.redis = redis_client
        self._legacy_tokens = legacy_tokens or []
        # Brute-force protection: in-memory failed attempt tracking
        self._login_attempts: Dict[str, list] = defaultdict(list)  # ip -> [timestamps]
        self._max_attempts = 5
        self._lockout_seconds = 15 * 60  # 15 minutes

    def add_legacy_token(self, token: str):
        """Add a legacy token for backward compatibility."""
        if token and token not in self._legacy_tokens:
            self._legacy_tokens.append(token)

    async def authenticate_request(self, request: web.Request,
                                   body: dict = None) -> Optional[dict]:
        """
        Extract and validate authentication from request.
        Returns auth context dict if valid, None if unauthorized.
        """
        # Method 1: Bearer JWT
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = self.jwt.verify_token(token, token_type="access")
            if payload:
                return {
                    "user_id": payload["sub"],
                    "api_key_id": payload.get("key_id"),
                    "scopes": payload.get("scopes", []),
                    "auth_method": "jwt",
                }
            return None

        # Method 2: API key from header
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            auth = await self.api_keys.authenticate(api_key)
            if auth:
                auth["auth_method"] = "api_key"
                return auth
            return None

        # Method 3: Token from body (API key, JWT, or legacy)
        if body and body.get("token"):
            token = body["token"]
            # Check if it's an API key (starts with aos_)
            if token.startswith("aos_"):
                auth = await self.api_keys.authenticate(token)
                if auth:
                    auth["auth_method"] = "api_key"
                    return auth
            # Try as JWT
            payload = self.jwt.verify_token(token, token_type="access")
            if payload:
                return {
                    "user_id": payload["sub"],
                    "api_key_id": payload.get("key_id"),
                    "scopes": payload.get("scopes", []),
                    "auth_method": "jwt",
                }
            # Try as legacy token
            import hmac as _hmac
            for legacy_token in self._legacy_tokens:
                if legacy_token and _hmac.compare_digest(token, legacy_token):
                    return {
                        "user_id": "legacy",
                        "api_key_id": None,
                        "scopes": ["browser"],
                        "auth_method": "legacy_token",
                    }

        return None

    async def check_rate_limit(self, auth_context: dict) -> tuple:
        """
        Check rate limit for the authenticated user.
        Returns: (allowed: bool, headers: dict)
        """
        if not self.redis:
            return True, {}

        user_id = auth_context["user_id"]
        rpm = auth_context.get("requests_per_minute", 60)

        allowed, current, remaining = await self.redis.check_rate_limit(
            f"user:{user_id}",
            max_requests=rpm,
            window_seconds=60,
        )

        headers = {
            "X-RateLimit-Limit": str(rpm),
            "X-RateLimit-Remaining": str(max(0, remaining)),
            "X-RateLimit-Reset": str(int(time.time()) + 60),
        }

        return allowed, headers

    def check_login_attempts(self, identifier: str) -> bool:
        """Check if login is allowed for this identifier (IP or username)."""
        # Periodically clean up expired login attempt records
        self._cleanup_login_attempts()

        now = time.time()
        cutoff = now - self._lockout_seconds
        attempts = self._login_attempts.get(identifier, [])
        # Clean old attempts
        recent = [t for t in attempts if t > cutoff]
        self._login_attempts[identifier] = recent
        return len(recent) < self._max_attempts

    def record_login_failure(self, identifier: str):
        """Record a failed login attempt."""
        self._login_attempts[identifier].append(time.time())

    def record_login_success(self, identifier: str):
        """Clear failed attempts on successful login."""
        self._login_attempts.pop(identifier, None)

    def get_lockout_remaining(self, identifier: str) -> int:
        """Get seconds remaining in lockout, or 0 if not locked out."""
        attempts = self._login_attempts.get(identifier, [])
        if len(attempts) < self._max_attempts:
            return 0
        oldest_relevant = max(attempts[-self._max_attempts:])
        remaining = int(oldest_relevant + self._lockout_seconds - time.time())
        return max(0, remaining)

    def _cleanup_login_attempts(self):
        """Remove expired login attempt records to prevent unbounded growth."""
        now = time.time()
        expired = [
            k for k, v in self._login_attempts.items()
            if not v or now - v[-1] > 3600  # Remove entries with no attempts in the last hour
        ]
        for k in expired:
            del self._login_attempts[k]

    def require_scope(self, scope: str):
        """Decorator to require a specific scope for an endpoint."""
        def decorator(handler):
            @wraps(handler)
            async def wrapper(request: web.Request) -> web.Response:
                auth = request.get("auth_context")
                if not auth:
                    return web.json_response(
                        {"status": "error", "error": "Authentication required"},
                        status=401
                    )
                scopes = auth.get("scopes", [])
                if isinstance(scopes, list):
                    has_scope = scope in scopes or "admin" in scopes
                elif isinstance(scopes, dict):
                    has_scope = scopes.get(scope, False) or scopes.get("admin", False)
                else:
                    has_scope = False

                if not has_scope:
                    return web.json_response(
                        {"status": "error", "error": f"Missing required scope: {scope}"},
                        status=403
                    )
                return await handler(request)
            return wrapper
        return decorator


def create_auth_middleware(auth_mw: AuthMiddleware):
    """
    Create aiohttp middleware that handles auth + rate limiting.
    """
    @web.middleware
    async def middleware(request: web.Request, handler):
        # Skip auth for public endpoints (no authentication required)
        skip_paths = {"/status", "/health", "/commands", "/favicon.ico"}
        # Skip auth for auth endpoints (register, login, refresh — they handle their own auth)
        skip_prefixes = ("/auth/register", "/auth/login", "/auth/refresh")
        if request.path in skip_paths or any(request.path.startswith(p) for p in skip_prefixes):
            return await handler(request)

        # Skip auth for OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await handler(request)

        # Parse body for POST requests
        body = None
        if request.method == "POST" and request.content_type == "application/json":
            try:
                body = await request.json()
                request['parsed_body'] = body  # Store for handlers to reuse
            except Exception:
                pass

        # Authenticate
        auth_context = await auth_mw.authenticate_request(request, body)
        if not auth_context:
            return web.json_response(
                {"status": "error", "error": "Invalid or missing authentication. Use API key (X-API-Key header or token field) or JWT Bearer token."},
                status=401,
            )

        # Rate limit
        allowed, rate_headers = await auth_mw.check_rate_limit(auth_context)
        if not allowed:
            resp = web.json_response(
                {"status": "error", "error": "Rate limit exceeded. Slow down."},
                status=429,
            )
            for k, v in rate_headers.items():
                resp.headers[k] = v
            return resp

        # Inject auth context into request
        request["auth_context"] = auth_context

        # Call handler
        response = await handler(request)

        # Add rate limit headers
        for k, v in rate_headers.items():
            response.headers[k] = v

        return response

    return middleware
