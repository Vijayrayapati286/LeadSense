"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database.connection import init_db
from app.icp import router as icp_router
from app.linkedin import router as linkedin_router
from app.offerings import router as offerings_router
from app.profile_extractor import router as profile_extractor_router
from app.services.scheduler_service import start_scheduler, stop_scheduler
from app.routers import (
    app_settings,
    auth,
    blacklist,
    campaign,
    custom_fields,
    dashboard,
    email,
    logs,
    mailers,
    recipient_groups,
    recipients,
    salesnav,
    tags,
    templates,
    users,
    webhooks,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.app_name)
    init_db()
    logger.info("Database initialized with seed data")
    try:
        from app.linkedin.bulk_service import resume_incomplete_bulk_jobs

        resume_incomplete_bulk_jobs()
    except Exception:
        logger.exception("Failed to resume incomplete LinkedIn bulk jobs")
    try:
        from app.offerings.match_batch_runner import resume_incomplete_match_jobs

        resume_incomplete_match_jobs()
    except Exception:
        logger.exception("Failed to resume incomplete offering match jobs")
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    description="Bulk Email Campaign Management System API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5180", "http://127.0.0.1:5180"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred"},
    )


# Register routers under /api prefix
API_PREFIX = "/api"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(campaign.router, prefix=API_PREFIX)
app.include_router(recipients.router, prefix=API_PREFIX)
app.include_router(recipient_groups.router, prefix=API_PREFIX)
app.include_router(tags.router, prefix=API_PREFIX)
app.include_router(templates.router, prefix=API_PREFIX)
app.include_router(mailers.router, prefix=API_PREFIX)
app.include_router(email.router, prefix=API_PREFIX)
app.include_router(logs.router, prefix=API_PREFIX)
app.include_router(blacklist.router, prefix=API_PREFIX)
app.include_router(webhooks.router, prefix=API_PREFIX)
app.include_router(app_settings.router, prefix=API_PREFIX)
app.include_router(custom_fields.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(salesnav.router, prefix=API_PREFIX)
app.include_router(linkedin_router, prefix=API_PREFIX)
app.include_router(profile_extractor_router, prefix=API_PREFIX)
app.include_router(icp_router, prefix=API_PREFIX)
app.include_router(offerings_router, prefix=API_PREFIX)

from app.storage.routes import batches_router as storage_batches_router
from app.storage.routes import router as storage_files_router

app.include_router(storage_files_router, prefix=API_PREFIX)
app.include_router(storage_batches_router, prefix=API_PREFIX)


@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
