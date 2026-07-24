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


def init_db() -> None:
    """Create all tables, seed dummy data if empty, and provision named users."""
    from app.models import Campaign, EmailLog, Recipient, Template, User
    from app.services.seed_service import provision_core_users, seed_dummy_data

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(Campaign).count() == 0:
            seed_dummy_data(db)
        provision_core_users(db)
    finally:
        db.close()
