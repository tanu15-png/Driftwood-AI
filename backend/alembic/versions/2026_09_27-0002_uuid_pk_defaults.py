"""chat/message/document UUID PKs: add missing gen_random_uuid() defaults

Revision ID: 0002_uuid_pk_defaults
Revises: 0001_initial_schema
Create Date: 2026-09-27

The initial migration created these primary keys without a server default,
while app/database/models declares `server_default=gen_random_uuid()` — any
insert that omits `id` (new threads, messages, ingested documents) failed with
NotNullViolation. profiles is unaffected: its id always comes from Supabase
Auth and is set explicitly.

Statements are written out per table (no loop) so the model-sync tripwire
test can pin each one to its model's declared default. ALTER COLUMN ... SET
DEFAULT is metadata-only in Postgres: instant, no table rewrite, no lock
beyond a momentary ACCESS EXCLUSIVE.
Run from backend/: `uv run alembic upgrade head`.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_uuid_pk_defaults"
down_revision: str = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE chat_threads ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE chat_messages ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE source_documents ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE message_citations ALTER COLUMN id SET DEFAULT gen_random_uuid()")


def downgrade() -> None:
    op.execute("ALTER TABLE chat_threads ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER TABLE chat_messages ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER TABLE source_documents ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER TABLE message_citations ALTER COLUMN id DROP DEFAULT")
