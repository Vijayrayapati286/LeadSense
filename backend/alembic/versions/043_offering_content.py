"""Store SmartOps offering file text on offerings + offering_documents.

Revision ID: 043
Revises: 042
Create Date: 2026-09-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing, drop_column_if_exists

revision: str = "043"
down_revision: Union[str, None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing("offerings", sa.Column("content", sa.Text(), nullable=True))
    add_column_if_missing("offering_documents", sa.Column("content", sa.Text(), nullable=True))


def downgrade() -> None:
    drop_column_if_exists("offering_documents", "content")
    drop_column_if_exists("offerings", "content")
