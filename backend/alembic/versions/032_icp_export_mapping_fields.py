"""Add CRM export mapping columns to icp_records.

Revision ID: 032
Revises: 031
Create Date: 2026-09-24 15:00:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing("icp_records", sa.Column("first_name", sa.String(length=255), nullable=True))
    add_column_if_missing("icp_records", sa.Column("last_name", sa.String(length=255), nullable=True))
    add_column_if_missing("icp_records", sa.Column("department", sa.String(length=255), nullable=True))
    add_column_if_missing("icp_records", sa.Column("phone", sa.String(length=100), nullable=True))
    add_column_if_missing("icp_records", sa.Column("city", sa.String(length=255), nullable=True))
    add_column_if_missing("icp_records", sa.Column("state", sa.String(length=255), nullable=True))
    add_column_if_missing("icp_records", sa.Column("country", sa.String(length=255), nullable=True))
    add_column_if_missing("icp_records", sa.Column("country_code", sa.String(length=16), nullable=True))
    add_column_if_missing(
        "icp_records", sa.Column("company_linkedin_url", sa.String(length=500), nullable=True)
    )
    add_column_if_missing("icp_records", sa.Column("company_city", sa.String(length=255), nullable=True))
    add_column_if_missing("icp_records", sa.Column("annual_revenue", sa.String(length=100), nullable=True))
    add_column_if_missing("icp_records", sa.Column("company_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in (
        "company_summary",
        "annual_revenue",
        "company_city",
        "company_linkedin_url",
        "country_code",
        "country",
        "state",
        "city",
        "phone",
        "department",
        "last_name",
        "first_name",
    ):
        try:
            op.drop_column("icp_records", col)
        except Exception:
            pass
