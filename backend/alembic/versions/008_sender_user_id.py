"""Add sender_user_id to campaign_recipients and email_logs

Tracks who actually triggered a send (Send/Schedule action), independent of
the campaign's creator, since campaigns and their lists are shared/edited
across the team.

Revision ID: 008
Revises: 007
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("campaign_recipients", sa.Column("sender_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_campaign_recipients_sender_user_id", "campaign_recipients", "users", ["sender_user_id"], ["id"]
    )
    op.add_column("email_logs", sa.Column("sender_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_email_logs_sender_user_id", "email_logs", "users", ["sender_user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_email_logs_sender_user_id", "email_logs", type_="foreignkey")
    op.drop_column("email_logs", "sender_user_id")
    op.drop_constraint("fk_campaign_recipients_sender_user_id", "campaign_recipients", type_="foreignkey")
    op.drop_column("campaign_recipients", "sender_user_id")
