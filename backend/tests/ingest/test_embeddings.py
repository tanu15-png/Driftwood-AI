"""Local embedding boundary checks without downloading or running a model."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from app.embeddings import (
    QUERY_INSTRUCTION,
    LocalEmbeddingModel,
    embed_query,
    embed_texts,
)


def test_tokenizer_counts_full_input_without_truncation(monkeypatch, tmp_path):
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace

    from app import embeddings

    raw = Tokenizer(WordLevel({"[UNK]": 0, "revenue": 1}, unk_token="[UNK]"))
    raw.pre_tokenizer = Whitespace()
    raw.enable_truncation(5)
    path = tmp_path / "tokenizer.json"
    raw.save(str(path))
    monkeypatch.setattr(embeddings, "hf_hub_download", lambda **kwargs: str(path))
    tokenizer = embeddings.create_tokenizer()
    assert tokenizer.count_tokens("revenue " * 600) == 600
    assert tokenizer.get_max_tokens() == 480


def test_overlong_input_is_rejected_before_inference():
    model = LocalEmbeddingModel(Mock(), SimpleNamespace(count_tokens=lambda text: 511))
    with pytest.raises(ValueError, match="510"):
        embed_texts(model, ["long passage"])
    model.encoder.embed.assert_not_called()


def test_wrong_dimensions_are_rejected():
    encoder = Mock()
    encoder.embed.return_value = [np.zeros(1536)]
    model = LocalEmbeddingModel(encoder, SimpleNamespace(count_tokens=lambda text: 10))
    with pytest.raises(RuntimeError, match="dimensions"):
        embed_texts(model, ["passage"])


async def test_query_instruction_and_vector_order():
    encoder = Mock()
    encoder.embed.return_value = [np.ones(384)]
    model = LocalEmbeddingModel(encoder, SimpleNamespace(count_tokens=lambda text: 10))
    vector = await embed_query(model, "Apple revenue")
    assert vector == [1.0] * 384
    encoder.embed.assert_called_once_with([QUERY_INSTRUCTION + "Apple revenue"], batch_size=32)
