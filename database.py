from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from config import settings


# Async engine -- uses asyncpg driver (not psycopg2)
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,  # Validating the connections before use
    echo=settings.DEBUG,  # Logging SQL queries in dev only
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # keeping objects usable after commit in async context
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def create_tables():
    """Called at startup -- creates all tables that don't exist yet."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables():
    """Used in tests only -- drops all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

