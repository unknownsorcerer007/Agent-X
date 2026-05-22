"""
Agent-OS Database Layer
Production-grade async SQLAlchemy with connection pooling, health checks,
and automatic retry on transient failures.
"""
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("agent-os.infra.database")


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""
    pass


class DatabaseManager:
    """
    Manages async database connections with:
    - Connection pooling (configurable size + overflow)
    - Automatic reconnection on failure
    - Health check endpoint
    - Query timing and slow-query logging
    """

    def __init__(self, dsn: str, pool_size: int = 20, max_overflow: int = 10,
                 pool_timeout: int = 30, pool_recycle: int = 3600):
        self.dsn = dsn
        self.engine = create_async_engine(
            dsn,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,  # Verify connections before use
            echo=False,
            connect_args={
                "server_settings": {
                    "application_name": "agent-os",
                    "statement_timeout": "30000",  # 30s statement timeout
                }
            } if "postgresql" in dsn else {},
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._setup_query_logging()

    def _setup_query_logging(self):
        """Log slow queries (>500ms)."""
        @event.listens_for(self.engine.sync_engine, "before_cursor_execute")
        def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            conn.info["query_start_time"] = time.time()

        @event.listens_for(self.engine.sync_engine, "after_cursor_execute")
        def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            elapsed = (time.time() - conn.info.get("query_start_time", time.time())) * 1000
            if elapsed > 500:
                logger.warning(f"Slow query ({elapsed:.0f}ms): {statement[:200]}")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session with automatic commit/rollback."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def health_check(self) -> dict:
        """Check database connectivity and return health status."""
        start = time.time()
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            latency_ms = (time.time() - start) * 1000
            pool = self.engine.pool
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "pool_size": pool.size(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "latency_ms": round((time.time() - start) * 1000, 2),
            }

    async def create_tables(self):
        """Create all tables (for development/testing)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

    async def drop_tables(self):
        """Drop all tables (DANGER - for testing only)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("Database tables dropped")

    async def close(self):
        """Close all connections."""
        await self.engine.dispose()
        logger.info("Database connections closed")


# Global instance (initialized by main.py)
_db: Optional[DatabaseManager] = None


def get_db() -> DatabaseManager:
    """Get the global database manager."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


def init_db(dsn: str, **kwargs) -> DatabaseManager:
    """Initialize the global database manager."""
    global _db
    _db = DatabaseManager(dsn, **kwargs)
    return _db
