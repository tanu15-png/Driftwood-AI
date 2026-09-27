"""HTTP auth routes: the `GET /me` probe for the frontend auth round-trip."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user

router = APIRouter(tags=["auth"])


class MeResponse(BaseModel):
    id: UUID
    email: str


@router.get("/me")
async def me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> MeResponse:
    """Probe: proves the browser's Supabase JWT verifies against FastAPI."""
    return MeResponse(id=user.id, email=user.email)
