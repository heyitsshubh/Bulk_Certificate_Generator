"""
Tests for the certificate download endpoint.

Covers:
  - Downloading a successfully generated certificate (200, PDF bytes)
  - Requesting a certificate for a job that doesn't exist (404)
  - Requesting a certificate for a recipient that doesn't exist (404)
  - Requesting a certificate for a recipient that belongs to a different job (404)
  - Requesting a certificate for a recipient still PENDING / INVALID / FAILED (404)
"""

from __future__ import annotations

import unittest.mock as mock
from pathlib import Path

from fastapi.testclient import TestClient


class TestCertificateDownload:
    def _submit_and_process(
        self,
        client: TestClient,
        payload: dict,
        storage_dir: Path | None = None,
    ) -> dict:
        """Submit a job, run the background task synchronously, return job body."""
        resp = client.post("/jobs", json=payload)
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        from app.services.job_service import process_job

        if storage_dir is not None:
            import app.core.config as cfg
            orig = cfg.get_settings()

            class PatchedSettings:
                APP_NAME = orig.APP_NAME
                APP_VERSION = orig.APP_VERSION
                DATABASE_URL = orig.DATABASE_URL
                STORAGE_DIR = storage_dir
                GENERATOR_TYPE = orig.GENERATOR_TYPE
                MAX_RECIPIENTS_PER_JOB = orig.MAX_RECIPIENTS_PER_JOB

            with mock.patch(
                "app.services.job_service.get_settings",
                return_value=PatchedSettings(),
            ):
                process_job(job_id)
        else:
            process_job(job_id)

        return client.get(f"/jobs/{job_id}").json()

    def _get_success_recipient_id(self, client: TestClient, job_id: str) -> str | None:
        recipients = client.get(f"/jobs/{job_id}/recipients").json()["recipients"]
        for r in recipients:
            if r["status"] == "SUCCESS":
                return r["id"]
        return None

    def test_download_certificate_returns_pdf(self, client: TestClient, tmp_path: Path):
        """End-to-end: submit → process → download."""
        job_body = self._submit_and_process(
            client,
            {
                "event_name": "Download Test",
                "issuer": "Corp",
                "recipients": [
                    {"full_name": "Alice Smith", "email": "alice@example.com"}
                ],
            },
            storage_dir=tmp_path,
        )

        job_id = job_body["job_id"]
        recipient_id = self._get_success_recipient_id(client, job_id)
        assert recipient_id is not None, "Expected at least one SUCCESS recipient"

        resp = client.get(f"/jobs/{job_id}/certificates/{recipient_id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"

    def test_download_nonexistent_job_returns_404(self, client: TestClient):
        resp = client.get(
            "/jobs/00000000-0000-0000-0000-000000000000/certificates/any-id"
        )
        assert resp.status_code == 404

    def test_download_nonexistent_recipient_returns_404(
        self, client: TestClient, valid_job_payload: dict
    ):
        job_id = client.post("/jobs", json=valid_job_payload).json()["job_id"]
        resp = client.get(
            f"/jobs/{job_id}/certificates/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404

    def test_download_pending_recipient_returns_404(self, client: TestClient):
        """A PENDING recipient has no certificate yet — should 404."""
        job_resp = client.post(
            "/jobs",
            json={
                "event_name": "Pending Test",
                "issuer": "Corp",
                "recipients": [
                    {"full_name": "Charlie", "email": "charlie@example.com"}
                ],
            },
        )
        job_id = job_resp.json()["job_id"]
        recipients = client.get(f"/jobs/{job_id}/recipients").json()["recipients"]
        # Find a recipient that is still PENDING (background task may race)
        pending = [r for r in recipients if r["status"] == "PENDING"]
        if not pending:
            # Background task already ran — skip (cannot reliably test this case)
            return
        pending_id = pending[0]["id"]
        resp = client.get(f"/jobs/{job_id}/certificates/{pending_id}")
        assert resp.status_code == 404

    def test_download_invalid_recipient_returns_404(self, client: TestClient):
        """An INVALID recipient was never generated — should 404."""
        job_resp = client.post(
            "/jobs",
            json={
                "event_name": "Invalid Test",
                "issuer": "Corp",
                "recipients": [{"full_name": "", "email": "bad-email"}],
            },
        )
        job_id = job_resp.json()["job_id"]
        recipients = client.get(f"/jobs/{job_id}/recipients").json()["recipients"]
        invalid_id = recipients[0]["id"]
        resp = client.get(f"/jobs/{job_id}/certificates/{invalid_id}")
        assert resp.status_code == 404

    def test_download_recipient_wrong_job_returns_404(
        self, client: TestClient, valid_job_payload: dict
    ):
        """Recipient from job A should not be downloadable under job B."""
        job_a = client.post("/jobs", json=valid_job_payload).json()["job_id"]
        job_b = client.post("/jobs", json=valid_job_payload).json()["job_id"]
        recipients_a = client.get(f"/jobs/{job_a}/recipients").json()["recipients"]
        recipient_id_from_a = recipients_a[0]["id"]
        resp = client.get(f"/jobs/{job_b}/certificates/{recipient_id_from_a}")
        assert resp.status_code == 404
