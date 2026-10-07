"""
Pydantic schemas for Recipient objects.

Design: Separation of concerns — RecipientInput is a lenient schema that
accepts raw strings so that per-recipient validation happens in the service
layer (RecipientValidator), not at the HTTP boundary.  This allows the API
to accept a full batch and mark individual bad recipients as INVALID rather
than rejecting the entire request.

RecipientStatusResponse is the read-only view used in API responses.
"""

from pydantic import BaseModel

from app.models.db import RecipientStatus


class RecipientInput(BaseModel):
    """
    Input schema for a single recipient.

    Intentionally permissive — full_name and email are accepted as plain
    strings.  Business validation is performed by RecipientValidator in the
    service layer so that individual bad rows don't abort the entire job.
    """

    full_name: str
    email: str


class RecipientStatusResponse(BaseModel):
    """Read-only view of a recipient and its current generation status."""

    id: str
    full_name: str
    email: str
    status: RecipientStatus
    error_message: str | None = None

    model_config = {"from_attributes": True}
