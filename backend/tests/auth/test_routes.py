"""Route tests for GET /me — dependency overrides only. No network, no DB."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import CurrentUser, get_current_user
from app.main import app

_USER_ID = uuid4()


@pytest.fixture()
def authenticated_client() -> TestClient:
    user = CurrentUser(id=_USER_ID, email="analyst@example.com")
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_me_returns_current_user(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/me")

    assert response.status_code == 200
    assert response.json() == {"id": str(_USER_ID), "email": "analyst@example.com"}


def test_me_without_token_returns_401() -> None:
    client = TestClient(app)

    response = client.get("/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"
    assert response.headers["www-authenticate"] == "Bearer"
