"""
Abstract Strategy interface for certificate generation.

Design: Strategy Pattern — AbstractCertificateGenerator defines the contract.
Concrete generators (PillowReportLabGenerator, or future alternatives) implement
this interface without requiring any changes to callers (Open/Closed Principle).

Liskov Substitution: any concrete generator can replace another wherever
AbstractCertificateGenerator is expected.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from app.services.certificate.data import CertificateData


class AbstractCertificateGenerator(ABC):
    """
    Strategy interface for generating a certificate PDF to disk.

    Implementors must:
      1. Accept a CertificateData value object (what to put on the cert).
      2. Write a PDF to `output_path`.
      3. Return the resolved output path.
      4. Raise a descriptive exception on failure (caller handles isolation).
    """

    @abstractmethod
    def generate(self, data: CertificateData, output_path: Path) -> Path:
        """
        Generate the certificate and save it to `output_path`.

        Args:
            data:        Immutable value object with all certificate content.
            output_path: Target file path (including filename and .pdf ext).

        Returns:
            The absolute path to the written PDF.

        Raises:
            Exception: Any exception propagates to the caller, which records
                       the failure without aborting other recipients.
        """
        ...
