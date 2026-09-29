"""Merge 041 (UAT stamp) with 039 (OOO + ICP export/location branch).

Revision ID: 042
Revises: 041, 039
Create Date: 2026-09-29

UAT alembic_version is 041 (merge of 040 + 030). 037/038/039 branch from
036 and were never applied. This merge makes a single head so
``alembic upgrade head`` runs 037 → 038 → 039, then this empty merge.

Those three migrations use add_column_if_missing / create-index-if-missing,
so they are safe if a database already has some of the columns.
"""
from typing import Sequence, Union

revision: str = "042"
down_revision: Union[str, tuple[str, ...], None] = ("041", "039")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
