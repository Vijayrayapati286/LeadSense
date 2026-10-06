"""Add download_url to offering_documents for SmartOps presigned links.

Revision ID: 047
Revises: 046
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing, drop_column_if_exists

revision: str = "047"
down_revision: Union[str, None] = "046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "offering_documents",
        sa.Column("download_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    drop_column_if_exists("offering_documents", "download_url")
