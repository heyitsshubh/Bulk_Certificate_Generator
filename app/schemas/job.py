"""
Pydantic schemas for Job objects.

JobCreateRequest applies strict validation on the job-level fields (event_name,
issuer, recipients list bounds) while delegating per-recipient validation to the
service layer.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, field_validator

from app.models.db import JobStatus
from app.schemas.recipient import RecipientInput, RecipientStatusResponse


class JobCreateRequest(BaseModel):
    """Payload for POST /jobs."""

    event_name: str
    issuer: str
    recipients: List[RecipientInput]

    @field_validator("event_name")
    @classmethod
    def event_name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("event_name must not be empty.")
        if len(v) > 200:
            raise ValueError("event_name must be at most 200 characters.")
        return v

    @field_validator("issuer")
    @classmethod
    def issuer_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("issuer must not be empty.")
        if len(v) > 200:
            raise ValueError("issuer must be at most 200 characters.")
        return v

    @field_validator("recipients")
    @classmethod
    def recipients_bounds(cls, v: List[RecipientInput]) -> List[RecipientInput]:
        if not v:
            raise ValueError("recipients list must contain at least one entry.")
        if len(v) > 1000:
            raise ValueError(
                "recipients list must not exceed 1000 entries per job."
            )
        return v


class JobCreateResponse(BaseModel):
    """Returned immediately after accepting a job (HTTP 202)."""

    job_id: str
    status: JobStatus
    total: int
    message: str


class JobStatusResponse(BaseModel):
    """Full job status including counters."""

    job_id: str
    event_name: str
    issuer: str
    status: JobStatus
    total: int
    succeeded: int
    failed: int
    invalid: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class JobRecipientsResponse(BaseModel):
    """List of recipients and their individual statuses for a given job."""

    job_id: str
    total: int
    recipients: List[RecipientStatusResponse]
