"""
JobService — orchestration layer for certificate generation jobs.

Design:
- Single Responsibility: JobService owns the business workflow of creating and
  processing a job.  It delegates data access to repositories and PDF rendering
  to the generator strategy.
- Dependency Inversion: depends on AbstractCertificateGenerator (not a concrete
  class), RecipientValidator, and repository abstractions.
- The background processing function (`process_job`) is a plain Python function
  (not a method) so it can be passed directly to FastAPI BackgroundTasks without
  binding a JobService instance.  It creates its own DB session for thread safety.

Background Processing Rationale:
  FastAPI BackgroundTasks runs the function in a thread-pool executor after the
  HTTP response has been sent.  The API immediately returns 202 with a job_id.
  The client polls GET /jobs/{job_id} for progress.

  Trade-off: for very high throughput (thousands of jobs/minute) a dedicated
  queue (Celery + Redis) would be more resilient.  BackgroundTasks is sufficient
  here because: (a) it requires zero extra infrastructure, (b) a single SQLite
  write-lock is acceptable at this scale, and (c) the scope is per-event
  generation (not a continuous stream of requests).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.db import Job, JobStatus, Recipient, RecipientStatus
from app.repositories.job_repository import JobRepository
from app.repositories.recipient_repository import RecipientRepository
from app.schemas.job import JobCreateRequest
from app.schemas.recipient import RecipientInput
from app.services.certificate.base import AbstractCertificateGenerator
from app.services.certificate.data import CertificateDataBuilder
from app.services.certificate.factory import CertificateGeneratorFactory
from app.services.validators import RecipientValidator

logger = logging.getLogger(__name__)


class JobService:
    """
    Handles job creation: validates recipients, persists the Job and
    Recipient records, and schedules background processing.
    """

    def __init__(
        self,
        job_repo: JobRepository,
        recipient_repo: RecipientRepository,
        validator: RecipientValidator,
    ) -> None:
        self._job_repo      = job_repo
        self._recipient_repo = recipient_repo
        self._validator     = validator

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def create_job(self, request: JobCreateRequest) -> Job:
        """
        Persist a new Job with its Recipient rows.

        Recipients that fail validation are saved immediately as INVALID
        so their error message is visible in the status response.
        Valid recipients are saved as PENDING for background processing.

        Returns:
            The persisted Job ORM instance.
        """
        job = Job(
            event_name=request.event_name,
            issuer=request.issuer,
            total=len(request.recipients),
        )
        self._job_repo.add(job)
        self._job_repo.flush()  # obtain job.id before adding recipients

        invalid_count = 0
        recipients: list[Recipient] = []

        for raw in request.recipients:
            recipient, is_invalid = self._build_recipient(raw, job.id)
            if is_invalid:
                invalid_count += 1
            recipients.append(recipient)

        self._recipient_repo.add_all(recipients)
        job.invalid = invalid_count
        self._job_repo.commit()
        self._job_repo.refresh(job)
        return job

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_recipient(
        self, raw: RecipientInput, job_id: str
    ) -> tuple[Recipient, bool]:
        """
        Validate raw input and construct a Recipient ORM instance.

        Returns:
            (Recipient, is_invalid) — is_invalid=True if validation failed.
        """
        result = self._validator.validate(raw.full_name, raw.email)
        if result.is_valid:
            return (
                Recipient(
                    job_id=job_id,
                    full_name=result.cleaned_name,
                    email=result.cleaned_email,
                    status=RecipientStatus.PENDING,
                ),
                False,
            )
        else:
            error_msg = "; ".join(result.errors)
            return (
                Recipient(
                    job_id=job_id,
                    full_name=raw.full_name or "",
                    email=raw.email or "",
                    status=RecipientStatus.INVALID,
                    error_message=error_msg[:500],
                ),
                True,
            )


# ---------------------------------------------------------------------------
# Background task — standalone function for thread safety
# ---------------------------------------------------------------------------

def process_job(job_id: str) -> None:
    """
    Background task: generates certificates for all PENDING recipients.

    This function is intentionally a module-level function (not a method) so
    it can be handed to FastAPI BackgroundTasks directly.  It creates its own
    SQLAlchemy session and closes it in a `finally` block regardless of
    success or failure.

    Failure isolation: each recipient is processed in its own try/except so
    that one bad rendering does not abort the remaining recipients.

    Args:
        job_id: UUID string of the job to process.
    """
    settings = get_settings()

    # New engine + session for this background thread
    connect_args = (
        {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
    )
    bg_engine  = create_engine(settings.DATABASE_URL, connect_args=connect_args)
    BgSession  = sessionmaker(bind=bg_engine)
    db         = BgSession()

    job_repo       = JobRepository(db)
    recipient_repo = RecipientRepository(db)
    generator: AbstractCertificateGenerator = CertificateGeneratorFactory.create()
    storage_dir    = Path(settings.STORAGE_DIR)

    try:
        job = job_repo.get_by_id(job_id)
        if not job:
            logger.error("process_job: job %s not found — aborting.", job_id)
            return

        # Transition → PROCESSING
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Job %s: started processing %d recipients.", job_id, job.total)

        pending = recipient_repo.get_pending_by_job_id(job_id)

        for recipient in pending:
            _process_single_recipient(
                recipient=recipient,
                job=job,
                job_id=job_id,
                generator=generator,
                storage_dir=storage_dir,
                recipient_repo=recipient_repo,
                job_repo=job_repo,
                db=db,
            )

        # Final job status
        _finalise_job(job, job_repo, db)
        logger.info(
            "Job %s done — succeeded=%d failed=%d invalid=%d",
            job_id, job.succeeded, job.failed, job.invalid,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s encountered an unexpected error: %s", job_id, exc)
        try:
            job = job_repo.get_by_id(job_id)
            if job:
                job.status = JobStatus.FAILED
                job.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()
        bg_engine.dispose()


def _process_single_recipient(
    *,
    recipient: Recipient,
    job: Job,
    job_id: str,
    generator: AbstractCertificateGenerator,
    storage_dir: Path,
    recipient_repo: RecipientRepository,
    job_repo: JobRepository,
    db,
) -> None:
    """
    Generate the certificate for one recipient and update its status.

    All exceptions are caught so that one failure never blocks others
    (Failure Isolation requirement).
    """
    try:
        cert_data = (
            CertificateDataBuilder()
            .with_recipient(recipient.full_name)
            .with_event(job.event_name)
            .with_issuer(job.issuer)
            .build()
        )
        output_path = storage_dir / job_id / f"{recipient.id}.pdf"
        generator.generate(cert_data, output_path)

        recipient_repo.mark_success(recipient, str(output_path))
        job.succeeded += 1
        logger.debug("Recipient %s — SUCCESS", recipient.id)

    except Exception as exc:  # noqa: BLE001
        reason = f"{type(exc).__name__}: {exc}"
        recipient_repo.mark_failed(recipient, reason)
        job.failed += 1
        logger.warning("Recipient %s — FAILED: %s", recipient.id, reason)

    finally:
        job.updated_at = datetime.now(timezone.utc)
        db.commit()


def _finalise_job(job: Job, job_repo: JobRepository, db) -> None:
    """Set the terminal status based on the outcome counters."""
    valid_total = job.total - job.invalid
    if valid_total == 0:
        # All recipients were invalid — nothing to generate
        job.status = JobStatus.FAILED
    elif job.succeeded == valid_total:
        job.status = JobStatus.COMPLETED
    elif job.succeeded > 0:
        job.status = JobStatus.PARTIAL
    else:
        job.status = JobStatus.FAILED

    job.updated_at = datetime.now(timezone.utc)
    db.commit()
