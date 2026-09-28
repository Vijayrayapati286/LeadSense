"""OOO inbound email tracking and outbound message-id correlation.

Revision ID: 031
Revises: 030
Create Date: 2026-03-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "campaign_recipients",
        sa.Column("ooo_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "email_logs",
        sa.Column("message_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "email_logs",
        sa.Column("ses_message_id", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_email_logs_message_id", "email_logs", ["message_id"])
    op.create_index("ix_email_logs_ses_message_id", "email_logs", ["ses_message_id"])

    op.create_table(
        "inbound_emails",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("inbound_message_id", sa.String(length=255), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("from_email", sa.String(length=255), nullable=True),
        sa.Column("to_email", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("in_reply_to", sa.String(length=255), nullable=True),
        sa.Column("references_header", sa.Text(), nullable=True),
        sa.Column("s3_bucket", sa.String(length=255), nullable=True),
        sa.Column("s3_key", sa.String(length=1024), nullable=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), nullable=True),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("recipients.id"), nullable=True),
        sa.Column(
            "campaign_recipient_id",
            sa.Integer(),
            sa.ForeignKey("campaign_recipients.id"),
            nullable=True,
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
    )
    op.create_index("ix_inbound_emails_inbound_message_id", "inbound_emails", ["inbound_message_id"], unique=True)
    op.create_index("ix_inbound_emails_classification", "inbound_emails", ["classification"])
    op.create_index("ix_inbound_emails_from_email", "inbound_emails", ["from_email"])
    op.create_index("ix_inbound_emails_id", "inbound_emails", ["id"])


def downgrade() -> None:
    op.drop_index("ix_inbound_emails_id", table_name="inbound_emails")
    op.drop_index("ix_inbound_emails_from_email", table_name="inbound_emails")
    op.drop_index("ix_inbound_emails_classification", table_name="inbound_emails")
    op.drop_index("ix_inbound_emails_inbound_message_id", table_name="inbound_emails")
    op.drop_table("inbound_emails")
    op.drop_index("ix_email_logs_ses_message_id", table_name="email_logs")
    op.drop_index("ix_email_logs_message_id", table_name="email_logs")
    op.drop_column("email_logs", "ses_message_id")
    op.drop_column("email_logs", "message_id")
    op.drop_column("campaign_recipients", "ooo_at")
