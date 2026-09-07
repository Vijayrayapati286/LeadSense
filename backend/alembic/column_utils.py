"""Helpers for idempotent Alembic migrations."""

from alembic import op
from sqlalchemy import inspect


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = {col["name"] for col in inspect(bind).get_columns(table_name)}
    return column_name in columns


def add_column_if_missing(table_name: str, column) -> None:
    if not column_exists(table_name, column.name):
        op.add_column(table_name, column)
