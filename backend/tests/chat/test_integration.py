"""Live auth and persisted streaming turn; temporary accounts are cleaned up.

Run explicitly with pytest -m integration. Admin-created confirmed accounts
avoid sending confirmation emails or changing the project's auth settings.
"""

import asyncio
import json
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClientOptions, create_async_client

from app.assistant.agent import create_agent, create_gemini_model
from app.assistant.runtime import AssistantRuntime, get_runtime
from app.auth.dependencies import _engine
from app.config import settings
from app.database.models import DocumentChunk, MessageCitation, Profile
from app.database.supabase import create_admin_client
from app.embeddings import create_model
from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_live_auth_stream_and_history() -> None:
    model = create_gemini_model()
    runtime = AssistantRuntime(create_agent(model), await asyncio.to_thread(create_model))
    app.dependency_overrides[get_runtime] = lambda: runtime
    admin = await create_admin_client()
    users = []
    try:
        headers = []
        for _ in range(2):
            email = f"copilot-check-{uuid4().hex}@example.com"
            password = uuid4().hex + "aA1!"
            created = await admin.auth.admin.create_user(
                {"email": email, "password": password, "email_confirm": True}
            )
            users.append(UUID(created.user.id))
            client = await create_async_client(
                settings.supabase_url,
                settings.supabase_anon_key,
                AsyncClientOptions(auto_refresh_token=False, persist_session=False),
            )
            signed_in = await client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            headers.append({"Authorization": f"Bearer {signed_in.session.access_token}"})

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as api:
            assert (await api.get("/health")).json() == {"status": "ok"}
            assert (await api.get("/me")).status_code == 401
            assert (
                await api.get("/me", headers={"Authorization": "Bearer invalid"})
            ).status_code == 401
            me = await api.get("/me", headers=headers[0])
            assert me.status_code == 200
            assert me.json()["id"] == str(users[0])
            thread = await api.post("/threads", headers=headers[0])
            assert thread.status_code == 201
            thread_id = thread.json()["id"]
            history_url = f"/threads/{thread_id}/messages"
            assert (await api.get(history_url, headers=headers[1])).status_code == 403
            response = await api.post(
                "/chat/stream",
                headers=headers[0],
                json={
                    "threadId": thread_id,
                    "messages": [{
                        "id": "user-turn",
                        "role": "user",
                        "parts": [{"type": "text", "text": "What were Apple's total net sales in fiscal 2024? Include the disclosed value and units."}],
                    }],
                },
            )
            assert response.status_code == 200
            assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
            events = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
            assert events[-1] == "[DONE]"
            assert any(json.loads(event)["type"] == "text-delta" for event in events[:-1])
            history = await api.get(history_url, headers=headers[0])
            assert history.status_code == 200
            assert [message["role"] for message in history.json()] == ["user", "assistant"]
            assistant = history.json()[1]
            parts = {part["type"]: part for part in assistant["parts"]}
            assert parts["data-grounding"]["data"]["status"] == "supported"
            assert parts["data-citations"]["data"]
            assert parts["data-sources"]["data"]
            assert assistant["metadata"]["usage"]["input_tokens"] > 0
            async with AsyncSession(_engine) as session:
                citations = (await session.execute(
                    select(MessageCitation, DocumentChunk)
                    .join(DocumentChunk, MessageCitation.chunk_id == DocumentChunk.id)
                    .where(MessageCitation.message_id == UUID(assistant["id"]))
                )).all()
                assert len(citations) == len(parts["data-citations"]["data"])
                for citation, chunk in citations:
                    assert " ".join(citation.excerpt.split()) in " ".join(chunk.chunk_text.split())
                    assert citation.document_id == chunk.document_id
            outside = await api.post("/chat/stream", headers=headers[0], json={
                "threadId": thread_id,
                "messages": [{"id": "outside", "role": "user", "parts": [{
                    "type": "text", "text": "What is the current weather on Mars? Answer only if the filing corpus states it.",
                }]}],
            })
            assert outside.status_code == 200
            outside_events = [json.loads(line[6:]) for line in outside.text.splitlines()
                              if line.startswith("data: ") and line != "data: [DONE]"]
            assert next(e for e in outside_events if e["type"] == "data-grounding")["data"]["status"] == "insufficient_evidence"
            assert next(e for e in outside_events if e["type"] == "data-citations")["data"] == []
            assert next(e for e in outside_events if e["type"] == "data-sources")["data"] == []
            replay = (await api.get(history_url, headers=headers[0])).json()
            assert len(replay) == 4
            assert replay[-1]["parts"][0]["text"].startswith("The filing corpus does not contain enough evidence")
            listed = await api.get("/threads", headers=headers[0])
            assert any(t["id"] == thread_id for t in listed.json())
    finally:
        app.dependency_overrides.pop(get_runtime, None)
        await model.client.aio.aclose()
        async with AsyncSession(_engine) as session:
            await session.execute(delete(Profile).where(Profile.id.in_(users)))
            await session.commit()
        for user_id in users:
            await admin.auth.admin.delete_user(str(user_id))
        await _engine.dispose()
