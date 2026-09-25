"""Org-scoped SmartOps offering sync columns.

Revision ID: 035
Revises: 034
Create Date: 2026-09-25 20:50:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing

revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "offerings" not in tables:
        return

    add_column_if_missing("offerings", sa.Column("offering_id", sa.String(64), nullable=True))
    add_column_if_missing(
        "offerings",
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organizations.org_id"),
            nullable=True,
        ),
    )
    add_column_if_missing("offerings", sa.Column("smartops_offering_id", sa.String(128), nullable=True))
    add_column_if_missing("offerings", sa.Column("file_format", sa.String(16), nullable=True))
    add_column_if_missing("offerings", sa.Column("file_name", sa.String(500), nullable=True))
    add_column_if_missing("offerings", sa.Column("file_url", sa.Text(), nullable=True))

    bind.execute(
        text(
            "UPDATE offerings SET offering_id = 'ls_off_' || CAST(id AS TEXT) "
            "WHERE offering_id IS NULL OR offering_id = ''"
        )
    )

    existing = {ix["name"] for ix in inspect(bind).get_indexes("offerings")}
    if "ix_offerings_organization_id" not in existing:
        op.create_index("ix_offerings_organization_id", "offerings", ["organization_id"])
    if "ix_offerings_offering_id" not in existing:
        op.create_index("ix_offerings_offering_id", "offerings", ["offering_id"], unique=True)
    if "uq_offerings_smartops_id" not in existing:
        op.create_index(
            "uq_offerings_smartops_id",
            "offerings",
            ["organization_id", "smartops_offering_id"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "offerings" not in tables:
        return
    existing = {ix["name"] for ix in inspect(bind).get_indexes("offerings")}
    for name in ("uq_offerings_smartops_id", "ix_offerings_offering_id", "ix_offerings_organization_id"):
        if name in existing:
            op.drop_index(name, table_name="offerings")
    for col in ("file_url", "file_name", "file_format", "smartops_offering_id", "organization_id", "offering_id"):
        cols = {c["name"] for c in inspect(bind).get_columns("offerings")}
        if col in cols:
            op.drop_column("offerings", col)
