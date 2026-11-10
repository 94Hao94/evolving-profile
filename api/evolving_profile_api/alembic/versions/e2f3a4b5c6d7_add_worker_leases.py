"""Add leases and fencing columns for distributed worker claims.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-11-07
"""

from collections.abc import Sequence

from alembic import context, op

from evolving_profile_api.alembic._dialect import run_for_dialect

revision: str = "e2f3a4b5c6d7"
down_revision: str | Sequence[str] | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _schema_prefix() -> str:
    schema = context.config.get_main_option("target_schema")
    return f'"{schema}".' if schema else ""


def _pg_upgrade() -> None:
    schema = _schema_prefix()
    op.execute(f"ALTER TABLE {schema}async_operations ADD COLUMN IF NOT EXISTS lease_id TEXT")
    op.execute(
        f"ALTER TABLE {schema}async_operations "
        f"ADD COLUMN IF NOT EXISTS claim_version INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(f"ALTER TABLE {schema}async_operations ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ")
    op.execute(f"ALTER TABLE {schema}async_operations ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS idx_async_operations_lease_expiry "
        f"ON {schema}async_operations (lease_expires_at) "
        f"WHERE status = 'processing' AND lease_expires_at IS NOT NULL"
    )


def _pg_downgrade() -> None:
    schema = _schema_prefix()
    op.execute(f"DROP INDEX IF EXISTS {schema}idx_async_operations_lease_expiry")
    for column in ("heartbeat_at", "lease_expires_at", "claim_version", "lease_id"):
        op.execute(f"ALTER TABLE {schema}async_operations DROP COLUMN IF EXISTS {column}")


def _oracle_upgrade() -> None:
    # Oracle has no IF NOT EXISTS for columns. The migration runner applies this
    # once per schema, so a regular ADD is sufficient for supported installs.
    op.execute(
        "ALTER TABLE async_operations ADD ("
        "lease_id VARCHAR2(128), "
        "claim_version NUMBER(10) DEFAULT 0 NOT NULL, "
        "lease_expires_at TIMESTAMP WITH TIME ZONE, "
        "heartbeat_at TIMESTAMP WITH TIME ZONE"
        ")"
    )
    op.execute(
        "CREATE INDEX idx_async_operations_lease_expiry "
        "ON async_operations (lease_expires_at)"
    )


def _oracle_downgrade() -> None:
    op.execute("DROP INDEX idx_async_operations_lease_expiry")
    op.execute(
        "ALTER TABLE async_operations DROP COLUMN lease_id"
    )
    op.execute("ALTER TABLE async_operations DROP COLUMN claim_version")
    op.execute("ALTER TABLE async_operations DROP COLUMN lease_expires_at")
    op.execute("ALTER TABLE async_operations DROP COLUMN heartbeat_at")


def upgrade() -> None:
    run_for_dialect(pg=_pg_upgrade, oracle=_oracle_upgrade)


def downgrade() -> None:
    run_for_dialect(pg=_pg_downgrade, oracle=_oracle_downgrade)
