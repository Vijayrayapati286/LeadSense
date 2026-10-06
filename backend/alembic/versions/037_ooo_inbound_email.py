"""OOO inbound email tracking and outbound message-id correlation.

Revision ID: 037
Revises: 036
Create Date: 2026-03-22 12:00:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing, table_exists

revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {idx["name"] for idx in inspect(bind).get_indexes(table_name)}


def _create_index_if_missing(name: str, table_name: str, columns: list[str], unique: bool = False) -> None:
    if not table_exists(table_name):
        return
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    add_column_if_missing("campaign_recipients", sa.Column("ooo_at", sa.DateTime(timezone=True), nullable=True))
    add_column_if_missing("email_logs", sa.Column("message_id", sa.String(length=255), nullable=True))
    add_column_if_missing("email_logs", sa.Column("ses_message_id", sa.String(length=255), nullable=True))
    _create_index_if_missing("ix_email_logs_message_id", "email_logs", ["message_id"])
    _create_index_if_missing("ix_email_logs_ses_message_id", "email_logs", ["ses_message_id"])

    if not table_exists("inbound_emails"):
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
    _create_index_if_missing(
        "ix_inbound_emails_inbound_message_id", "inbound_emails", ["inbound_message_id"], unique=True
    )
    _create_index_if_missing("ix_inbound_emails_classification", "inbound_emails", ["classification"])
    _create_index_if_missing("ix_inbound_emails_from_email", "inbound_emails", ["from_email"])
    _create_index_if_missing("ix_inbound_emails_id", "inbound_emails", ["id"])


def downgrade() -> None:
    if table_exists("inbound_emails"):
        for name in (
            "ix_inbound_emails_id",
            "ix_inbound_emails_from_email",
            "ix_inbound_emails_classification",
            "ix_inbound_emails_inbound_message_id",
        ):
            try:
                op.drop_index(name, table_name="inbound_emails")
            except Exception:
                pass
        op.drop_table("inbound_emails")
    for name in ("ix_email_logs_ses_message_id", "ix_email_logs_message_id"):
        try:
            op.drop_index(name, table_name="email_logs")
        except Exception:
            pass
    from column_utils import drop_column_if_exists

    drop_column_if_exists("email_logs", "ses_message_id")
    drop_column_if_exists("email_logs", "message_id")
    drop_column_if_exists("campaign_recipients", "ooo_at")
