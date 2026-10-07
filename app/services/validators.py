"""
Recipient data validator.

Design: Single Responsibility — this class does one thing: validate a
recipient's raw input fields and return a structured result.  Validation
logic is completely decoupled from HTTP handling, database access, and
certificate generation.

Using a dedicated ValidationResult dataclass (rather than raising or
returning None) makes the caller's intent explicit and avoids exception-
driven flow control in the happy path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Pre-compiled regex for efficiency when validating many recipients.
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)

_MAX_NAME_LEN  = 150
_MAX_EMAIL_LEN = 254  # RFC 5321 maximum


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a single recipient's fields."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    cleaned_name: str = ""
    cleaned_email: str = ""


class RecipientValidator:
    """
    Validates a recipient's full_name and email against business rules.

    Rules:
      - full_name: non-empty after stripping, ≤ 150 chars, printable chars only.
      - email:     non-empty, ≤ 254 chars, matches RFC-5321-like regex.
    """

    def validate(self, full_name: str, email: str) -> ValidationResult:
        """
        Return a ValidationResult with all accumulated errors (not fail-fast).

        Args:
            full_name: Raw name string from the request.
            email:     Raw email string from the request.

        Returns:
            ValidationResult with is_valid=True if no errors were found.
        """
        errors: list[str] = []
        cleaned_name  = full_name.strip()  if isinstance(full_name, str)  else ""
        cleaned_email = email.strip().lower() if isinstance(email, str) else ""

        # --- full_name ---
        if not cleaned_name:
            errors.append("full_name must not be empty.")
        elif len(cleaned_name) > _MAX_NAME_LEN:
            errors.append(
                f"full_name must be at most {_MAX_NAME_LEN} characters "
                f"(got {len(cleaned_name)})."
            )
        elif not cleaned_name.isprintable():
            errors.append("full_name contains non-printable characters.")

        # --- email ---
        if not cleaned_email:
            errors.append("email must not be empty.")
        elif len(cleaned_email) > _MAX_EMAIL_LEN:
            errors.append(
                f"email must be at most {_MAX_EMAIL_LEN} characters."
            )
        elif not _EMAIL_RE.match(cleaned_email):
            errors.append(f"'{email}' is not a valid email address.")

        return ValidationResult(
            is_valid=not errors,
            errors=errors,
            cleaned_name=cleaned_name,
            cleaned_email=cleaned_email,
        )
