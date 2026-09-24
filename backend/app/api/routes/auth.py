"""
backend/app/api/routes/auth.py — Authentication Endpoints

Endpoints:
  POST /api/v1/auth/register  → Public recruiter self-registration
  POST /api/v1/auth/login     → Returns JWT access token
  GET  /api/v1/auth/me        → Returns current recruiter profile (auth required)
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from backend.app.core.database import get_db
from backend.app.core.config import settings

router = APIRouter()

# ---- Password hashing ----
# Using bcrypt directly because passlib is incompatible with bcrypt >= 4.1.0

# ---- OAuth2 scheme (reads Bearer token from Authorization header) ----
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ---- Pydantic Schemas ----

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RecruiterProfile(BaseModel):
    user_id: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime


# ---- Helpers ----

def _hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


def _create_access_token(user_id: str, email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Dependency: validates JWT and returns the current recruiter.
    Use with: Depends(get_current_user) on protected endpoints.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    result = await db.execute(
        text("SELECT user_id, email, full_name, role, is_active FROM users WHERE user_id = :uid"),
        {"uid": user_id},
    )
    user = result.mappings().first()
    if not user or not user["is_active"]:
        raise credentials_exc
    return dict(user)


async def require_recruiter(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency: ensures user has recruiter or admin role."""
    if current_user["role"] not in ("recruiter", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter or admin role required",
        )
    return current_user


# ---- Endpoints ----

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Public recruiter self-registration.
    Creates account and immediately returns a JWT so the user is logged in.
    """
    # Check if email already taken
    existing = await db.execute(
        text("SELECT user_id FROM users WHERE email = :email"),
        {"email": payload.email},
    )
    if existing.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters.",
        )

    user_id = str(uuid.uuid4())
    hashed = _hash_password(payload.password)

    await db.execute(
        text("""
            INSERT INTO users (user_id, email, hashed_password, full_name, role, is_active)
            VALUES (:uid, :email, :hashed, :full_name, 'recruiter', TRUE)
        """),
        {
            "uid": user_id,
            "email": payload.email,
            "hashed": hashed,
            "full_name": payload.full_name,
        },
    )
    await db.commit()

    token = _create_access_token(user_id, payload.email, "recruiter")
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Login with email + password. Returns a JWT access token.
    Uses OAuth2 password form (compatible with Swagger UI's 'Authorize' button).
    """
    result = await db.execute(
        text("SELECT user_id, email, hashed_password, role, is_active FROM users WHERE email = :email"),
        {"email": form_data.username},  # OAuth2 form uses 'username' field for email
    )
    user = result.mappings().first()

    if not user or not _verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Contact support.",
        )

    token = _create_access_token(str(user["user_id"]), user["email"], user["role"])
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=RecruiterProfile)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Returns the authenticated recruiter's profile."""
    return current_user
