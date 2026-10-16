"""Track when a bulk job's verified contacts were added to ICP.

Revision ID: 049
Revises: 048
Create Date: 2026-10-16
"""

from typing import Sequence, Union

import sqlalchemy as sa

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing, drop_column_if_exists

revision: str = "049"
down_revision: Union[str, None] = "048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "linkedin_bulk_jobs",
        sa.Column("icp_added_at", sa.DateTime(timezone=True), nullable=True),
    )
    add_column_if_missing(
        "linkedin_bulk_jobs",
        sa.Column("icp_added_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    drop_column_if_exists("linkedin_bulk_jobs", "icp_added_count")
    drop_column_if_exists("linkedin_bulk_jobs", "icp_added_at")
