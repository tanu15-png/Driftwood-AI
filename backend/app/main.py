import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.assistant.agent import create_agent, create_gemini_model
from app.assistant.runtime import AssistantRuntime
from app.auth.routes import router as auth_router
from app.chat.routes import router as chat_router
from app.config import settings
from app.embeddings import create_model


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    model = create_gemini_model()
    try:
        async with create_agent(model) as agent:
            application.state.assistant = AssistantRuntime(
                agent, await asyncio.to_thread(create_model)
            )
            yield
    finally:
        await model.client.aio.aclose()


app = FastAPI(title="Document Copilot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
