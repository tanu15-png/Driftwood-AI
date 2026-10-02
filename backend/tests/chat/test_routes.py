"""Route tests for threads/messages/stream. Dependency overrides; no DB."""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.assistant.outputs import Citation, GroundedAnswer, GroundedClaim, SourcePassage
from app.assistant.runtime import get_runtime
from app.auth.dependencies import CurrentUser, get_current_user
from app.chat import orchestrator
from app.chat import routes as chat_routes
from app.chat.orchestrator import PreparedTurn
from app.main import app

_USER = CurrentUser(id=uuid4(), email="analyst@example.com")


@pytest.fixture()
def client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_runtime] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


class ThreadOut:
    def __init__(self, id, title="t") -> None:
        self.id = id
        self.title = title
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)


class FakeChats:
    """Monkeypatch target standing in for app.database.chats."""

    def __init__(self, thread_id: UUID) -> None:
        self.thread_id = thread_id
        self.created_with = None
        self.persisted = None
        self.owned_calls = 0

    async def list_threads(self, session, user_id):
        return [ThreadOut(self.thread_id)]

    async def create_thread(self, session, user_id, title):
        self.created_with = (user_id, title)
        return ThreadOut(self.thread_id, title)

    async def get_owned_thread(self, session, user_id, thread_id):
        self.owned_calls += 1
        assert user_id == _USER.id
        return ThreadOut(thread_id)

    async def list_messages(self, session, thread_id):
        return []

    async def persist_turn(self, session, thread, user_message, assistant_message, citations=()):
        self.persisted = (user_message, assistant_message)
        self.citations = citations


@pytest.fixture()
def fake_chats(monkeypatch: pytest.MonkeyPatch) -> FakeChats:
    fake = FakeChats(uuid4())
    monkeypatch.setattr(chat_routes, "chats", fake)
    monkeypatch.setattr(orchestrator, "chats", fake)
    source = SourcePassage(
        id=uuid4(), document_id=uuid4(), chunk_text="Revenue grew.",
        ticker="AAPL", company="Apple", fiscal_year=2025, filing_type="10-K",
        filing_date="2025-10-31", source_url="https://www.sec.gov/filing",
    )

    async def prepare(*args):
        return PreparedTurn(GroundedAnswer(
            claims=[GroundedClaim(text="Revenue grew.", citation_ids=[1])],
            citations=[Citation(id=1, chunk_id=source.id, quote="Revenue grew.")],
            refusal_reason=None,
        ), [source], {"input_tokens": 10, "output_tokens": 5})

    monkeypatch.setattr(chat_routes, "prepare_turn", prepare)
    return fake


def test_list_threads_returns_owned(client, fake_chats) -> None:
    response = client.get("/threads")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == str(fake_chats.thread_id)


def test_create_thread_returns_201(client, fake_chats) -> None:
    response = client.post("/threads", json={"title": "Research"})
    assert response.status_code == 201
    assert response.json()["title"] == "Research"
    assert fake_chats.created_with == (_USER.id, "Research")


def test_create_thread_without_body(client, fake_chats) -> None:
    response = client.post("/threads")
    assert response.status_code == 201


def test_list_messages_requires_ownership(client, fake_chats) -> None:
    response = client.get(f"/threads/{fake_chats.thread_id}/messages")
    assert response.status_code == 200
    assert response.json() == []
    assert fake_chats.owned_calls == 1


def _stream_request(thread_id: UUID) -> dict:
    return {
        "threadId": str(thread_id),
        "messages": [
            {"id": "u1", "role": "user", "parts": [{"type": "text", "text": "hi"}]}
        ],
    }


def test_stream_persists_only_after_completion(client, fake_chats, monkeypatch) -> None:
    thread_id = fake_chats.thread_id

    with client.stream("POST", "/chat/stream", json=_stream_request(thread_id)) as response:
        assert response.status_code == 200
        assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(line.removeprefix("data: "))

    # Wire format: typed parts, then [DONE].
    types = [json.loads(e).get("type") for e in events[:-1]]
    assert types[0] == "start"
    assert "text-start" in types
    assert "text-delta" in types
    assert types[-2] == "finish-step"
    assert types[-1] == "finish"
    assert events[-1] == "[DONE]"
    deltas = "".join(
        json.loads(e).get("delta", "") for e in events[:-1] if "delta" in json.loads(e)
    )
    assert deltas.strip() == "Revenue grew. [1]"
    assert "source-url" in types
    assert "data-citations" in types
    assert "data-sources" in types

    # Persistence happens only after the stream finished (client.stream only
    # exits once the whole SSE body was consumed).
    user_message, assistant_message = fake_chats.persisted
    assert user_message.role == "user"
    assert user_message.content == "hi"
    assert assistant_message.role == "assistant"
    assert assistant_message.content == "Revenue grew. [1]"
    assert assistant_message.ui_message["metadata"]["usage"]["input_tokens"] == 10
    assert len(fake_chats.citations) == 1


def test_stream_unknown_message_shape_is_422(client, fake_chats, monkeypatch) -> None:
    payload = {"threadId": str(fake_chats.thread_id), "messages": [{"role": "assistant"}]}
    response = client.post("/chat/stream", json=payload)
    assert response.status_code == 422
    # Failed turns must not persist anything.
    assert fake_chats.persisted is None


def test_stream_empty_messages_is_422(client, fake_chats) -> None:
    response = client.post(
        "/chat/stream",
        json={"threadId": str(fake_chats.thread_id), "messages": []},
    )
    assert response.status_code == 422


def test_stream_requires_auth() -> None:
    client = TestClient(app)
    response = client.post(
        "/chat/stream", json=_stream_request(uuid4())
    )
    assert response.status_code == 401


def test_grounding_failure_is_json_error_before_stream(client, fake_chats, monkeypatch):
    async def reject(*args):
        raise HTTPException(502, "Grounding validation failed; no answer was produced.")

    monkeypatch.setattr(chat_routes, "prepare_turn", reject)
    response = client.post("/chat/stream", json=_stream_request(fake_chats.thread_id))
    assert response.status_code == 502
    assert response.headers["content-type"] == "application/json"
    assert fake_chats.persisted is None
