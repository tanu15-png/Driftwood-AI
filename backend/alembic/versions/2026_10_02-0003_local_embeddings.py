"""Replace Gemini vectors with local BGE vectors; preserve passage IDs and text.

Existing embeddings cannot be converted between models. The migration clears
them and rebuilds the vector index; corpus ingestion repopulates the vectors.
Downgrading also requires re-embedding with the former model.
"""

from alembic import op

revision = "0003_local_embeddings"
down_revision = "0002_uuid_pk_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX ix_document_chunks_embedding_hnsw")
    op.execute(
        "ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(384) "
        "USING NULL::vector(384)"
    )
    op.execute(
        "UPDATE document_chunks SET metadata = metadata - 'embedding_model' - 'embedding_dimensions'"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_document_chunks_embedding_hnsw")
    op.execute(
        "ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1536) "
        "USING NULL::vector(1536)"
    )
    op.execute(
        "UPDATE document_chunks SET metadata = metadata - 'embedding_model' - 'embedding_dimensions'"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
