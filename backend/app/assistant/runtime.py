"""The application owns long-lived model clients and the local CPU model."""

from dataclasses import dataclass

from fastapi import Request
from pydantic_ai import Agent

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.embeddings import LocalEmbeddingModel


@dataclass
class AssistantRuntime:
    agent: Agent[DocumentAgentDeps, GroundedAnswer]
    embed_model: LocalEmbeddingModel


def get_runtime(request: Request) -> AssistantRuntime:
    return request.app.state.assistant
