"""
CertificateGeneratorFactory — Factory Pattern.

Design:
- Factory Pattern: centralises the creation of AbstractCertificateGenerator
  objects.  Callers never `import` or instantiate concrete generators directly.
- Open/Closed: new generator backends (e.g., WeasyPrint) can be registered
  via `register()` without changing any existing code.
- Dependency Inversion: the factory returns the abstract interface type, so
  every consumer is coded against the abstraction, not a concrete class.
"""

from __future__ import annotations

from typing import Dict, Type

from app.core.config import get_settings
from app.services.certificate.base import AbstractCertificateGenerator


class CertificateGeneratorFactory:
    """
    Creates AbstractCertificateGenerator instances from a string key.

    The registry maps string identifiers (matching the GENERATOR_TYPE
    setting) to concrete generator classes.  New backends are added with
    `CertificateGeneratorFactory.register(...)` — no if/elif chains.
    """

    _registry: Dict[str, Type[AbstractCertificateGenerator]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        generator_cls: Type[AbstractCertificateGenerator],
    ) -> None:
        """
        Register a concrete generator under a string key.

        Args:
            name:          Identifier matched against GENERATOR_TYPE config.
            generator_cls: A subclass of AbstractCertificateGenerator.

        Example::

            CertificateGeneratorFactory.register(
                "my_backend", MyCustomGenerator
            )
        """
        cls._registry[name] = generator_cls

    @classmethod
    def create(cls) -> AbstractCertificateGenerator:
        """
        Instantiate and return the generator configured in settings.

        Raises:
            ValueError: if GENERATOR_TYPE is not in the registry.
        """
        settings = get_settings()
        generator_type = settings.GENERATOR_TYPE
        generator_cls = cls._registry.get(generator_type)
        if generator_cls is None:
            available = ", ".join(cls._registry.keys()) or "(none registered)"
            raise ValueError(
                f"Unknown generator type '{generator_type}'. "
                f"Available: {available}"
            )
        return generator_cls()


# ---------------------------------------------------------------------------
# Register the built-in backend at import time.
# This import is intentionally local to avoid circular imports.
# ---------------------------------------------------------------------------

def _register_defaults() -> None:
    from app.services.certificate.pillow_generator import PillowReportLabGenerator

    CertificateGeneratorFactory.register("pillow_reportlab", PillowReportLabGenerator)


_register_defaults()
