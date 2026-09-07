"""Offerings recommendation engine: embeddings, hard filters, feedback, score components.

Revision ID: 017
Revises: 016
Create Date: 2026-08-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("offerings", sa.Column("pricing_range", sa.String(length=100), nullable=True))
    op.add_column("offerings", sa.Column("hard_filter_rules", sa.JSON(), nullable=True))
    op.add_column("offerings", sa.Column("embedding", sa.JSON(), nullable=True))
    op.add_column("offerings", sa.Column("embedding_model", sa.String(length=100), nullable=True))
    op.add_column("offerings", sa.Column("profile_text", sa.Text(), nullable=True))

    op.add_column("icp_records", sa.Column("embedding", sa.JSON(), nullable=True))
    op.add_column("icp_records", sa.Column("embedding_model", sa.String(length=100), nullable=True))

    op.add_column(
        "offering_matches",
        sa.Column("icp_fit_score", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "offering_matches",
        sa.Column("problem_fit_score", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "offering_matches",
        sa.Column("role_fit_score", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "offering_matches",
        sa.Column("company_fit_score", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "offering_matches",
        sa.Column("historical_score", sa.Integer(), nullable=False, server_default="70"),
    )
    op.add_column("offering_matches", sa.Column("missing_information", sa.JSON(), nullable=True))
    op.add_column("offering_matches", sa.Column("explanation", sa.Text(), nullable=True))
    op.add_column(
        "offering_matches",
        sa.Column("semantic_similarity", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "offering_recommendation_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=False),
        sa.Column("offering_id", sa.Integer(), nullable=False),
        sa.Column("icp_record_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("score_at_action", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_id"], ["offering_matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offering_id"], ["offerings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["icp_record_id"], ["icp_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_offering_feedback_offering",
        "offering_recommendation_feedback",
        ["offering_id"],
    )
    op.create_index(
        "ix_offering_feedback_icp",
        "offering_recommendation_feedback",
        ["icp_record_id"],
    )
    op.create_index(
        "ix_offering_feedback_action",
        "offering_recommendation_feedback",
        ["action"],
    )


def downgrade() -> None:
    op.drop_index("ix_offering_feedback_action", table_name="offering_recommendation_feedback")
    op.drop_index("ix_offering_feedback_icp", table_name="offering_recommendation_feedback")
    op.drop_index("ix_offering_feedback_offering", table_name="offering_recommendation_feedback")
    op.drop_table("offering_recommendation_feedback")

    op.drop_column("offering_matches", "semantic_similarity")
    op.drop_column("offering_matches", "explanation")
    op.drop_column("offering_matches", "missing_information")
    op.drop_column("offering_matches", "historical_score")
    op.drop_column("offering_matches", "company_fit_score")
    op.drop_column("offering_matches", "role_fit_score")
    op.drop_column("offering_matches", "problem_fit_score")
    op.drop_column("offering_matches", "icp_fit_score")

    op.drop_column("icp_records", "embedding_model")
    op.drop_column("icp_records", "embedding")

    op.drop_column("offerings", "profile_text")
    op.drop_column("offerings", "embedding_model")
    op.drop_column("offerings", "embedding")
    op.drop_column("offerings", "hard_filter_rules")
    op.drop_column("offerings", "pricing_range")
