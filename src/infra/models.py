"""
Agent-OS Database Models
All SQLAlchemy ORM models for production deployment.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import (
    String, Text, Integer, Boolean, DateTime,
    ForeignKey, Index, CheckConstraint,
    func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infra.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    """User account — one per customer/organization."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    organization: Mapped[Optional[str]] = mapped_column(String(200))

    # Quotas and limits
    plan: Mapped[str] = mapped_column(
        String(50), nullable=False, default="free",
        server_default="free"
    )
    monthly_request_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10000, server_default="10000"
    )
    concurrent_session_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    storage_limit_mb: Mapped[int] = mapped_column(
        Integer, nullable=False, default=500, server_default="500"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow,
        onupdate=utcnow, server_default=func.now()
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    api_keys: Mapped[list["APIKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["AgentSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    usage_logs: Mapped[list["UsageLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("monthly_request_limit > 0", name="ck_user_request_limit_positive"),
        CheckConstraint("concurrent_session_limit > 0", name="ck_user_session_limit_positive"),
    )


class APIKey(Base):
    """API keys for authentication. Key prefix stored in plaintext, full hash stored securely."""
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Key prefix (first 8 chars) for identification — NOT the full key
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    # bcrypt hash of the full key
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Scopes/permissions
    scopes: Mapped[dict] = mapped_column(
        sa.JSON, nullable=False, default=dict,
        server_default=text("'{}'")
    )

    # Rate limits (per-key overrides)
    requests_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    requests_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10000, server_default="10000"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Usage tracking
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_used_ip: Mapped[Optional[str]] = mapped_column(String(45))  # IPv6 max
    total_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="api_keys")

    __table_args__ = (
        Index("ix_api_keys_user_active", "user_id", "is_active"),
    )


class AgentSession(Base):
    """Persistent session records for agent browser sessions."""
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    api_key_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), index=True
    )

    # Session metadata
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    browser_profile: Mapped[Optional[str]] = mapped_column(String(100))
    device: Mapped[Optional[str]] = mapped_column(String(50))

    # Stats
    commands_executed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    blocked_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    pages_visited: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Connection info
    client_ip: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    user: Mapped["User"] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_sessions_user_status", "user_id", "status"),
        Index("ix_sessions_expires", "expires_at"),
    )


class UsageLog(Base):
    """Per-request usage tracking for billing and analytics."""
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    api_key_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)

    # Request details
    command: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success, error, rate_limited
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Performance
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    # Network
    client_ip: Mapped[Optional[str]] = mapped_column(String(45))

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now(),
        index=True
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="usage_logs")

    __table_args__ = (
        Index("ix_usage_user_command", "user_id", "command", "created_at"),
        Index("ix_usage_created_status", "created_at", "status"),
    )


class AuditLog(Base):
    """Security audit trail — immutable record of all sensitive actions."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # Action details
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50))
    resource_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Context
    client_ip: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    details: Mapped[Optional[dict]] = mapped_column(sa.JSON)

    # Result
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamp (immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now(),
        index=True
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_action_created", "action", "created_at"),
        Index("ix_audit_user_action", "user_id", "action"),
    )
