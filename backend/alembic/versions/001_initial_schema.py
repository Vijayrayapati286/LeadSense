"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("azure_oid", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("azure_oid"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_id", "users", ["id"], unique=False)

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_name", sa.String(255), nullable=False),
        sa.Column("campaign_id", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("target_audience", sa.String(255), nullable=True),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("emails_sent", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id"),
    )
    op.create_index("ix_campaigns_campaign_id", "campaigns", ["campaign_id"], unique=True)
    op.create_index("ix_campaigns_id", "campaigns", ["id"], unique=False)
    op.create_index("ix_campaigns_status", "campaigns", ["status"], unique=False)

    op.create_table(
        "recipients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("designation", sa.String(255), nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("is_selected", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recipients_email", "recipients", ["email"], unique=False)
    op.create_index("ix_recipients_id", "recipients", ["id"], unique=False)

    op.create_table(
        "templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("closing", sa.Text(), nullable=True),
        sa.Column("cta", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "email_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["recipient_id"], ["recipients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_logs_status", "email_logs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_email_logs_status", table_name="email_logs")
    op.drop_table("email_logs")
    op.drop_table("templates")
    op.drop_index("ix_recipients_id", table_name="recipients")
    op.drop_index("ix_recipients_email", table_name="recipients")
    op.drop_table("recipients")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_index("ix_campaigns_id", table_name="campaigns")
    op.drop_index("ix_campaigns_campaign_id", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
