"""Supabase JWT verification + current-user dependency.

The browser sends `Authorization: Bearer <supabase access token>`. We verify
the token against Supabase Auth's `/user` endpoint (the source of truth — no
local JWT parsing, so revoked or expired tokens fail immediately) and map the
caller to a `profiles` row, creating it on first sign-in.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.database.models import Profile
from app.database.supabase import create_admin_client

# Auto-error must be off: a missing header is expected and handled below so we
# can return our own 401 shape before any retrieval or LLM work happens.
_bearer = HTTPBearer(auto_error=False)

_engine = create_async_engine(settings.sqlalchemy_database_url)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def _get_session() -> AsyncSession:
    async with _session_factory() as session:
        yield session


GetSession = Annotated[AsyncSession, Depends(_get_session)]


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _verify_token(token: str) -> tuple[UUID, str]:
    """Check the JWT against Supabase Auth; return (user_id, email).

    Raises on any failure — the 401 mapping is get_current_user's job.
    """
    # Admin client bypasses RLS and accepts an explicit jwt, avoiding any
    # session lookup against the anon key.
    admin = await create_admin_client()
    auth_user = await admin.auth.get_user(token)
    if auth_user is None:
        raise ValueError("Supabase Auth returned no user")
    return UUID(auth_user.user.id), auth_user.user.email or ""


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: GetSession,
) -> CurrentUser:
    """Verify the Supabase JWT and ensure a profiles row exists for it.

    Raises 401 for missing/malformed/invalid tokens — always before any
    retrieval or LLM work, since every protected route depends on this.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Missing bearer token")

    try:
        user_id, email = await _verify_token(credentials.credentials)
    except Exception as exc:
        # AuthApiError (invalid/expired JWT, 4xx from /auth/v1/user) and any
        # transport failure both mean "cannot authenticate this caller" —
        # never a 500, and never a leak of Supabase error details.
        raise _unauthorized("Invalid or expired token") from exc

    profile = await session.get(Profile, user_id)
    if profile is None:
        # First sign-in: create the profile with the service role, which
        # bypasses the (intentionally insert-less) profiles RLS policies.
        profile = Profile(id=user_id, email=email)
        session.add(profile)
        await session.commit()
    elif profile.email != email:
        profile.email = email
        await session.commit()

    return CurrentUser(id=profile.id, email=profile.email)
