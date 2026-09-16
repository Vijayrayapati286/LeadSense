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


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("org_id", sa.String(length=50), nullable=False),
        sa.Column("org_name", sa.String(length=255), nullable=False),
        sa.Column("org_type", sa.String(length=50), nullable=False),
        sa.Column("integration_token", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("org_id"),
        sa.UniqueConstraint("integration_token"),
    )
    op.create_index("ix_organizations_integration_token", "organizations", ["integration_token"])

    op.add_column("users", sa.Column("org_id", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("role", sa.String(length=50), nullable=False, server_default="USER"))
    op.add_column("users", sa.Column("status", sa.String(length=50), nullable=False, server_default="ACTIVE"))
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])
    op.create_foreign_key("fk_users_org_id", "users", "organizations", ["org_id"], ["org_id"])

    for table in ("campaigns", "recipients", "mailers", "recipient_groups", "tags"):
        op.add_column(table, sa.Column("org_id", sa.String(length=50), nullable=True))
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])
        op.create_foreign_key(f"fk_{table}_org_id", table, "organizations", ["org_id"], ["org_id"])

    # Allow same list/tag names across tenants
    try:
        op.drop_constraint("recipient_groups_name_key", "recipient_groups", type_="unique")
    except Exception:
        pass
    try:
        op.drop_index("ix_recipient_groups_name", table_name="recipient_groups")
    except Exception:
        pass
    try:
        op.drop_constraint("tags_name_key", "tags", type_="unique")
    except Exception:
        pass
    try:
        op.drop_index("ix_tags_name", table_name="tags")
    except Exception:
        pass

    op.create_index("ix_recipient_groups_name", "recipient_groups", ["name"])
    op.create_index("ix_tags_name", "tags", ["name"])
    op.create_unique_constraint("uq_recipient_groups_org_name", "recipient_groups", ["org_id", "name"])
    op.create_unique_constraint("uq_tags_org_name", "tags", ["org_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_tags_org_name", "tags", type_="unique")
    op.drop_constraint("uq_recipient_groups_org_name", "recipient_groups", type_="unique")

    for table in ("tags", "recipient_groups", "mailers", "recipients", "campaigns"):
        op.drop_constraint(f"fk_{table}_org_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_org_id", table_name=table)
        op.drop_column(table, "org_id")

    op.drop_constraint("fk_users_org_id", "users", type_="foreignkey")
    op.drop_index("ix_users_org_id", table_name="users")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "status")
    op.drop_column("users", "role")
    op.drop_column("users", "org_id")

    op.drop_index("ix_organizations_integration_token", table_name="organizations")
    op.drop_table("organizations")
