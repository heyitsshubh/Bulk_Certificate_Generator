"""
Routers for job-related endpoints.

Endpoints:
  POST /jobs                         — Submit a bulk generation job
  GET  /jobs/{job_id}                — Get job status and counters
  GET  /jobs/{job_id}/recipients     — List all recipients with statuses
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import JobNotFoundException
from app.repositories.job_repository import JobRepository
from app.repositories.recipient_repository import RecipientRepository
from app.schemas.job import (
    JobCreateRequest,
    JobCreateResponse,
    JobRecipientsResponse,
    JobStatusResponse,
)
from app.schemas.recipient import RecipientStatusResponse
from app.services.job_service import JobService, process_job
from app.services.validators import RecipientValidator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# ---------------------------------------------------------------------------
# Dependency factories (Dependency Inversion — router never nests concrete types)
# ---------------------------------------------------------------------------

def get_job_service(db: Annotated[Session, Depends(get_db)]) -> JobService:
    return JobService(
        job_repo=JobRepository(db),
        recipient_repo=RecipientRepository(db),
        validator=RecipientValidator(),
    )


def get_job_repository(db: Annotated[Session, Depends(get_db)]) -> JobRepository:
    return JobRepository(db)


def get_recipient_repository(
    db: Annotated[Session, Depends(get_db)],
) -> RecipientRepository:
    return RecipientRepository(db)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobCreateResponse,
    summary="Submit a bulk certificate generation job",
    description=(
        "Accepts a list of recipients and event details. "
        "Immediately returns a job_id. "
        "Generation runs in the background — poll GET /jobs/{job_id} for progress."
    ),
)
def create_job(
    request: JobCreateRequest,
    background_tasks: BackgroundTasks,
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobCreateResponse:
    job = service.create_job(request)
    background_tasks.add_task(process_job, job.id)
    logger.info("Job %s created with %d recipients.", job.id, job.total)
    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        total=job.total,
        message=(
            f"Job accepted. {job.total} recipients queued "
            f"({job.invalid} failed validation). "
            f"Poll GET /jobs/{job.id} for progress."
        ),
    )


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status and counters",
)
def get_job_status(
    job_id: str,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
) -> JobStatusResponse:
    job = job_repo.get_by_id(job_id)
    if not job:
        raise JobNotFoundException(job_id)
    return JobStatusResponse(
        job_id=job.id,
        event_name=job.event_name,
        issuer=job.issuer,
        status=job.status,
        total=job.total,
        succeeded=job.succeeded,
        failed=job.failed,
        invalid=job.invalid,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


@router.get(
    "/{job_id}/recipients",
    response_model=JobRecipientsResponse,
    summary="List all recipients and their individual statuses",
)
def list_recipients(
    job_id: str,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    recipient_repo: Annotated[RecipientRepository, Depends(get_recipient_repository)],
) -> JobRecipientsResponse:
    job = job_repo.get_by_id(job_id)
    if not job:
        raise JobNotFoundException(job_id)
    recipients = recipient_repo.get_by_job_id(job_id)
    return JobRecipientsResponse(
        job_id=job_id,
        total=len(recipients),
        recipients=[
            RecipientStatusResponse.model_validate(r) for r in recipients
        ],
    )
