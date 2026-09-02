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
    dialect = getattr(conn.dialect, "name", "") or ""
    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in rows}
    try:
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
    except Exception:
        pass
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

    bool_type = "BOOLEAN" if dialect != "sqlite" else "INTEGER"
    job_adds = {
        "verified_count": "INTEGER DEFAULT 0",
        "mismatch_count": "INTEGER DEFAULT 0",
        "review_count": "INTEGER DEFAULT 0",
        "needs_review_count": "INTEGER DEFAULT 0",
        "resolved_count": "INTEGER DEFAULT 0",
        "phase": "VARCHAR(32) DEFAULT 'pending'",
        "excel_finalized": "BOOLEAN DEFAULT FALSE" if dialect != "sqlite" else "INTEGER DEFAULT 0",
        "backup_status": "VARCHAR(32) DEFAULT 'none'",
        "backup_file_path": "VARCHAR(500)",
        "started_at": "TIMESTAMP WITH TIME ZONE" if dialect != "sqlite" else "DATETIME",
    }
    item_adds = {
        "verification_status": "VARCHAR(32) DEFAULT 'NOT_VERIFIED'",
        "verification_score": "INTEGER DEFAULT 0",
        "name_match": bool_type,
        "designation_match": bool_type,
        "company_match": bool_type,
        "location_match": bool_type,
        "company_location_match": bool_type,
        "verification_reason": "TEXT",
        "resolved_name": "VARCHAR(500)",
        "resolved_designation": "VARCHAR(500)",
        "resolved_company": "VARCHAR(500)",
        "resolved_location": "VARCHAR(500)",
        "resolved_company_location": "VARCHAR(500)",
        "resolution_summary": "VARCHAR(64)",
        "resolved_by": "INTEGER",
        "resolved_at": "TIMESTAMP WITH TIME ZONE" if dialect != "sqlite" else "DATETIME",
    }

    for name, ddl in job_adds.items():
        if name not in job_cols:
            statements.append(f"ALTER TABLE linkedin_bulk_jobs ADD COLUMN {name} {ddl}")
    for name, ddl in item_adds.items():
        if name not in item_cols:
            statements.append(f"ALTER TABLE linkedin_bulk_job_items ADD COLUMN {name} {ddl}")

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
        # create_all may have already created these; IF NOT EXISTS is portable enough
        # for Postgres; SQLite create_all handles new ORM tables on next init.
        if "linkedin_bulk_conflict_resolutions" not in tables:
            if dialect == "sqlite":
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS linkedin_bulk_conflict_resolutions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job_item_id INTEGER NOT NULL REFERENCES linkedin_bulk_job_items(id) ON DELETE CASCADE,
                            field VARCHAR(64) NOT NULL,
                            uploaded_value TEXT,
                            extracted_value TEXT,
                            resolution VARCHAR(32) NOT NULL,
                            resolved_value TEXT,
                            resolved_by INTEGER,
                            resolved_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                )
            else:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS linkedin_bulk_conflict_resolutions (
                            id SERIAL PRIMARY KEY,
                            job_item_id INTEGER NOT NULL REFERENCES linkedin_bulk_job_items(id) ON DELETE CASCADE,
                            field VARCHAR(64) NOT NULL,
                            uploaded_value TEXT,
                            extracted_value TEXT,
                            resolution VARCHAR(32) NOT NULL,
                            resolved_value TEXT,
                            resolved_by INTEGER,
                            resolved_at TIMESTAMPTZ DEFAULT NOW()
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS ix_bulk_conflict_item_field
                        ON linkedin_bulk_conflict_resolutions (job_item_id, field)
                        """
                    )
                )

        resolution_cols = _column_names(conn, "linkedin_bulk_conflict_resolutions")
        for name, ddl in {
            "edited_value": "TEXT",
            "resolved_by_name": "VARCHAR(255)",
            "resolved_by_email": "VARCHAR(255)",
            "change_summary": "TEXT",
        }.items():
            if name not in resolution_cols:
                conn.execute(
                    text(f"ALTER TABLE linkedin_bulk_conflict_resolutions ADD COLUMN {name} {ddl}")
                )
                logger.info("Patched linkedin_bulk_conflict_resolutions.%s", name)

        if "linkedin_bulk_backups" not in tables:
            if dialect == "sqlite":
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS linkedin_bulk_backups (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job_id VARCHAR(36) NOT NULL REFERENCES linkedin_bulk_jobs(id) ON DELETE CASCADE,
                            user_id INTEGER,
                            backup_version INTEGER NOT NULL DEFAULT 1,
                            file_path VARCHAR(500) NOT NULL,
                            status VARCHAR(32) NOT NULL DEFAULT 'ready',
                            error TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                )
            else:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS linkedin_bulk_backups (
                            id SERIAL PRIMARY KEY,
                            job_id VARCHAR(36) NOT NULL REFERENCES linkedin_bulk_jobs(id) ON DELETE CASCADE,
                            user_id INTEGER,
                            backup_version INTEGER NOT NULL DEFAULT 1,
                            file_path VARCHAR(500) NOT NULL,
                            status VARCHAR(32) NOT NULL DEFAULT 'ready',
                            error TEXT,
                            created_at TIMESTAMPTZ DEFAULT NOW()
                        )
                        """
                    )
                )
    if statements:
        logger.info("LinkedIn bulk schema patched (%s statements)", len(statements))


