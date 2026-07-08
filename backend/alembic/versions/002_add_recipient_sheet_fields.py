"""Add extended recipient sheet fields

Revision ID: 002
Revises: 001
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_COLUMNS = [
    sa.Column("create_date", sa.Date(), nullable=True),
    sa.Column("fresh_mail", sa.String(255), nullable=True),
    sa.Column("follow_up_1", sa.String(255), nullable=True),
    sa.Column("follow_up_2", sa.String(255), nullable=True),
    sa.Column("follow_up_3", sa.String(255), nullable=True),
    sa.Column("grouping", sa.String(255), nullable=True),
    sa.Column("vertical", sa.String(255), nullable=True),
    sa.Column("sub_vertical", sa.String(255), nullable=True),
    sa.Column("revenue", sa.String(100), nullable=True),
    sa.Column("revenue_range", sa.String(100), nullable=True),
    sa.Column("website", sa.String(500), nullable=True),
    sa.Column("state", sa.String(255), nullable=True),
    sa.Column("region", sa.String(255), nullable=True),
    sa.Column("first_name", sa.String(255), nullable=True),
    sa.Column("last_name", sa.String(255), nullable=True),
    sa.Column("designation_level", sa.String(100), nullable=True),
    sa.Column("contact_location", sa.String(255), nullable=True),
    sa.Column("campaign_tag", sa.String(255), nullable=True),
    sa.Column("linkedin_message", sa.Text(), nullable=True),
    sa.Column("linkedin_connection_request", sa.Text(), nullable=True),
    sa.Column("response_1", sa.String(255), nullable=True),
    sa.Column("response_2", sa.String(255), nullable=True),
    sa.Column("status", sa.String(50), nullable=True),
    sa.Column("comments", sa.Text(), nullable=True),
]


def upgrade() -> None:
    for column in NEW_COLUMNS:
        op.add_column("recipients", column)


def downgrade() -> None:
    for column in reversed(NEW_COLUMNS):
        op.drop_column("recipients", column.name)
