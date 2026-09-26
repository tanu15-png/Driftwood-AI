"""Model + migration wiring tests. No network, no DB."""

from pathlib import Path

from sqlalchemy.schema import CreateIndex, CreateTable

import app.database.models  # noqa: F401  (importing registers all tables)
from app.database import Base
from app.database.models.constants import EMBEDDING_DIMENSIONS

_MIGRATION_FILE = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "2026_09_25-0001_initial_schema.py"
)


def test_embedding_dimensions_constant_matches_1536() -> None:
    assert EMBEDDING_DIMENSIONS == 1536


def test_document_chunk_declares_retrieval_indexes() -> None:
    indexes = Base.metadata.tables["document_chunks"].indexes
    index_names = {i.name for i in indexes}
    assert "ix_document_chunks_embedding_hnsw" in index_names
    assert "ix_document_chunks_search_vector_gin" in index_names
    assert "ix_document_chunks_metadata_gin" in index_names


def test_hnsw_index_targets_embedding_with_cosine_ops() -> None:
    indexes = Base.metadata.tables["document_chunks"].indexes
    hnsw = next(i for i in indexes if i.name == "ix_document_chunks_embedding_hnsw")
    assert list(hnsw.columns.keys()) == ["embedding"]
    assert hnsw.dialect_options["postgresql"]["using"] == "hnsw"
    assert hnsw.dialect_options["postgresql"]["ops"] == {
        "embedding": "vector_cosine_ops"
    }


def test_all_six_tables_registered() -> None:
    expected = {
        "profiles",
        "chat_threads",
        "chat_messages",
        "message_citations",
        "source_documents",
        "document_chunks",
    }
    assert set(Base.metadata.tables) == expected


def test_migration_file_covers_all_tables() -> None:
    migration_source = _MIGRATION_FILE.read_text()
    for table in Base.metadata.tables:
        assert f'"{table}"' in migration_source, f"missing table {table}"


def test_model_ddl_compiles_against_postgres() -> None:
    from sqlalchemy.dialects import postgresql

    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert "CREATE TABLE" in ddl
        for index in table.indexes:
            ddl = str(CreateIndex(index).compile(dialect=dialect))
            assert "CREATE INDEX" in ddl
