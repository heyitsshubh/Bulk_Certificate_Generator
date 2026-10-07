"""
Unit tests for certificate generation logic.

Covers:
  - CertificateDataBuilder: normal build, missing fields raise ValueError
  - CertificateData: immutability (frozen dataclass)
  - RecipientValidator: valid input, invalid email, empty name, edge cases
  - CertificateGeneratorFactory: returns correct concrete type
  - PillowReportLabGenerator: generates a real PDF file
  - Failure isolation: one bad recipient doesn't block others (via process_job)
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from app.services.certificate.data import CertificateData, CertificateDataBuilder
from app.services.certificate.factory import CertificateGeneratorFactory
from app.services.certificate.pillow_generator import PillowReportLabGenerator
from app.services.validators import RecipientValidator


# ---------------------------------------------------------------------------
# CertificateDataBuilder
# ---------------------------------------------------------------------------


class TestCertificateDataBuilder:
    def test_build_returns_certificate_data(self):
        data = (
            CertificateDataBuilder()
            .with_recipient("Alice Smith")
            .with_event("Python Bootcamp")
            .with_issuer("Acme Corp")
            .build()
        )
        assert isinstance(data, CertificateData)
        assert data.recipient_name == "Alice Smith"
        assert data.event_name == "Python Bootcamp"
        assert data.issuer == "Acme Corp"

    def test_date_is_always_today(self):
        data = (
            CertificateDataBuilder()
            .with_recipient("Bob")
            .with_event("Event")
            .build()
        )
        assert data.date == date.today()

    def test_missing_recipient_raises(self):
        with pytest.raises(ValueError, match="recipient_name"):
            CertificateDataBuilder().with_event("Event").build()

    def test_missing_event_raises(self):
        with pytest.raises(ValueError, match="event_name"):
            CertificateDataBuilder().with_recipient("Alice").build()

    def test_strips_whitespace(self):
        data = (
            CertificateDataBuilder()
            .with_recipient("  Alice  ")
            .with_event("  Bootcamp  ")
            .with_issuer("  Corp  ")
            .build()
        )
        assert data.recipient_name == "Alice"
        assert data.event_name == "Bootcamp"
        assert data.issuer == "Corp"

    def test_issuer_defaults_to_na_when_empty(self):
        data = (
            CertificateDataBuilder()
            .with_recipient("Alice")
            .with_event("Event")
            .build()
        )
        assert data.issuer == "N/A"

    def test_certificate_data_is_immutable(self):
        data = (
            CertificateDataBuilder()
            .with_recipient("Alice")
            .with_event("Event")
            .build()
        )
        with pytest.raises((AttributeError, TypeError)):
            data.recipient_name = "Bob"  # type: ignore[misc]

    def test_fluent_chaining_returns_builder(self):
        builder = CertificateDataBuilder()
        result = builder.with_recipient("X").with_event("Y").with_issuer("Z")
        assert result is builder  # same object — fluent API


# ---------------------------------------------------------------------------
# RecipientValidator
# ---------------------------------------------------------------------------


class TestRecipientValidator:
    def setup_method(self):
        self.validator = RecipientValidator()

    def test_valid_input_passes(self):
        result = self.validator.validate("Alice Smith", "alice@example.com")
        assert result.is_valid is True
        assert result.errors == []
        assert result.cleaned_name == "Alice Smith"
        assert result.cleaned_email == "alice@example.com"

    def test_empty_name_fails(self):
        result = self.validator.validate("", "alice@example.com")
        assert result.is_valid is False
        assert any("full_name" in e for e in result.errors)

    def test_whitespace_only_name_fails(self):
        result = self.validator.validate("   ", "alice@example.com")
        assert result.is_valid is False

    def test_name_too_long_fails(self):
        result = self.validator.validate("A" * 151, "alice@example.com")
        assert result.is_valid is False

    def test_invalid_email_no_at_fails(self):
        result = self.validator.validate("Alice", "notanemail")
        assert result.is_valid is False
        assert any("email" in e.lower() for e in result.errors)

    def test_invalid_email_no_domain_fails(self):
        result = self.validator.validate("Alice", "alice@")
        assert result.is_valid is False

    def test_empty_email_fails(self):
        result = self.validator.validate("Alice", "")
        assert result.is_valid is False

    def test_accumulates_multiple_errors(self):
        result = self.validator.validate("", "bad-email")
        assert result.is_valid is False
        assert len(result.errors) >= 2

    def test_email_is_lowercased(self):
        result = self.validator.validate("Alice", "ALICE@EXAMPLE.COM")
        assert result.is_valid is True
        assert result.cleaned_email == "alice@example.com"

    def test_name_whitespace_is_stripped(self):
        result = self.validator.validate("  Alice Smith  ", "a@b.com")
        assert result.cleaned_name == "Alice Smith"


# ---------------------------------------------------------------------------
# CertificateGeneratorFactory
# ---------------------------------------------------------------------------


class TestCertificateGeneratorFactory:
    def test_create_returns_pillow_generator_by_default(self):
        generator = CertificateGeneratorFactory.create()
        assert isinstance(generator, PillowReportLabGenerator)

    def test_register_and_create_custom_generator(self):
        from app.services.certificate.base import AbstractCertificateGenerator

        class FakeGenerator(AbstractCertificateGenerator):
            def generate(self, data, output_path):
                return output_path

        CertificateGeneratorFactory.register("fake", FakeGenerator)
        # Temporarily patch settings
        import app.core.config as cfg_module
        original = cfg_module.get_settings()

        class PatchedSettings:
            GENERATOR_TYPE = "fake"
            STORAGE_DIR = original.STORAGE_DIR

        import unittest.mock as mock
        with mock.patch("app.services.certificate.factory.get_settings", return_value=PatchedSettings()):
            gen = CertificateGeneratorFactory.create()
        assert isinstance(gen, FakeGenerator)

    def test_unknown_generator_type_raises(self):
        import unittest.mock as mock
        import app.core.config as cfg_module

        class BadSettings:
            GENERATOR_TYPE = "nonexistent_backend"

        with mock.patch("app.services.certificate.factory.get_settings", return_value=BadSettings()):
            with pytest.raises(ValueError, match="nonexistent_backend"):
                CertificateGeneratorFactory.create()


# ---------------------------------------------------------------------------
# PillowReportLabGenerator — real PDF generation
# ---------------------------------------------------------------------------


class TestPillowReportLabGenerator:
    def _make_data(self, name: str = "Test User") -> CertificateData:
        return (
            CertificateDataBuilder()
            .with_recipient(name)
            .with_event("Test Event 2026")
            .with_issuer("Test Corp")
            .build()
        )

    def test_generate_creates_pdf_file(self):
        generator = PillowReportLabGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test_cert.pdf"
            result = generator.generate(self._make_data(), out)
            assert result.exists()
            assert result.suffix == ".pdf"
            assert result.stat().st_size > 0

    def test_generate_creates_valid_pdf_header(self):
        """Generated file must start with the %PDF magic bytes."""
        generator = PillowReportLabGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "cert.pdf"
            generator.generate(self._make_data(), out)
            with open(out, "rb") as f:
                header = f.read(4)
            assert header == b"%PDF"

    def test_generate_creates_parent_directories(self):
        generator = PillowReportLabGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "nested" / "dirs" / "cert.pdf"
            assert not out.parent.exists()
            generator.generate(self._make_data(), out)
            assert out.exists()

    def test_generate_long_name(self):
        """Long names should not crash the generator."""
        generator = PillowReportLabGenerator()
        long_name = "A" * 100
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "long.pdf"
            generator.generate(self._make_data(long_name), out)
            assert out.exists()

    def test_generate_unicode_name(self):
        """Unicode characters in the name should be handled gracefully."""
        generator = PillowReportLabGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "unicode.pdf"
            # Should not raise; may fall back to replacement characters
            generator.generate(self._make_data("José García"), out)
            assert out.exists()


# ---------------------------------------------------------------------------
# Failure isolation — one bad recipient must not block others
# ---------------------------------------------------------------------------


class TestFailureIsolation:
    def test_bad_recipient_does_not_block_good_ones(self, client, tmp_path):
        """
        Submit a job where one recipient will cause a generation error
        (by monkeypatching the generator) and verify the other succeeds.
        """
        import unittest.mock as mock
        from app.services import job_service as js_module

        call_count = {"n": 0}

        def flaky_generate(self, data, output_path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("Simulated generation failure")
            # Second call: actually write a tiny PDF placeholder
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"%PDF-1.4 mock")
            return output_path

        with mock.patch.object(PillowReportLabGenerator, "generate", flaky_generate):
            resp = client.post("/jobs", json={
                "event_name": "Isolation Test",
                "issuer": "Corp",
                "recipients": [
                    {"full_name": "Will Fail",    "email": "fail@example.com"},
                    {"full_name": "Will Succeed", "email": "ok@example.com"},
                ],
            })
            assert resp.status_code == 202
            job_id = resp.json()["job_id"]
        
        status_resp = client.get(f"/jobs/{job_id}")
        body = status_resp.json()
        assert body["failed"] == 1
        assert body["succeeded"] == 1
        assert body["status"] in ("PARTIAL",)
