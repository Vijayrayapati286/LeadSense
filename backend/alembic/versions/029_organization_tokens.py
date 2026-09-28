"""Add organization_tokens table and organizations.created_by_user_id.

Revision ID: 029
Revises: 028
Create Date: 2026-09-17 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_organizations_created_by_user_id",
        "organizations",
        "users",
        ["created_by_user_id"],
        ["id"],
    )

    op.create_table(
        "organization_tokens",
        sa.Column("token_id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.org_id"]),
        sa.PrimaryKeyConstraint("token_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_organization_tokens_organization_id", "organization_tokens", ["organization_id"])
    op.create_index("ix_organization_tokens_token_hash", "organization_tokens", ["token_hash"])
    op.create_index("ix_organization_tokens_status", "organization_tokens", ["status"])


def downgrade() -> None:
    op.drop_index("ix_organization_tokens_status", table_name="organization_tokens")
    op.drop_index("ix_organization_tokens_token_hash", table_name="organization_tokens")
    op.drop_index("ix_organization_tokens_organization_id", table_name="organization_tokens")
    op.drop_table("organization_tokens")
    op.drop_constraint("fk_organizations_created_by_user_id", "organizations", type_="foreignkey")
    op.drop_column("organizations", "created_by_user_id")
