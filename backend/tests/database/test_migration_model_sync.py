"""Tripwire against model/migration drift on UUID primary keys.

The 0002 incident: models declared `server_default=gen_random_uuid()` but the
initial migration created the columns without it, so inserts omitting `id`
failed at runtime with NotNullViolation. This test pins the contract: every
model whose `id` has that server default must be covered by a migration that
also mentions `gen_random_uuid()` for that table.
"""

from pathlib import Path

from app.database.models import Base

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _tables_with_uuid_default_models() -> set[str]:
    tables = set()
    for table in Base.metadata.tables.values():
        id_column = table.columns["id"]
        if id_column.server_default is not None and "gen_random_uuid" in str(
            id_column.server_default.arg
        ):
            tables.add(table.name)
    return tables


def test_migrations_cover_every_model_uuid_default() -> None:
    migration_sql = "\n".join(
        path.read_text() for path in _VERSIONS_DIR.glob("*.py")
    )
    for table in sorted(_tables_with_uuid_default_models()):
        assert f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT gen_random_uuid()" in (
            migration_sql
        ), (
            f"{table}.id declares a gen_random_uuid() server default in the "
            "models, but no migration adds it — inserts omitting id will fail "
            "with NotNullViolation (see 0002_uuid_pk_defaults)."
        )
