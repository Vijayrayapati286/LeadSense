"""Drop duplicate first_name/last_name from icp_records (name is enough).

Revision ID: 034
Revises: 033
Create Date: 2026-09-25 12:40:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing, drop_column_if_exists

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    drop_column_if_exists("icp_records", "first_name")
    drop_column_if_exists("icp_records", "last_name")


def downgrade() -> None:
    add_column_if_missing("icp_records", sa.Column("first_name", sa.String(length=255), nullable=True))
    add_column_if_missing("icp_records", sa.Column("last_name", sa.String(length=255), nullable=True))
