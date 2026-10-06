"""Helpers for idempotent Alembic migrations."""

from alembic import op
from sqlalchemy import inspect

__all__ = (
    "table_exists",
    "column_exists",
    "add_column_if_missing",
    "drop_column_if_exists",
)


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in inspect(bind).get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    bind = op.get_bind()
    columns = {col["name"] for col in inspect(bind).get_columns(table_name)}
    return column_name in columns


def add_column_if_missing(table_name: str, column) -> None:
    if not column_exists(table_name, column.name):
        op.add_column(table_name, column)


def drop_column_if_exists(table_name: str, column_name: str) -> None:
    if column_exists(table_name, column_name):
        op.drop_column(table_name, column_name)
