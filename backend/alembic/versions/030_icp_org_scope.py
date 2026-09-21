"""Scope ICP records by tenant org_id.

Revision ID: 030
Revises: 026
Create Date: 2026-09-18 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "030"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("icp_records", sa.Column("org_id", sa.String(length=50), nullable=True))
    op.create_index("ix_icp_records_org_id", "icp_records", ["org_id"])
    op.create_index("ix_icp_org_verified_at", "icp_records", ["org_id", "verified_at"])
    op.create_index("ix_icp_org_industry", "icp_records", ["org_id", "industry"])
    op.create_index("ix_icp_org_dedupe", "icp_records", ["org_id", "dedupe_key"])

    op.execute(
        """
        UPDATE icp_records
        SET org_id = (
            SELECT users.org_id FROM users WHERE users.id = icp_records.user_id
        )
        WHERE org_id IS NULL AND user_id IS NOT NULL
        """
    )

    try:
        op.drop_constraint("uq_icp_user_linkedin_url", "icp_records", type_="unique")
    except Exception:
        pass
    op.create_unique_constraint(
        "uq_icp_org_linkedin_url", "icp_records", ["org_id", "linkedin_url"]
    )


def downgrade() -> None:
    try:
        op.drop_constraint("uq_icp_org_linkedin_url", "icp_records", type_="unique")
    except Exception:
        pass
    op.drop_index("ix_icp_org_dedupe", table_name="icp_records")
    op.drop_index("ix_icp_org_industry", table_name="icp_records")
    op.drop_index("ix_icp_org_verified_at", table_name="icp_records")
    op.drop_index("ix_icp_records_org_id", table_name="icp_records")
    op.drop_column("icp_records", "org_id")
    op.create_unique_constraint(
        "uq_icp_user_linkedin_url", "icp_records", ["user_id", "linkedin_url"]
    )
