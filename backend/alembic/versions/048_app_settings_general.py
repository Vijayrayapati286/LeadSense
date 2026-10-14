"""General Settings: risky send mode for campaign mail.

Revision ID: 048
Revises: 047
Create Date: 2026-10-13
"""

from typing import Sequence, Union

import sqlalchemy as sa

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing, drop_column_if_exists

revision: str = "048"
down_revision: Union[str, None] = "047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "app_settings",
        sa.Column("risky_send_mode", sa.String(16), nullable=False, server_default="ask"),
    )


def downgrade() -> None:
    drop_column_if_exists("app_settings", "risky_send_mode")
