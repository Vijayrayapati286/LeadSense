"""Alembic migration environment."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database.connection import Base, DATABASE_URL
from app.models import (  # noqa: F401
    Campaign,
    CampaignRecipient,
    CampaignSequenceStage,
    CustomField,
    EmailLog,
    Recipient,
    RecipientCustomValue,
    RecipientGroup,
    Template,
    User,
)
from app.linkedin import bulk_models as _linkedin_bulk_models  # noqa: F401
from app.profile_extractor import models as _profile_extractor_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Reuse the app's own resolved URL (handles the Postgres-unavailable ->
# SQLite fallback) instead of recomputing it here, so `alembic upgrade head`
# actually targets whichever database the running app is using.
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
