"""
Job-specific repository.

Extends BaseRepository with queries tailored to the Job model.
All data-access logic for jobs lives here — routers and services never
touch SQLAlchemy session internals directly.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.db import Job, JobStatus
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    """Data-access layer for Job records."""

    def __init__(self, db: Session) -> None:
        super().__init__(Job, db)

    def get_by_id(self, job_id: str) -> Optional[Job]:  # type: ignore[override]
        """Fetch a job by its UUID string primary key."""
        return (
            self._db.query(Job)
            .filter(Job.id == job_id)
            .first()
        )

    def update_status(self, job: Job, status: JobStatus) -> None:
        """Change a job's status and flush (without committing)."""
        job.status = status
        self._db.flush()

    def update_counters(
        self,
        job: Job,
        *,
        succeeded: int = 0,
        failed: int = 0,
        invalid: int = 0,
    ) -> None:
        """Increment the job's success/fail/invalid counters atomically."""
        job.succeeded += succeeded
        job.failed += failed
        job.invalid += invalid
        self._db.flush()
