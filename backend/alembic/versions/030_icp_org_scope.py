"""Scope ICP records by tenant org_id.

Revision ID: 030
Revises: 026
Create Date: 2026-09-18 17:30:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing, table_exists

revision: str = "030"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_names(table_name: str) -> set[str]:
    if not table_exists(table_name):
        return set()
    bind = op.get_bind()
    return {idx["name"] for idx in inspect(bind).get_indexes(table_name)}


def _constraint_names(table_name: str) -> set[str]:
    if not table_exists(table_name):
        return set()
    bind = op.get_bind()
    names = set()
    for key in ("get_unique_constraints", "get_pk_constraint", "get_foreign_keys", "get_check_constraints"):
        getter = getattr(inspect(bind), key, None)
        if not getter:
            continue
        result = getter(table_name)
        if isinstance(result, dict):
            if result.get("name"):
                names.add(result["name"])
        else:
            for item in result or []:
                if item.get("name"):
                    names.add(item["name"])
    return names


def upgrade() -> None:
    if not table_exists("icp_records"):
        return
    add_column_if_missing("icp_records", sa.Column("org_id", sa.String(length=50), nullable=True))
    indexes = _index_names("icp_records")
    if "ix_icp_records_org_id" not in indexes:
        op.create_index("ix_icp_records_org_id", "icp_records", ["org_id"])
    if "ix_icp_org_verified_at" not in indexes:
        op.create_index("ix_icp_org_verified_at", "icp_records", ["org_id", "verified_at"])
    if "ix_icp_org_industry" not in indexes:
        op.create_index("ix_icp_org_industry", "icp_records", ["org_id", "industry"])
    if "ix_icp_org_dedupe" not in indexes:
        op.create_index("ix_icp_org_dedupe", "icp_records", ["org_id", "dedupe_key"])

    op.execute(
        """
        UPDATE icp_records
        SET org_id = (
            SELECT users.org_id FROM users WHERE users.id = icp_records.user_id
        )
        WHERE org_id IS NULL AND user_id IS NOT NULL
        """
    )

    constraints = _constraint_names("icp_records")
    if "uq_icp_user_linkedin_url" in constraints:
        try:
            op.drop_constraint("uq_icp_user_linkedin_url", "icp_records", type_="unique")
        except Exception:
            pass
    if "uq_icp_org_linkedin_url" not in constraints:
        try:
            op.create_unique_constraint(
                "uq_icp_org_linkedin_url", "icp_records", ["org_id", "linkedin_url"]
            )
        except Exception:
            pass


def downgrade() -> None:
    if not table_exists("icp_records"):
        return
    try:
        op.drop_constraint("uq_icp_org_linkedin_url", "icp_records", type_="unique")
    except Exception:
        pass
    for name in ("ix_icp_org_dedupe", "ix_icp_org_industry", "ix_icp_org_verified_at", "ix_icp_records_org_id"):
        try:
            op.drop_index(name, table_name="icp_records")
        except Exception:
            pass
    from column_utils import drop_column_if_exists

    drop_column_if_exists("icp_records", "org_id")
    try:
        op.create_unique_constraint(
            "uq_icp_user_linkedin_url", "icp_records", ["user_id", "linkedin_url"]
        )
    except Exception:
        pass
