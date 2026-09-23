"""Drop unused sectors and manager_assignments tables.

Revision ID: 033
Revises: 032
Create Date: 2026-09-22 11:24:00.000000
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "sectors" in tables:
        op.drop_table("sectors")
    if "manager_assignments" in tables:
        op.drop_table("manager_assignments")


def downgrade() -> None:
    pass
