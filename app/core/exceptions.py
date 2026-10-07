"""
Custom HTTP exception types for the application.

Design: Single Responsibility — each exception class carries only the status
code and a default detail message relevant to one failure scenario.
New error cases are added by subclassing HTTPException, not by modifying
existing handlers (Open/Closed Principle).
"""

from fastapi import HTTPException, status


class JobNotFoundException(HTTPException):
    """Raised when a requested job does not exist in the database."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )


class RecipientNotFoundException(HTTPException):
    """Raised when a requested recipient does not exist or has no certificate."""

    def __init__(self, recipient_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recipient '{recipient_id}' not found or certificate not yet generated.",
        )


class CertificateFileNotFoundException(HTTPException):
    """Raised when the certificate PDF file is missing from disk."""

    def __init__(self, path: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate file not found on disk: {path}",
        )


class RecipientJobMismatchException(HTTPException):
    """Raised when a recipient does not belong to the given job."""

    def __init__(self, recipient_id: str, job_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Recipient '{recipient_id}' does not belong to job '{job_id}'."
            ),
        )
