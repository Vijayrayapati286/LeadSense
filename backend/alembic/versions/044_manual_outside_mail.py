"""Record mail sent outside LeadSense.

Revision ID: 044
Revises: 043
Create Date: 2026-09-29 10:50:00.000000

Moved off revision 037, which already belongs to OOO inbound email.
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing

revision: str = "044"
down_revision: Union[str, None] = "043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "campaigns",
        sa.Column("origin", sa.String(20), nullable=False, server_default="leadsense"),
    )
    add_column_if_missing(
        "email_logs",
        sa.Column("source", sa.String(20), nullable=False, server_default="ses"),
    )
    add_column_if_missing("email_logs", sa.Column("subject", sa.String(500), nullable=True))
    add_column_if_missing("email_logs", sa.Column("body", sa.Text(), nullable=True))
    add_column_if_missing(
        "campaign_recipients",
        sa.Column("manual_follow_up_at", sa.DateTime(timezone=True), nullable=True),
    )
    add_column_if_missing(
        "campaign_recipients",
        sa.Column("manual_follow_up_action", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    pass
