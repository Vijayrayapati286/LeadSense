"""Database engine, session factory, and initialization."""

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Base(DeclarativeBase):
    pass


def _resolve_database_url() -> str:
    """Resolve database URL with SQLite fallback when PostgreSQL is unavailable."""
    url = settings.database_url

    if url.startswith("sqlite"):
        return url

    if settings.use_sqlite_fallback:
        try:
            engine = create_engine(url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            logger.info("Connected to PostgreSQL")
            return url
        except Exception as exc:
            logger.warning("PostgreSQL unavailable (%s), using SQLite fallback", exc)
            return "sqlite:///./bulk_email.db"

    return url


DATABASE_URL = _resolve_database_url()

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=not DATABASE_URL.startswith("sqlite"),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _column_names(conn, table: str) -> set[str]:
    inspector_rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table
            """
        ),
        {"table": table},
    )
    names = {row[0] for row in inspector_rows}
    if names:
        return names
    # SQLite
    rows = conn.execute(text(f"PRAGMA table_info({table})"))
    return {row[1] for row in rows}


def _ensure_linkedin_bulk_schema() -> None:
    """Add verification columns to existing bulk tables. create_all does not ALTER."""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "linkedin_bulk_jobs" not in tables:
        return

    job_cols = {c["name"] for c in inspector.get_columns("linkedin_bulk_jobs")}
    item_cols = (
        {c["name"] for c in inspector.get_columns("linkedin_bulk_job_items")}
        if "linkedin_bulk_job_items" in tables
        else set()
    )
    dialect = engine.dialect.name
    statements: list[str] = []

    job_adds = {
        "verified_count": "INTEGER DEFAULT 0",
        "mismatch_count": "INTEGER DEFAULT 0",
        "review_count": "INTEGER DEFAULT 0",
        "phase": "VARCHAR(32) DEFAULT 'pending'",
        "excel_finalized": "BOOLEAN DEFAULT FALSE" if dialect != "sqlite" else "INTEGER DEFAULT 0",
    }
    item_adds = {
        "verification_status": "VARCHAR(32) DEFAULT 'NOT_VERIFIED'",
        "verification_score": "INTEGER DEFAULT 0",
        "name_match": "BOOLEAN" if dialect != "sqlite" else "INTEGER",
        "designation_match": "BOOLEAN" if dialect != "sqlite" else "INTEGER",
        "company_match": "BOOLEAN" if dialect != "sqlite" else "INTEGER",
        "location_match": "BOOLEAN" if dialect != "sqlite" else "INTEGER",
        "verification_reason": "TEXT",
    }

    for name, ddl in job_adds.items():
        if name not in job_cols:
            statements.append(f"ALTER TABLE linkedin_bulk_jobs ADD COLUMN {name} {ddl}")
    for name, ddl in item_adds.items():
        if name not in item_cols:
            statements.append(f"ALTER TABLE linkedin_bulk_job_items ADD COLUMN {name} {ddl}")

    if not statements:
        return

    with engine.begin() as conn:
        for stmt in statements:
            logger.info("Applying LinkedIn bulk schema patch: %s", stmt)
            conn.execute(text(stmt))
        if dialect != "sqlite":
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_bulk_items_job_verify
                    ON linkedin_bulk_job_items (job_id, verification_status)
                    """
                )
            )
    logger.info("LinkedIn bulk schema patched (%s statements)", len(statements))


def init_db() -> None:
    """Create all tables, seed dummy data if empty, and provision named users."""
    from app.models import Campaign, EmailLog, Recipient, Template, User
    from app.profile_extractor import models as _profile_extractor_models  # noqa: F401
    from app.linkedin import bulk_models as _linkedin_bulk_models  # noqa: F401
    from app.services.seed_service import provision_core_users, seed_dummy_data

    Base.metadata.create_all(bind=engine)
    _ensure_linkedin_bulk_schema()

    db = SessionLocal()
    try:
        if db.query(Campaign).count() == 0:
            seed_dummy_data(db)
        provision_core_users(db)
    finally:
        db.close()
