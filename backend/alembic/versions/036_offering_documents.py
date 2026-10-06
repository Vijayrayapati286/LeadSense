"""Multi-doc SmartOps offerings: doc_count + offering_documents.

Revision ID: 036
Revises: 035
Create Date: 2026-09-25 22:30:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing

revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "offerings" in tables:
        add_column_if_missing(
            "offerings",
            sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
        )

    if "offering_documents" not in tables:
        op.create_table(
            "offering_documents",
            sa.Column("doc_id", sa.String(128), primary_key=True),
            sa.Column("offering_id", sa.String(64), nullable=False),
            sa.Column("file_name", sa.String(500), nullable=False),
            sa.Column("file_format", sa.String(16), nullable=False),
            sa.Column("s3_key", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["offering_id"], ["offerings.offering_id"], ondelete="CASCADE"),
        )
        op.create_index("idx_offering_docs_offering", "offering_documents", ["offering_id"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "offering_documents" in tables:
        op.drop_index("idx_offering_docs_offering", table_name="offering_documents")
        op.drop_table("offering_documents")
    if "offerings" in tables:
        cols = {c["name"] for c in inspect(bind).get_columns("offerings")}
        if "doc_count" in cols:
            op.drop_column("offerings", "doc_count")
