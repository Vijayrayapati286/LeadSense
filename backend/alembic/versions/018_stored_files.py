"""Create stored_files table for S3 object metadata.

Revision ID: 018
Revises: 017
Create Date: 2026-08-26 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("s3_bucket", sa.String(length=255), nullable=False),
        sa.Column("s3_key", sa.String(length=1000), nullable=False),
        sa.Column("mime_type", sa.String(length=200), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="uploaded"),
        sa.Column("content_version", sa.String(length=128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stored_files_batch_id", "stored_files", ["batch_id"])
    op.create_index("ix_stored_files_user_id", "stored_files", ["user_id"])
    op.create_index("ix_stored_files_batch_type", "stored_files", ["batch_id", "file_type"])
    op.create_index("ix_stored_files_user_batch", "stored_files", ["user_id", "batch_id"])
    op.create_index("ix_stored_files_s3_key", "stored_files", ["s3_key"])


def downgrade() -> None:
    op.drop_index("ix_stored_files_s3_key", table_name="stored_files")
    op.drop_index("ix_stored_files_user_batch", table_name="stored_files")
    op.drop_index("ix_stored_files_batch_type", table_name="stored_files")
    op.drop_index("ix_stored_files_user_id", table_name="stored_files")
    op.drop_index("ix_stored_files_batch_id", table_name="stored_files")
    op.drop_table("stored_files")
