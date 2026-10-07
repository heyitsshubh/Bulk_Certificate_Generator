"""
Recipient-specific repository.

Provides fine-grained query methods for Recipient records, keeping the
service layer free of ORM-level filtering and ordering logic.
"""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.db import Recipient, RecipientStatus
from app.repositories.base import BaseRepository


class RecipientRepository(BaseRepository[Recipient]):
    """Data-access layer for Recipient records."""

    def __init__(self, db: Session) -> None:
        super().__init__(Recipient, db)

    def get_by_id(self, recipient_id: str) -> Optional[Recipient]:  # type: ignore[override]
        return (
            self._db.query(Recipient)
            .filter(Recipient.id == recipient_id)
            .first()
        )

    def get_by_job_id(self, job_id: str) -> List[Recipient]:
        """Return all recipients belonging to a job (ordered by creation)."""
        return (
            self._db.query(Recipient)
            .filter(Recipient.job_id == job_id)
            .order_by(Recipient.created_at)
            .all()
        )

    def get_pending_by_job_id(self, job_id: str) -> List[Recipient]:
        """Return only PENDING recipients for a given job."""
        return (
            self._db.query(Recipient)
            .filter(
                Recipient.job_id == job_id,
                Recipient.status == RecipientStatus.PENDING,
            )
            .order_by(Recipient.created_at)
            .all()
        )

    def mark_invalid(self, recipient: Recipient, reason: str) -> None:
        """Mark a recipient as INVALID with the provided reason."""
        recipient.status = RecipientStatus.INVALID
        recipient.error_message = reason
        self._db.flush()

    def mark_success(self, recipient: Recipient, certificate_path: str) -> None:
        """Mark a recipient as SUCCESS and store the path to their PDF."""
        recipient.status = RecipientStatus.SUCCESS
        recipient.certificate_path = certificate_path
        self._db.flush()

    def mark_failed(self, recipient: Recipient, reason: str) -> None:
        """Mark a recipient as FAILED with the error message."""
        recipient.status = RecipientStatus.FAILED
        recipient.error_message = reason[:500]  # column limit
        self._db.flush()