def _ensure_offerings_recommendation_schema() -> None:
    """Patch offering/ICP columns for recommendation engine. create_all does not ALTER."""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    dialect = engine.dialect.name
    json_type = "JSON" if dialect != "sqlite" else "TEXT"
    int_default = lambda d: f"INTEGER DEFAULT {d}"  # noqa: E731

    with engine.begin() as conn:
        if "icp_records" in tables:
            cols = {c["name"] for c in inspector.get_columns("icp_records")}
            icp_adds = {
                "embedding": json_type,
                "embedding_model": "VARCHAR(100)",
            }
            for name, ddl in icp_adds.items():
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE icp_records ADD COLUMN {name} {ddl}"))
                    logger.info("Added icp_records.%s", name)

        if "offerings" in tables:
            cols = {c["name"] for c in inspector.get_columns("offerings")}
            offering_adds = {
                "pricing_range": "VARCHAR(100)",
                "hard_filter_rules": json_type,
                "embedding": json_type,
                "embedding_model": "VARCHAR(100)",
                "profile_text": "TEXT",
            }
            for name, ddl in offering_adds.items():
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE offerings ADD COLUMN {name} {ddl}"))
                    logger.info("Added offerings.%s", name)

        if "offering_matches" in tables:
            cols = {c["name"] for c in inspector.get_columns("offering_matches")}
            match_adds = {
                "icp_fit_score": int_default(0),
                "problem_fit_score": int_default(0),
                "role_fit_score": int_default(0),
                "company_fit_score": int_default(0),
                "historical_score": int_default(70),
                "semantic_similarity": int_default(0),
                "missing_information": json_type,
                "explanation": "TEXT",
            }
            for name, ddl in match_adds.items():
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE offering_matches ADD COLUMN {name} {ddl}"))
                    logger.info("Added offering_matches.%s", name)

        if "offering_recommendation_feedback" not in tables:
            # create_all should have made it; re-check after create_all
            pass


def _ensure_app_settings_schema() -> None:
    """Patch app_settings columns for runtime preferences. create_all does not ALTER."""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "app_settings" not in tables:
        return

    dialect = engine.dialect.name
    bool_type = "BOOLEAN DEFAULT FALSE" if dialect != "sqlite" else "INTEGER DEFAULT 0"
    cols = {c["name"] for c in inspector.get_columns("app_settings")}
    adds = {
        "business_hours_start": "INTEGER DEFAULT 9",
        "business_hours_end": "INTEGER DEFAULT 18",
        "default_page_size": "INTEGER DEFAULT 10",
        "default_ai_tone": "VARCHAR(32) DEFAULT 'formal'",
        "default_use_recipient_timezone": bool_type,
    }

    with engine.begin() as conn:
        for name, ddl in adds.items():
            if name not in cols:
                conn.execute(text(f"ALTER TABLE app_settings ADD COLUMN {name} {ddl}"))
                logger.info("Added app_settings.%s", name)


def init_db() -> None:
    """Create all tables, seed dummy data if empty, and provision named users."""
    from app.models import Campaign, EmailLog, Recipient, Template, User
    from app.profile_extractor import models as _profile_extractor_models  # noqa: F401
    from app.linkedin import bulk_models as _linkedin_bulk_models  # noqa: F401
    from app.icp import models as _icp_models  # noqa: F401
    from app.offerings import models as _offerings_models  # noqa: F401
    from app.storage import models as _storage_models  # noqa: F401
    from app.services.seed_service import provision_core_users, seed_dummy_data

    Base.metadata.create_all(bind=engine)
    _ensure_linkedin_bulk_schema()
    _ensure_offerings_recommendation_schema()
    _ensure_app_settings_schema()

    db = SessionLocal()
    try:
        if db.query(Campaign).count() == 0:
            seed_dummy_data(db)
        provision_core_users(db)
    finally:
        db.close()
