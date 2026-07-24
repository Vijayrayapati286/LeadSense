"""Add multi-template support (Template.name, CampaignRecipient.template_id)

Revision ID: 003
Revises: 002
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("name", sa.String(255), nullable=True))
    op.add_column("campaign_recipients", sa.Column("template_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("campaign_recipients") as batch_op:
        batch_op.create_foreign_key(
            "fk_campaign_recipients_template_id", "templates", ["template_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("campaign_recipients") as batch_op:
        batch_op.drop_constraint("fk_campaign_recipients_template_id", type_="foreignkey")
        batch_op.drop_column("template_id")
    op.drop_column("templates", "name")
