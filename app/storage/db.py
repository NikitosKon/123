"""Подключение к БД (SQLAlchemy Async)."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        url = get_settings().database_url
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url.removeprefix("postgres://")
        elif url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
        _engine = create_async_engine(url, pool_size=10, max_overflow=20)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as s:
        yield s
