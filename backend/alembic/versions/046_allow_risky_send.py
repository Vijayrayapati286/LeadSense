"""Remember when a sender confirmed including risky emails.

Revision ID: 046
Revises: 045
Create Date: 2026-09-29 14:40:00.000000

Moved off revision 039, which already belongs to ICP company location.
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing

revision: str = "046"
down_revision: Union[str, None] = "045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "campaign_recipients",
        sa.Column("allow_risky_send", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("campaign_recipients", "allow_risky_send")
