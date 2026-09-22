"""Add organizations.client_name for tenant client display name.

Revision ID: 034
Revises: 033
Create Date: 2026-09-22 12:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "organizations" in tables:
        cols = {c["name"] for c in inspect(bind).get_columns("organizations")}
        if "client_name" not in cols:
            op.add_column("organizations", sa.Column("client_name", sa.String(255), nullable=True))
    if "user_email_verifications" in tables and bind.dialect.name != "sqlite":
        bind.execute(text("ALTER TABLE user_email_verifications ALTER COLUMN code TYPE VARCHAR(128)"))


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "organizations" in tables:
        cols = {c["name"] for c in inspect(bind).get_columns("organizations")}
        if "client_name" in cols:
            op.drop_column("organizations", "client_name")
