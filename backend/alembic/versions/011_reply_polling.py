"""Reply detection: EmailLog.message_id + mailbox_sync_state

Supports automatic reply detection via Microsoft Graph (graph_reply_service.py,
off by default behind ENABLE_REPLY_POLLING — see app/config.py). Adds:

- email_logs.message_id: the RFC 5322 Message-ID we now set ourselves on
  outgoing mail (ses_service.py), so an inbound reply's In-Reply-To/
  References headers can be matched back to the send that prompted it.
- mailbox_sync_state: one row per rep, tracking how far each mailbox poll
  has progressed so already-scanned mail isn't re-fetched.

Revision ID: 011
Revises: 010
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("email_logs") as batch_op:
        batch_op.add_column(sa.Column("message_id", sa.String(255), nullable=True))
        batch_op.create_index("ix_email_logs_message_id", ["message_id"])

    op.create_table(
        "mailbox_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("mailbox_sync_state")
    with op.batch_alter_table("email_logs") as batch_op:
        batch_op.drop_index("ix_email_logs_message_id")
        batch_op.drop_column("message_id")
