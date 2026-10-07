"""
FastAPI application entry point.

Responsibilities:
  - Create the FastAPI app instance with metadata.
  - Create all database tables on startup.
  - Register routers.
  - Expose a health-check endpoint.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import Base, engine
from app.routers import certificates, jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN001
    """Create database tables on startup (idempotent)."""
    logger.info("Starting %s — creating database tables if needed.", settings.APP_NAME)
    Base.metadata.create_all(bind=engine)
    yield
    logger.info("Shutting down %s.", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Bulk certificate generation API. "
        "Submit a list of recipients, track job progress, "
        "and download individual PDFs."
    ),
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(jobs.router)
app.include_router(certificates.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"], summary="Health check")
def health() -> dict:
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}
