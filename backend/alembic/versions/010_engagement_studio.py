"""Engagement Studio: library-template stages, skip condition, list targeting

Renames the "Follow-up Sequence" feature to "Engagement Studio" at the
product/code level (backend/app/models/models.py: CampaignSequenceStage ->
EngagementStudioStage). The underlying campaign_sequence_stages table keeps
its name to avoid a risky rename/data migration — only new columns are added.

- campaign_sequence_stages.mailer_id: optional live reference to a library
  Mailer, so a stage can reuse a saved template instead of duplicating its
  content inline. subject/body become nullable since mailer_id can supply
  them instead.
- campaign_sequence_stages.skip_if_tagged: condition — skip sending a stage to
  a prospect who already has a manual response_tag (Hot/Warm/Cold/Negative),
  on top of the existing reply/bounce/suppression check.
- engagement_studio_lists: which of a campaign's prospect lists are enrolled
  in its Engagement Studio automation (no rows = whole campaign, matching
  prior behavior).

Revision ID: 010
Revises: 009
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("campaign_sequence_stages") as batch_op:
        batch_op.add_column(sa.Column("mailer_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("skip_if_tagged", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.alter_column("subject", existing_type=sa.String(500), nullable=True)
        batch_op.alter_column("body", existing_type=sa.Text(), nullable=True)
        batch_op.create_foreign_key(
            "fk_campaign_sequence_stages_mailer_id", "mailers", ["mailer_id"], ["id"]
        )

    op.create_table(
        "engagement_studio_lists",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("recipient_groups.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("campaign_id", "group_id", name="uq_engagement_studio_list"),
    )


def downgrade() -> None:
    op.drop_table("engagement_studio_lists")
    with op.batch_alter_table("campaign_sequence_stages") as batch_op:
        batch_op.drop_constraint("fk_campaign_sequence_stages_mailer_id", type_="foreignkey")
        batch_op.alter_column("body", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("subject", existing_type=sa.String(500), nullable=False)
        batch_op.drop_column("skip_if_tagged")
        batch_op.drop_column("mailer_id")
