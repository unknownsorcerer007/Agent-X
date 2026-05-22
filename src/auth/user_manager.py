"""
Agent-OS User Manager
Full user lifecycle: registration, authentication, quota enforcement.
"""
import logging
import re
import secrets
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import bcrypt

logger = logging.getLogger("agent-os.auth.users")


class UserManager:
    """
    User account management with:
    - Registration with email/password
    - bcrypt password hashing
    - Quota enforcement
    - Usage tracking
    """

    # Email validation regex
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

    def __init__(self, db_session_factory=None):
        self._db_factory = db_session_factory
        self._memory_store: Dict[str, Dict] = {}
        # In-memory logging deques for usage and audit when no database
        self._memory_usage_log: deque = deque(maxlen=10000)
        self._memory_audit_log: deque = deque(maxlen=10000)

    def hash_password(self, password: str) -> str:
        """Hash a password with bcrypt."""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception:
            return False

    def _validate_email(self, email: str) -> bool:
        """Validate email format using regex pattern."""
        return bool(self.EMAIL_PATTERN.match(email))

    async def create_user(self, email: str, username: str, password: str,
                          display_name: str = None, organization: str = None,
                          plan: str = "free") -> Dict[str, Any]:
        """Register a new user."""
        # Validate inputs
        if not email or not self._validate_email(email):
            raise ValueError("Valid email required")
        if not username or len(username) < 3:
            raise ValueError("Username must be at least 3 characters")
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters")

        password_hash = self.hash_password(password)
        user_id = secrets.token_hex(16)

        plan_limits = {
            "free": {"requests": 10000, "sessions": 3, "storage_mb": 500},
            "pro": {"requests": 100000, "sessions": 10, "storage_mb": 5000},
            "enterprise": {"requests": 1000000, "sessions": 50, "storage_mb": 50000},
        }
        limits = plan_limits.get(plan, plan_limits["free"])

        user_data = {
            "id": user_id,
            "email": email.lower().strip(),
            "username": username.strip(),
            "password_hash": password_hash,
            "display_name": display_name or username,
            "organization": organization,
            "plan": plan,
            "monthly_request_limit": limits["requests"],
            "concurrent_session_limit": limits["sessions"],
            "storage_limit_mb": limits["storage_mb"],
            "is_active": True,
            "is_verified": False,
            "is_admin": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_login_at": None,
        }

        if self._db_factory:
            from src.infra.models import User as UserModel
            async with self._db_factory() as session:
                # Check for existing email/username
                from sqlalchemy import select
                existing = await session.execute(
                    select(UserModel).where(
                        (UserModel.email == user_data["email"]) |
                        (UserModel.username == user_data["username"])
                    )
                )
                if existing.scalar_one_or_none():
                    raise ValueError("Email or username already exists")

                db_user = UserModel(**{k: v for k, v in user_data.items() if k != "id"})
                db_user.id = user_id
                session.add(db_user)
                await session.commit()
        else:
            # Check in-memory
            for u in self._memory_store.values():
                if u["email"] == user_data["email"]:
                    raise ValueError("Email already exists")
                if u["username"] == user_data["username"]:
                    raise ValueError("Username already exists")
            self._memory_store[user_id] = user_data

        logger.info(f"User created: {username} ({email})")

        return {
            "id": user_id,
            "email": user_data["email"],
            "username": user_data["username"],
            "display_name": user_data["display_name"],
            "plan": plan,
            "monthly_request_limit": limits["requests"],
            "concurrent_session_limit": limits["sessions"],
            "created_at": user_data["created_at"].isoformat(),
        }

    async def authenticate_user(self, username_or_email: str, password: str) -> Optional[Dict]:
        """Authenticate user with username/email + password."""
        if self._db_factory:
            from src.infra.models import User as UserModel
            from sqlalchemy import select
            async with self._db_factory() as session:
                result = await session.execute(
                    select(UserModel).where(
                        ((UserModel.email == username_or_email.lower()) |
                         (UserModel.username == username_or_email)) &
                        (UserModel.is_active.is_(True))
                    )
                )
                db_user = result.scalar_one_or_none()
                if not db_user:
                    return None

                if not self.verify_password(password, db_user.password_hash):
                    return None

                # Update last login
                db_user.last_login_at = datetime.now(timezone.utc)
                await session.commit()

                return {
                    "user_id": db_user.id,
                    "email": db_user.email,
                    "username": db_user.username,
                    "plan": db_user.plan,
                    "is_admin": db_user.is_admin,
                    "scopes": self._get_scopes_for_plan(db_user.plan),
                }
        else:
            for user_data in self._memory_store.values():
                if (user_data["email"] == username_or_email.lower() or
                        user_data["username"] == username_or_email):
                    if not user_data.get("is_active"):
                        return None
                    if self.verify_password(password, user_data["password_hash"]):
                        user_data["last_login_at"] = datetime.now(timezone.utc)
                        return {
                            "user_id": user_data["id"],
                            "email": user_data["email"],
                            "username": user_data["username"],
                            "plan": user_data["plan"],
                            "is_admin": user_data.get("is_admin", False),
                            "scopes": self._get_scopes_for_plan(user_data["plan"]),
                        }
        return None

    async def get_user(self, user_id: str) -> Optional[Dict]:
        """Get user by ID."""
        if self._db_factory:
            from src.infra.models import User as UserModel
            from sqlalchemy import select
            async with self._db_factory() as session:
                result = await session.execute(
                    select(UserModel).where(UserModel.id == user_id)
                )
                db_user = result.scalar_one_or_none()
                if db_user:
                    return {
                        "id": db_user.id,
                        "email": db_user.email,
                        "username": db_user.username,
                        "display_name": db_user.display_name,
                        "organization": db_user.organization,
                        "plan": db_user.plan,
                        "is_active": db_user.is_active,
                        "is_admin": db_user.is_admin,
                        "monthly_request_limit": db_user.monthly_request_limit,
                        "concurrent_session_limit": db_user.concurrent_session_limit,
                        "created_at": db_user.created_at.isoformat(),
                        "last_login_at": db_user.last_login_at.isoformat() if db_user.last_login_at else None,
                    }
        return self._memory_store.get(user_id)

    async def check_quota(self, user_id: str, current_month_requests: int) -> Dict:
        """Check if user has remaining quota."""
        user = await self.get_user(user_id)
        if not user:
            return {"allowed": False, "reason": "User not found"}

        limit = user.get("monthly_request_limit", 10000)
        if current_month_requests >= limit:
            return {
                "allowed": False,
                "reason": "Monthly request limit exceeded",
                "limit": limit,
                "used": current_month_requests,
            }

        return {
            "allowed": True,
            "limit": limit,
            "used": current_month_requests,
            "remaining": limit - current_month_requests,
        }

    def _get_scopes_for_plan(self, plan: str) -> list:
        """Get available scopes based on plan."""
        scopes = {
            "free": ["browser"],
            "pro": ["browser", "scanning", "workflows"],
            "enterprise": ["browser", "scanning", "workflows", "admin"],
        }
        return scopes.get(plan, scopes["free"])

    async def log_usage(self, user_id: str, command: str, status: str,
                        duration_ms: int, api_key_id: str = None,
                        session_id: str = None, client_ip: str = None,
                        error_message: str = None):
        """Log a command execution for billing/analytics."""
        if not self._db_factory:
            self._memory_usage_log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "api_key_id": api_key_id,
                "session_id": session_id,
                "command": command,
                "status": status,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "error_message": error_message,
            })
            return
        from src.infra.models import UsageLog
        async with self._db_factory() as session:
            log = UsageLog(
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                command=command,
                status=status,
                duration_ms=duration_ms,
                client_ip=client_ip,
                error_message=error_message,
            )
            session.add(log)
            await session.commit()

    async def log_audit(self, user_id: str, action: str, success: bool,
                        client_ip: str = None, details: dict = None,
                        resource_type: str = None, resource_id: str = None,
                        error_message: str = None):
        """Log a security audit event."""
        if not self._db_factory:
            self._memory_audit_log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "client_ip": client_ip,
                "details": details,
                "success": success,
                "error_message": error_message,
            })
            return
        from src.infra.models import AuditLog
        async with self._db_factory() as session:
            log = AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                client_ip=client_ip,
                details=details,
                success=success,
                error_message=error_message,
            )
            session.add(log)
            await session.commit()
