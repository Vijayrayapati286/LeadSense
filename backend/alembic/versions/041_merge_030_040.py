"""Merge the 030 ICP-org branch into the main 040 chain.

Revision ID: 041
Revises: 040, 030
Create Date: 2026-09-28 14:35:00.000000
"""
from typing import Sequence, Union

revision: str = "041"
down_revision: Union[str, tuple[str, ...], None] = ("040", "030")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
