"""Add company_location and export alias columns on icp_records.

Revision ID: 039
Revises: 038
Create Date: 2026-09-24 16:00:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing

revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "icp_records", sa.Column("company_location", sa.String(length=500), nullable=True)
    )
    add_column_if_missing("icp_records", sa.Column("contact_state", sa.String(length=255), nullable=True))
    add_column_if_missing(
        "icp_records", sa.Column("contact_country", sa.String(length=255), nullable=True)
    )
    add_column_if_missing(
        "icp_records", sa.Column("account_linkedin_url", sa.String(length=500), nullable=True)
    )
    add_column_if_missing("icp_records", sa.Column("account_city", sa.String(length=255), nullable=True))
    add_column_if_missing("icp_records", sa.Column("account_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in (
        "account_summary",
        "account_city",
        "account_linkedin_url",
        "contact_country",
        "contact_state",
        "company_location",
    ):
        try:
            op.drop_column("icp_records", col)
        except Exception:
            pass
