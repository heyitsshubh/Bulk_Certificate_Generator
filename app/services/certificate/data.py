"""
CertificateData value object and its Builder.

Design Patterns:
- Value Object  — CertificateData is immutable (frozen dataclass); once
  built it cannot be accidentally mutated by downstream code.
- Builder Pattern — CertificateDataBuilder provides a fluent, readable
  API for assembling CertificateData step by step, enforcing all required
  fields at build() time rather than scattering validation across call sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CertificateData:
    """
    Immutable value object representing all information needed to render
    a single certificate.  Always created via CertificateDataBuilder.
    """

    recipient_name: str
    event_name: str
    issuer: str
    date: date  # Always today — set automatically by the builder


class CertificateDataBuilder:
    """
    Fluent builder for CertificateData.

    Usage::

        data = (
            CertificateDataBuilder()
            .with_recipient("Alice Smith")
            .with_event("Python Bootcamp 2026")
            .with_issuer("Acme Corp")
            .build()
        )
    """

    def __init__(self) -> None:
        self._recipient_name: str = ""
        self._event_name: str = ""
        self._issuer: str = ""

    # ------------------------------------------------------------------
    # Fluent setters
    # ------------------------------------------------------------------

    def with_recipient(self, name: str) -> "CertificateDataBuilder":
        self._recipient_name = name.strip()
        return self

    def with_event(self, event_name: str) -> "CertificateDataBuilder":
        self._event_name = event_name.strip()
        return self

    def with_issuer(self, issuer: str) -> "CertificateDataBuilder":
        self._issuer = issuer.strip()
        return self

    # ------------------------------------------------------------------
    # Terminal operation
    # ------------------------------------------------------------------

    def build(self) -> CertificateData:
        """
        Validate that all required fields are set and return a frozen
        CertificateData instance.  The date is always set to today.

        Raises:
            ValueError: if recipient_name or event_name are missing.
        """
        errors: list[str] = []
        if not self._recipient_name:
            errors.append("recipient_name is required")
        if not self._event_name:
            errors.append("event_name is required")
        if errors:
            raise ValueError("; ".join(errors))

        return CertificateData(
            recipient_name=self._recipient_name,
            event_name=self._event_name,
            issuer=self._issuer or "N/A",
            date=date.today(),
        )
