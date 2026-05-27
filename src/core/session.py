"""
Agent-X Session Manager
Handles session lifecycle, auto-wipe, and sandboxing.
"""
import asyncio
import time
import logging
import secrets
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("agent-x.session")

# Hard cap on total sessions (active + expired) to prevent memory leaks.
MAX_SESSIONS: int = 1000


@dataclass
class Session:
    """Represents an agent session."""
    session_id: str
    agent_token: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0
    pages: list = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    active: bool = True
    blocked_requests: int = 0
    commands_executed: int = 0
    ref_map: Optional[Any] = None  # DOM snapshot RefMap for @eN ref resolution

    def __post_init__(self) -> None:
        if self.expires_at == 0:
            self.expires_at = self.created_at + (15 * 60)  # 15 min default

    @property
    def is_expired(self) -> bool:
        """Check if the session has exceeded its timeout."""
        return time.time() > self.expires_at

    @property
    def time_remaining(self) -> float:
        """Seconds until the session expires."""
        return max(0, self.expires_at - time.time())

    @property
    def age(self) -> float:
        """Seconds since the session was created."""
        return time.time() - self.created_at


class SessionManager:
    """Manages agent sessions with auto-cleanup and sandboxing."""

    def __init__(self, config: Any, browser: Any = None) -> None:
        self.config = config
        self.browser = browser
        self.sessions: Dict[str, Session] = {}
        self._token_to_session: Dict[str, str] = {}  # agent_token -> session_id
        self._cleanup_task: Optional[asyncio.Task] = None
        self._max_sessions: int = config.get("session.max_concurrent", 3)
        self._default_timeout: float = config.get("session.timeout_minutes", 15) * 60

    async def start(self) -> None:
        """Start the session cleanup loop."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session manager started")

    async def stop(self) -> None:
        """Stop and wipe all sessions."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        for session_id in list(self.sessions.keys()):
            await self.destroy_session(session_id)
        logger.info("All sessions destroyed")

    def create_session(
        self, agent_token: str, timeout_minutes: Optional[int] = None
    ) -> Session:
        """Create a new session for an agent, or return an existing active one.

        If the agent already has an active, non-expired session, that session
        is returned instead of creating a duplicate. This prevents orphan
        sessions from accumulating when the same token reconnects.

        Args:
            agent_token: The agent's authentication token.
            timeout_minutes: Optional custom timeout in minutes.

        Returns:
            The new or existing Session.

        Raises:
            RuntimeError: If the global session cap has been reached.
        """
        # BUG FIX 1: Check for existing active session for this token
        existing = self.get_session_by_token(agent_token)
        if existing is not None:
            logger.debug(
                f"Reusing existing session {existing.session_id} for token "
                f"{agent_token[:8]}..."
            )
            return existing

        # BUG FIX 2: Enforce global session cap to prevent memory leaks
        if len(self.sessions) >= MAX_SESSIONS:
            # First pass: evict all expired sessions
            expired_ids: List[str] = [
                sid for sid, s in self.sessions.items() if s.is_expired
            ]
            for sid in expired_ids:
                evicted = self.sessions.pop(sid, None)
                if evicted:
                    self._token_to_session.pop(evicted.agent_token, None)

            if expired_ids:
                logger.info(
                    f"Evicted {len(expired_ids)} expired sessions "
                    f"(cap: {MAX_SESSIONS})"
                )

            # Second pass: if still at cap, refuse to create
            if len(self.sessions) >= MAX_SESSIONS:
                raise RuntimeError(
                    f"Session limit reached ({MAX_SESSIONS}). "
                    "Destroy existing sessions before creating new ones."
                )

        # Enforce max concurrent *active* sessions
        active = [s for s in self.sessions.values() if s.active and not s.is_expired]
        if len(active) >= self._max_sessions:
            oldest = min(active, key=lambda s: s.created_at)
            self.sessions[oldest.session_id].active = False
            logger.info(
                f"Deactivated oldest session {oldest.session_id} "
                f"(concurrent limit: {self._max_sessions})"
            )

        session_id = secrets.token_urlsafe(16)
        timeout = (timeout_minutes or self.config.get("session.timeout_minutes", 15)) * 60

        session = Session(
            session_id=session_id,
            agent_token=agent_token,
            expires_at=time.time() + timeout,
        )
        self.sessions[session_id] = session
        self._token_to_session[agent_token] = session_id
        logger.info(f"Session created: {session_id} (expires in {timeout / 60:.0f}min)")
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            The Session if found and not expired, None otherwise.
        """
        session = self.sessions.get(session_id)
        if session and session.is_expired:
            session.active = False
            return None
        return session

    def get_session_by_token(self, agent_token: str) -> Optional[Session]:
        """Get active session by agent token using reverse index (O(1)).

        Args:
            agent_token: The agent's authentication token.

        Returns:
            The active, non-expired Session for this token, or None.
        """
        session_id = self._token_to_session.get(agent_token)
        if session_id is None:
            return None
        session = self.sessions.get(session_id)
        if session is None or not session.active or session.is_expired:
            # Clean up stale index entry
            self._token_to_session.pop(agent_token, None)
            return None
        return session

    async def destroy_session(self, session_id: str) -> None:
        """Destroy a session and wipe all its data, including browser tabs.

        Args:
            session_id: The session identifier to destroy.
        """
        session = self.sessions.get(session_id)
        if session:
            session.active = False
            # Close associated browser tabs
            if self.browser is None:
                logger.warning(
                    f"Browser instance is None while destroying session {session_id} — "
                    "browser tabs cannot be closed"
                )
            if self.browser and hasattr(session, "data") and session.data:
                tab_ids = session.data.get("tab_ids", [])
                for tab_id in tab_ids:
                    try:
                        await self.browser.close_tab(tab_id)
                    except Exception:
                        pass
            # Wipe session data (security)
            session.data.clear()
            session.pages.clear()
            # Clean up reverse index
            self._token_to_session.pop(session.agent_token, None)
            del self.sessions[session_id]
            logger.info(f"Session destroyed and wiped: {session_id}")

    def extend_session(self, session_id: str, minutes: int = 15) -> None:
        """Extend session timeout.

        Args:
            session_id: The session identifier.
            minutes: Number of minutes to extend by.
        """
        session = self.sessions.get(session_id)
        if session and session.active:
            session.expires_at = time.time() + (minutes * 60)

    def list_active_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions (no sensitive data).

        Returns:
            List of dicts with safe session metadata.
        """
        return [
            {
                "session_id": s.session_id,
                "created_at": datetime.fromtimestamp(s.created_at).isoformat(),
                "expires_in_seconds": int(s.time_remaining),
                "commands_executed": s.commands_executed,
                "blocked_requests": s.blocked_requests,
                "active": s.active and not s.is_expired,
            }
            for s in self.sessions.values()
        ]

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                expired = [sid for sid, s in self.sessions.items() if s.is_expired]
                for sid in expired:
                    await self.destroy_session(sid)
                if expired:
                    logger.info(f"Cleaned up {len(expired)} expired sessions")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
