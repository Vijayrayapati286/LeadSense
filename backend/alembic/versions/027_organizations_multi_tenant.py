"""Add organizations table and multi-tenant org_id columns.

Revision ID: 027
Revises: 026
Create Date: 2026-09-16 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG_TABLES = ("campaigns", "recipients", "mailers", "recipient_groups", "tags")


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name LIMIT 1"),
        {"name": name},
    ).first()
    return row is not None


def _run_ddl(stmt: str) -> None:
    """Run one DDL statement inside a SAVEPOINT so a failure cannot abort the outer txn."""
    conn = op.get_bind()
    with conn.begin_nested():
        conn.execute(sa.text(stmt))


def upgrade() -> None:
    _run_ddl(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            org_id VARCHAR(50) NOT NULL,
            org_name VARCHAR(255) NOT NULL,
            org_type VARCHAR(50) NOT NULL,
            integration_token VARCHAR(255) NOT NULL,
            status VARCHAR(50) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (org_id),
            UNIQUE (integration_token)
        )
        """
    )
    _run_ddl(
        "CREATE INDEX IF NOT EXISTS ix_organizations_integration_token "
        "ON organizations (integration_token)"
    )

    # users — may already be partially applied on UAT
    _run_ddl("ALTER TABLE users ADD COLUMN IF NOT EXISTS org_id VARCHAR(50)")
    _run_ddl(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) "
        "NOT NULL DEFAULT 'USER'"
    )
    _run_ddl(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(50) "
        "NOT NULL DEFAULT 'ACTIVE'"
    )
    _run_ddl(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ "
        "NOT NULL DEFAULT now()"
    )
    _run_ddl("CREATE INDEX IF NOT EXISTS ix_users_org_id ON users (org_id)")
    if not _constraint_exists("fk_users_org_id"):
        with op.get_bind().begin_nested():
            op.create_foreign_key(
                "fk_users_org_id", "users", "organizations", ["org_id"], ["org_id"]
            )

    for table in _ORG_TABLES:
        _run_ddl(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS org_id VARCHAR(50)")
        _run_ddl(f"CREATE INDEX IF NOT EXISTS ix_{table}_org_id ON {table} (org_id)")
        fk = f"fk_{table}_org_id"
        if not _constraint_exists(fk):
            with op.get_bind().begin_nested():
                op.create_foreign_key(
                    fk, table, "organizations", ["org_id"], ["org_id"]
                )

    # Drop old unique indexes/constraints safely (IF EXISTS + SAVEPOINT per step)
    for stmt in (
        "ALTER TABLE recipient_groups DROP CONSTRAINT IF EXISTS recipient_groups_name_key",
        "DROP INDEX IF EXISTS ix_recipient_groups_name",
        "ALTER TABLE tags DROP CONSTRAINT IF EXISTS tags_name_key",
        "DROP INDEX IF EXISTS ix_tags_name",
    ):
        _run_ddl(stmt)

    _run_ddl(
        "CREATE INDEX IF NOT EXISTS ix_recipient_groups_name ON recipient_groups (name)"
    )
    _run_ddl("CREATE INDEX IF NOT EXISTS ix_tags_name ON tags (name)")

    if not _constraint_exists("uq_recipient_groups_org_name"):
        with op.get_bind().begin_nested():
            op.create_unique_constraint(
                "uq_recipient_groups_org_name", "recipient_groups", ["org_id", "name"]
            )
    if not _constraint_exists("uq_tags_org_name"):
        with op.get_bind().begin_nested():
            op.create_unique_constraint(
                "uq_tags_org_name", "tags", ["org_id", "name"]
            )


def downgrade() -> None:
    for stmt in (
        "ALTER TABLE tags DROP CONSTRAINT IF EXISTS uq_tags_org_name",
        "ALTER TABLE recipient_groups DROP CONSTRAINT IF EXISTS uq_recipient_groups_org_name",
    ):
        _run_ddl(stmt)

    for table in ("tags", "recipient_groups", "mailers", "recipients", "campaigns"):
        _run_ddl(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_org_id")
        _run_ddl(f"DROP INDEX IF EXISTS ix_{table}_org_id")
        _run_ddl(f"ALTER TABLE {table} DROP COLUMN IF EXISTS org_id")

    _run_ddl("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_org_id")
    _run_ddl("DROP INDEX IF EXISTS ix_users_org_id")
    _run_ddl("ALTER TABLE users DROP COLUMN IF EXISTS updated_at")
    _run_ddl("ALTER TABLE users DROP COLUMN IF EXISTS status")
    _run_ddl("ALTER TABLE users DROP COLUMN IF EXISTS role")
    _run_ddl("ALTER TABLE users DROP COLUMN IF EXISTS org_id")

    _run_ddl("DROP INDEX IF EXISTS ix_organizations_integration_token")
    _run_ddl("DROP TABLE IF EXISTS organizations")
