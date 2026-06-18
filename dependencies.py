import logging
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError

from database import AsyncSessionLocal
from config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer()


# --- Database session -------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields one async DB session per request. Commits on success, rolls back on any exception, always closes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# --- JWT Authentication --------------------------------------------

async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Extracts and Validates the Bearer JWT Token. Raises 401 if token is missing, expired or tampered. Returns the decoded payload: {"user_id": ..., "role": ...}
    """
    token = credentials.credentials
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        role: str = payload.get("role", "applicant")
        if user_id is None:
            raise credentials_error
        return {"user_id": user_id, "role": role}
    except JWTError as exc:
        logger.warning(f"JWT validation failed: {exc}")
        raise credentials_error


# --- Role-based access --------------------------------------

def require_role(*allowed_roles: str):
    """
    Factory Dependency -- returns a checker function that validates the current user's role against the allowed set.

    Usage:
        Depends(require_role("admin", "ops"))
    """
    async def checker(
            current_user: dict = Depends(get_current_user),
    ) -> dict:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user['role']}' is not authorized for this action."
            )
        return current_user
    return checker


# --- Token Creation --------------------------------------------------

def create_access_token(user_id: str, role: str) -> str:
    import datetime
    from jose import jwt
    expire = datetime.datetime.utcnow() + datetime.timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

