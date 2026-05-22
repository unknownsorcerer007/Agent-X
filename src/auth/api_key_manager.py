"""
Agent-OS API Key Manager
Full lifecycle management for API keys with secure storage,
scoped permissions, and usage tracking.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import bcrypt

logger = logging.getLogger("agent-os.auth.api_keys")

# API key format: aos_<32 random hex chars>
KEY_PREFIX = "aos_"
KEY_LENGTH = 32


class APIKeyManager:
    """
    Manages API key lifecycle:
    - Generation with secure random tokens
    - bcrypt hashing for storage
    - Prefix-based lookup for O(1) identification
    - Scoped permissions
    - Per-key rate limits
    - Expiration and revocation
    """

    def __init__(self, db_session_factory=None):
        """
        Args:
            db_session_factory: Async callable returning a DB session.
                                If None, uses in-memory storage (for testing).
        """
        self._db_factory = db_session_factory
        self._memory_store: Dict[str, Dict] = {}  # Fallback for no-DB mode

    def generate_key(self) -> Tuple[str, str, str]:
        """
        Generate a new API key.
        Returns: (full_key, key_prefix, key_hash)
        - full_key: Give this to the user ONCE
        - key_prefix: Store in DB for identification
        - key_hash: Store in DB for verification (never reversible)
        """
        random_part = secrets.token_hex(KEY_LENGTH // 2)
        full_key = f"{KEY_PREFIX}{random_part}"
        key_prefix = full_key[:12]  # "aos_" + first 8 hex chars
        key_hash = bcrypt.hashpw(full_key.encode(), bcrypt.gensalt(rounds=12)).decode()
        return full_key, key_prefix, key_hash

    def verify_key(self, provided_key: str, stored_hash: str) -> bool:
        """Verify an API key against its stored bcrypt hash."""
        try:
            return bcrypt.checkpw(provided_key.encode(), stored_hash.encode())
        except Exception as e:
            logger.error(f"Key verification error: {e}")
            return False

    async def create_key(self, user_id: str, name: str,
                         scopes: Dict[str, bool] = None,
                         requests_per_minute: int = 60,
                         requests_per_day: int = 10000,
                         expires_in_days: int = None) -> Dict[str, Any]:
        """
        Create a new API key for a user.
        Returns dict with the full key (only shown once) and metadata.
        """
        full_key, key_prefix, key_hash = self.generate_key()

        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        key_data = {
            "id": secrets.token_hex(16),
            "user_id": user_id,
            "name": name,
            "key_prefix": key_prefix,
            "key_hash": key_hash,
            "scopes": scopes or {"browser": True, "scanning": False},
            "requests_per_minute": requests_per_minute,
            "requests_per_day": requests_per_day,
            "is_active": True,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc),
            "total_requests": 0,
        }

        if self._db_factory:
            # Store in database
            from src.infra.models import APIKey as APIKeyModel
            async with self._db_factory() as session:
                db_key = APIKeyModel(
                    user_id=user_id,
                    name=name,
                    key_prefix=key_prefix,
                    key_hash=key_hash,
                    scopes=scopes or {"browser": True, "scanning": False},
                    requests_per_minute=requests_per_minute,
                    requests_per_day=requests_per_day,
                    expires_at=expires_at,
                )
                session.add(db_key)
                await session.flush()
                key_data["id"] = db_key.id
                await session.commit()
        else:
            self._memory_store[key_prefix] = key_data

        logger.info(f"API key created for user {user_id}: {key_prefix}...")

        return {
            "id": key_data["id"],
            "name": name,
            "key_prefix": key_prefix,
            "full_key": full_key,  # Only time this is shown!
            "scopes": key_data["scopes"],
            "requests_per_minute": requests_per_minute,
            "requests_per_day": requests_per_day,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "created_at": key_data["created_at"].isoformat(),
            "warning": "Store this key securely. It will not be shown again.",
        }

    async def authenticate(self, provided_key: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate an API key.
        Returns user/key info if valid, None if invalid.
        """
        if not provided_key or not provided_key.startswith(KEY_PREFIX):
            return None

        key_prefix = provided_key[:12]

        if self._db_factory:
            from src.infra.models import APIKey as APIKeyModel
            from sqlalchemy import select
            async with self._db_factory() as session:
                result = await session.execute(
                    select(APIKeyModel).where(
                        APIKeyModel.key_prefix == key_prefix,
                        APIKeyModel.is_active.is_(True),
                    )
                )
                db_key = result.scalar_one_or_none()
                if not db_key:
                    return None

                # Check expiration
                if db_key.expires_at and datetime.now(timezone.utc) > db_key.expires_at:
                    logger.warning(f"Expired API key used: {key_prefix}")
                    return None

                # Verify hash
                if not self.verify_key(provided_key, db_key.key_hash):
                    logger.warning(f"Invalid API key attempt: {key_prefix}")
                    return None

                # Update usage
                db_key.last_used_at = datetime.now(timezone.utc)
                db_key.total_requests += 1
                await session.commit()

                return {
                    "user_id": db_key.user_id,
                    "api_key_id": db_key.id,
                    "key_prefix": key_prefix,
                    "scopes": db_key.scopes,
                    "requests_per_minute": db_key.requests_per_minute,
                    "requests_per_day": db_key.requests_per_day,
                }
        else:
            # In-memory fallback
            key_data = self._memory_store.get(key_prefix)
            if not key_data:
                return None

            if not key_data.get("is_active"):
                return None

            if key_data.get("expires_at"):
                if datetime.now(timezone.utc) > key_data["expires_at"]:
                    return None

            if not self.verify_key(provided_key, key_data["key_hash"]):
                return None

            key_data["total_requests"] = key_data.get("total_requests", 0) + 1

            return {
                "user_id": key_data["user_id"],
                "api_key_id": key_data["id"],
                "key_prefix": key_prefix,
                "scopes": key_data["scopes"],
                "requests_per_minute": key_data["requests_per_minute"],
                "requests_per_day": key_data["requests_per_day"],
            }

    async def revoke_key(self, key_id_or_prefix: str, user_id: str) -> bool:
        """Revoke (deactivate) an API key.
        
        Accepts either the key's `id` or `key_prefix` for flexibility,
        since list_keys() returns `id` but the HTTP route uses `key_prefix`.
        """
        if self._db_factory:
            from src.infra.models import APIKey as APIKeyModel
            from sqlalchemy import update, or_
            async with self._db_factory() as session:
                result = await session.execute(
                    update(APIKeyModel)
                    .where(
                        or_(
                            APIKeyModel.key_prefix == key_id_or_prefix,
                            APIKeyModel.id == key_id_or_prefix,
                        ),
                        APIKeyModel.user_id == user_id,
                    )
                    .values(is_active=False)
                )
                await session.commit()
                return result.rowcount > 0
        else:
            # Try lookup by key_prefix first
            key_data = self._memory_store.get(key_id_or_prefix)
            # If not found, search by id
            if not key_data:
                for stored_key, data in self._memory_store.items():
                    if data.get("id") == key_id_or_prefix:
                        key_data = data
                        break
            if key_data and key_data["user_id"] == user_id:
                key_data["is_active"] = False
                return True
            return False

    async def list_keys(self, user_id: str) -> List[Dict]:
        """List all API keys for a user (without hashes)."""
        if self._db_factory:
            from src.infra.models import APIKey as APIKeyModel
            from sqlalchemy import select
            async with self._db_factory() as session:
                result = await session.execute(
                    select(APIKeyModel)
                    .where(APIKeyModel.user_id == user_id)
                    .order_by(APIKeyModel.created_at.desc())
                )
                keys = result.scalars().all()
                return [
                    {
                        "id": k.id,
                        "name": k.name,
                        "key_prefix": k.key_prefix,
                        "scopes": k.scopes,
                        "is_active": k.is_active,
                        "requests_per_minute": k.requests_per_minute,
                        "total_requests": k.total_requests,
                        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                        "created_at": k.created_at.isoformat(),
                        "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                    }
                    for k in keys
                ]
        else:
            return [
                {
                    "id": v["id"],
                    "name": v["name"],
                    "key_prefix": k,
                    "scopes": v["scopes"],
                    "is_active": v.get("is_active", True),
                    "total_requests": v.get("total_requests", 0),
                    "created_at": v["created_at"].isoformat(),
                }
                for k, v in self._memory_store.items()
                if v["user_id"] == user_id
            ]

    async def check_scope(self, provided_key: str, required_scope: str) -> bool:
        """Check if an API key has a specific scope."""
        auth = await self.authenticate(provided_key)
        if not auth:
            return False
        scopes = auth.get("scopes", {})
        return scopes.get(required_scope, False) or scopes.get("admin", False)
