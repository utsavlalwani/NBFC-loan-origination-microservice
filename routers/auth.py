from fastapi import APIRouter, HTTPException, status

from schemas.auth import UserLogin, Token
from dependencies import create_access_token

router = APIRouter()

# Hardcoded test users -- to be replaced with a real users table in production
MOCK_USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "ops_user": {"password": "ops123", "role": "ops"},
    "applicant": {"password": "app123", "role": "applicant"},
}


@router.post("/login", response_model=Token, summary="Get a JWT access token")
async def login(credentials: UserLogin):
    user = MOCK_USERS.get(credentials.username)
    if not user or user["password"] != credentials.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(user_id=credentials.username, role=user["role"])
    return Token(access_token=token)

