"""
ORM models for the application.

Two tables:
  - Job        — represents a single bulk generation request.
  - Recipient  — represents one certificate recipient within a job.

Status enums use Python's str + enum.Enum so SQLAlchemy stores them as
VARCHAR strings, which are human-readable in SQL queries and portable
across databases.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def _uuid() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class JobStatus(str, enum.Enum):
    """Lifecycle states for a bulk generation job."""

    PENDING = "PENDING"          # Job accepted, not yet processing
    PROCESSING = "PROCESSING"    # Background task is actively running
    COMPLETED = "COMPLETED"      # All valid recipients succeeded
    PARTIAL = "PARTIAL"          # Some recipients failed / were invalid
    FAILED = "FAILED"            # All valid recipients failed (or system error)


class RecipientStatus(str, enum.Enum):
    """Per-recipient outcome."""

    PENDING = "PENDING"    # Awaiting generation
    SUCCESS = "SUCCESS"    # Certificate generated successfully
    FAILED = "FAILED"      # Valid data, but generation raised an exception
    INVALID = "INVALID"    # Failed business validation (e.g., bad email)


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class Job(Base):
    """A bulk certificate generation job submitted by the client."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    event_name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str] = mapped_column(String(200), nullable=False)

    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, values_callable=lambda e: [m.value for m in e]),
        default=JobStatus.PENDING,
        nullable=False,
    )

    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    succeeded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    recipients: Mapped[list["Recipient"]] = relationship(
        "Recipient", back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id!r} status={self.status!r}>"


class Recipient(Base):
    """A single certificate recipient within a job."""

    __tablename__ = "recipients"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)

    status: Mapped[RecipientStatus] = mapped_column(
        SAEnum(
            RecipientStatus,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RecipientStatus.PENDING,
        nullable=False,
    )

    error_message: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    certificate_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    job: Mapped["Job"] = relationship("Job", back_populates="recipients")

    def __repr__(self) -> str:
        return (
            f"<Recipient id={self.id!r} name={self.full_name!r} "
            f"status={self.status!r}>"
        )
