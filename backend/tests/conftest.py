"""Shared test fixtures for the WOO Buddy backend test suite.

Provides:
- Test PostgreSQL database (woobuddy_test) with per-test cleanup
- httpx.AsyncClient wired to the FastAPI app with dependency overrides
- Direct DB session for service-level tests (rollback-based)
"""

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.session import get_db
from app.models.schemas import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://woobuddy:woobuddy@localhost:5432/woobuddy_test",
)

# NullPool: each operation gets a fresh connection, avoiding "operation in progress"
# errors when connections are reused between fixtures.
_test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
_test_session_factory = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False,
)
_tables_created = False


async def _ensure_tables() -> None:
    global _tables_created
    if not _tables_created:
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        _tables_created = True


async def _truncate_tables() -> None:
    """Delete all rows from all tables (respecting FK order)."""
    async with _test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


# ---------------------------------------------------------------------------
# Direct DB session (for service-level tests like propagation)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession]:
    """Per-test database session with automatic transaction rollback.

    Use this for tests that directly call service functions (not HTTP endpoints).
    """
    await _ensure_tables()
    async with _test_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        yield session
        await session.close()
        await trans.rollback()


# ---------------------------------------------------------------------------
# HTTP client (for endpoint tests)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """httpx.AsyncClient wired to the FastAPI app.

    Each HTTP request gets its own DB session. Data is committed for real
    and truncated after each test.
    """
    await _ensure_tables()
    await _truncate_tables()

    from app.main import create_app

    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        async with _test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await _truncate_tables()


@pytest_asyncio.fixture
async def seed_db() -> AsyncGenerator[AsyncSession]:
    """Committable session for seeding data before endpoint tests.

    Use together with `client` when you need pre-existing data in the DB.
    Data is committed (visible to client) and cleaned up by client's truncation.
    """
    await _ensure_tables()
    session = _test_session_factory()
    yield session
    await session.close()
