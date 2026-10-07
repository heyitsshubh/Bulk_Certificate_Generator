"""
Router for certificate download.

Endpoint:
  GET /jobs/{job_id}/certificates/{recipient_id}
    — Stream the generated PDF for a specific recipient.

Design: The router checks ownership (recipient belongs to job) before
serving the file, preventing cross-job information disclosure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import (
    CertificateFileNotFoundException,
    JobNotFoundException,
    RecipientJobMismatchException,
    RecipientNotFoundException,
)
from app.models.db import RecipientStatus
from app.repositories.job_repository import JobRepository
from app.repositories.recipient_repository import RecipientRepository

router = APIRouter(prefix="/jobs", tags=["Certificates"])


def get_job_repository(db: Annotated[Session, Depends(get_db)]) -> JobRepository:
    return JobRepository(db)


def get_recipient_repository(
    db: Annotated[Session, Depends(get_db)],
) -> RecipientRepository:
    return RecipientRepository(db)


@router.get(
    "/{job_id}/certificates/{recipient_id}",
    summary="Download the generated certificate PDF for a recipient",
    response_description="The certificate PDF file as an attachment.",
    responses={
        200: {"content": {"application/pdf": {}}},
        404: {"description": "Job, recipient, or certificate file not found."},
    },
)
def download_certificate(
    job_id: str,
    recipient_id: str,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    recipient_repo: Annotated[RecipientRepository, Depends(get_recipient_repository)],
) -> FileResponse:
    # 1. Validate job exists
    job = job_repo.get_by_id(job_id)
    if not job:
        raise JobNotFoundException(job_id)

    # 2. Validate recipient exists and belongs to this job
    recipient = recipient_repo.get_by_id(recipient_id)
    if not recipient:
        raise RecipientNotFoundException(recipient_id)
    if recipient.job_id != job_id:
        raise RecipientJobMismatchException(recipient_id, job_id)

    # 3. Validate certificate was generated successfully
    if recipient.status != RecipientStatus.SUCCESS or not recipient.certificate_path:
        raise RecipientNotFoundException(recipient_id)

    # 4. Validate the file exists on disk
    cert_path = Path(recipient.certificate_path)
    if not cert_path.exists():
        raise CertificateFileNotFoundException(str(cert_path))

    # 5. Stream the file
    filename = f"certificate_{recipient.full_name.replace(' ', '_')}.pdf"
    return FileResponse(
        path=str(cert_path),
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
