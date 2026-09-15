"""Shared FastAPI dependencies: DB sessions and the agent concurrency limiter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.sessions import repository


async def get_db() -> AsyncIterator[AsyncSession]:
    async with repository.session() as db:
        yield db


@lru_cache
def _semaphore_for(max_concurrent: int) -> asyncio.Semaphore:
    return asyncio.Semaphore(max_concurrent)


def get_agent_semaphore(settings: Settings = Depends(get_settings)) -> asyncio.Semaphore:
    # `settings` MUST be `Depends(get_settings)`, not a plain `= None`
    # default: FastAPI treats an un-marked BaseModel-typed parameter on a
    # dependency callable as a second request-body model, which silently
    # breaks JSON binding for every route using this dependency (discovered
    # via a failing test: FastAPI expected `{"body": ..., "settings": ...}`
    # instead of the flat QueryRequest JSON).
    return _semaphore_for(settings.agent_max_concurrent_requests)
