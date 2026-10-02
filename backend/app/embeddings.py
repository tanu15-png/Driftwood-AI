"""Local CPU embeddings shared by corpus intake and retrieval."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from fastembed import TextEmbedding
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from app.config import settings
from app.database.models.constants import EMBEDDING_DIMENSIONS

MODEL_TOKEN_LIMIT = 512
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class BgeTokenizer(BaseTokenizer):
    tokenizer: Any
    max_tokens: int

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False).ids)

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self) -> Callable[[str], int]:
        return self.count_tokens


def create_tokenizer(max_tokens: int = 480, *, download: bool = False) -> BgeTokenizer:
    path = hf_hub_download(
        repo_id=settings.embedding_model,
        filename="tokenizer.json",
        cache_dir=str(settings.embedding_cache_dir / "tokenizer"),
        local_files_only=not download,
    )
    tokenizer = Tokenizer.from_file(path)
    # Count the whole passage so overlong inputs cannot appear to fit.
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return BgeTokenizer(tokenizer=tokenizer, max_tokens=max_tokens)


@dataclass
class LocalEmbeddingModel:
    encoder: TextEmbedding
    tokenizer: BaseTokenizer


def create_model(*, download: bool = False) -> LocalEmbeddingModel:
    return LocalEmbeddingModel(
        encoder=TextEmbedding(
            model_name=settings.embedding_model,
            cache_dir=str(settings.embedding_cache_dir),
            threads=2,
            providers=["CPUExecutionProvider"],
            local_files_only=not download,
        ),
        tokenizer=create_tokenizer(download=download),
    )


def embed_texts(model: LocalEmbeddingModel, texts: list[str]) -> list[list[float]]:
    # Reserve CLS/SEP tokens; never allow the runtime to silently truncate.
    for text in texts:
        if model.tokenizer.count_tokens(text) > MODEL_TOKEN_LIMIT - 2:
            raise ValueError("Embedding input exceeds 510 tokens; re-chunk the filing.")
    vectors = [vector.tolist() for vector in model.encoder.embed(texts, batch_size=32)]
    if len(vectors) != len(texts) or any(
        len(vector) != EMBEDDING_DIMENSIONS for vector in vectors
    ):
        raise RuntimeError("Local embedding output does not match the database dimensions.")
    return vectors


def embed_query_sync(model: LocalEmbeddingModel, query: str) -> list[float]:
    return embed_texts(model, [QUERY_INSTRUCTION + query])[0]


async def embed_query(model: LocalEmbeddingModel, query: str) -> list[float]:
    # Tokenization and CPU inference must not block the request event loop.
    return await asyncio.to_thread(embed_query_sync, model, query)


if __name__ == "__main__":
    model = create_model(download=True)
    vectors = embed_texts(model, ["Apple revenue", "NVIDIA data center GPUs"])
    print(f"Local CPU model ready: {settings.embedding_model}, {len(vectors[0])} dimensions")
