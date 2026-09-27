"""Auth dependency unit tests. No network, no DB — everything mocked."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth import dependencies as deps
from app.auth.dependencies import CurrentUser, get_current_user
from app.database.models import Profile

_USER_ID = uuid4()


class FakeCredentials:
    def __init__(self, credentials: str | None) -> None:
        self.scheme = "bearer"
        self.credentials = credentials


class FakeAuthUser:
    def __init__(self, user_id: str, email: str | None) -> None:
        self.id = user_id
        self.email = email


class FakeUserResponse:
    def __init__(self, user: FakeAuthUser) -> None:
        self.user = user


class FakeSession:
    """Minimal AsyncSession stand-in: get() + tracked adds/commits."""

    def __init__(self, profile: Profile | None) -> None:
        self._profile = profile
        self.added: list[Profile] = []
        self.commit_count = 0

    async def get(self, model, key):
        assert model is Profile
        return self._profile

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commit_count += 1


@pytest.fixture()
def fake_supabase(monkeypatch: pytest.MonkeyPatch):
    """Patch token verification + admin client creation; returns call log."""

    class Log:
        def __init__(self) -> None:
            self.tokens: list[str] = []
            self.response: FakeUserResponse | None = FakeUserResponse(
                FakeAuthUser(str(_USER_ID), "analyst@example.com")
            )
            self.error: Exception | None = None

    log = Log()

    async def fake_verify(token: str):
        log.tokens.append(token)
        if log.error:
            raise log.error
        assert log.response is not None
        return _USER_ID, log.response.user.email or ""

    monkeypatch.setattr(deps, "_verify_token", fake_verify)
    return log


async def test_missing_header_returns_401(fake_supabase) -> None:
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(None, FakeSession(None))
    assert excinfo.value.status_code == 401
    assert excinfo.value.headers == {"WWW-Authenticate": "Bearer"}
    # No verification attempt, no Supabase call.
    assert fake_supabase.tokens == []


async def test_empty_token_returns_401(fake_supabase) -> None:
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(FakeCredentials(None), FakeSession(None))
    assert excinfo.value.status_code == 401
    assert fake_supabase.tokens == []


async def test_valid_token_creates_missing_profile(fake_supabase) -> None:
    session = FakeSession(None)
    user = await get_current_user(FakeCredentials("jwt-abc"), session)

    assert fake_supabase.tokens == ["jwt-abc"]
    assert user == CurrentUser(id=_USER_ID, email="analyst@example.com")
    assert [p.id for p in session.added] == [_USER_ID]
    assert session.commit_count == 1


async def test_valid_token_updates_stale_email(fake_supabase) -> None:
    stale = Profile(id=_USER_ID, email="old@example.com")
    session = FakeSession(stale)

    user = await get_current_user(FakeCredentials("jwt-abc"), session)

    assert user.email == "analyst@example.com"
    assert stale.email == "analyst@example.com"
    assert session.added == []
    assert session.commit_count == 1


async def test_known_profile_skips_write(fake_supabase) -> None:
    existing = Profile(id=_USER_ID, email="analyst@example.com")
    session = FakeSession(existing)

    await get_current_user(FakeCredentials("jwt-abc"), session)

    assert session.added == []
    assert session.commit_count == 0


async def test_verification_failure_maps_to_401(
    fake_supabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_supabase.error = RuntimeError("supabase down / bad jwt")

    class BoomSession:
        async def get(self, *args):
            raise AssertionError("DB must not be touched when auth fails")

    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(FakeCredentials("jwt-abc"), BoomSession())
    assert excinfo.value.status_code == 401
