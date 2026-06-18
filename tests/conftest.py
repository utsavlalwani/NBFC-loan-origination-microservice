import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from main import app
from database import Base, get_db  # Note: get_db imported but overridden below
from dependencies import get_db as dep_get_db

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/loanflow_test"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_test_tables():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    """Test client with DB dependency overridden to use test session."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[dep_get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_token(client):
    """Returns a valid JWT token for the 'applicant' test user."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "applicant", "password": "app123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def ops_token(client):
    """Returns a valid JWT token for the 'ops_user' test user."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "ops_user", "password": "ops123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]
