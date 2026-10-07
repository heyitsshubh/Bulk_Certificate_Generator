"""
Tests for job creation, validation, and status endpoints.

Covers:
  - Creating a valid job (POST /jobs)
  - Empty recipients list → 422
  - Too many recipients → 422
  - Empty event_name → 422
  - Recipient with invalid email → marked INVALID, job still proceeds
  - Recipient with empty full_name → marked INVALID
  - GET /jobs/{job_id} — status polling
  - GET /jobs/{job_id}/recipients — per-recipient list
  - GET /jobs/nonexistent → 404
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


class TestCreateJob:
    def test_valid_job_returns_202(self, client: TestClient, valid_job_payload: dict):
        resp = client.post("/jobs", json=valid_job_payload)
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert body["total"] == 2
        assert body["status"] == "PENDING"
        assert body["job_id"] in body["message"]

    def test_valid_job_has_unique_ids(self, client: TestClient, valid_job_payload: dict):
        r1 = client.post("/jobs", json=valid_job_payload).json()
        r2 = client.post("/jobs", json=valid_job_payload).json()
        assert r1["job_id"] != r2["job_id"]

    def test_empty_recipients_returns_422(self, client: TestClient):
        resp = client.post("/jobs", json={
            "event_name": "Bootcamp",
            "issuer": "Corp",
            "recipients": [],
        })
        assert resp.status_code == 422

    def test_too_many_recipients_returns_422(self, client: TestClient):
        recipients = [
            {"full_name": f"Person {i}", "email": f"p{i}@x.com"}
            for i in range(1001)
        ]
        resp = client.post("/jobs", json={
            "event_name": "Big Event",
            "issuer": "Corp",
            "recipients": recipients,
        })
        assert resp.status_code == 422

    def test_empty_event_name_returns_422(self, client: TestClient):
        resp = client.post("/jobs", json={
            "event_name": "   ",
            "issuer": "Corp",
            "recipients": [{"full_name": "Alice", "email": "a@b.com"}],
        })
        assert resp.status_code == 422

    def test_empty_issuer_returns_422(self, client: TestClient):
        resp = client.post("/jobs", json={
            "event_name": "Event",
            "issuer": "",
            "recipients": [{"full_name": "Alice", "email": "a@b.com"}],
        })
        assert resp.status_code == 422

    def test_missing_recipients_field_returns_422(self, client: TestClient):
        resp = client.post("/jobs", json={"event_name": "Event", "issuer": "X"})
        assert resp.status_code == 422

    def test_invalid_email_recipient_marked_invalid(self, client: TestClient):
        """A bad email should not abort the whole job — that recipient is INVALID."""
        resp = client.post("/jobs", json={
            "event_name": "Workshop",
            "issuer": "Corp",
            "recipients": [
                {"full_name": "Good Person", "email": "good@example.com"},
                {"full_name": "Bad Person",  "email": "not-an-email"},
            ],
        })
        assert resp.status_code == 202
        body = resp.json()
        job_id = body["job_id"]
        assert body["total"] == 2

        # Check recipients endpoint for per-row statuses
        r_resp = client.get(f"/jobs/{job_id}/recipients")
        assert r_resp.status_code == 200
        recipients = r_resp.json()["recipients"]
        statuses = {r["email"]: r["status"] for r in recipients}
        assert statuses.get("not-an-email") == "INVALID"
        assert statuses.get("good@example.com") in ("PENDING", "SUCCESS")

    def test_empty_name_recipient_marked_invalid(self, client: TestClient):
        resp = client.post("/jobs", json={
            "event_name": "Workshop",
            "issuer": "Corp",
            "recipients": [
                {"full_name": "   ", "email": "valid@example.com"},
            ],
        })
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        r_resp = client.get(f"/jobs/{job_id}/recipients")
        recipients = r_resp.json()["recipients"]
        assert recipients[0]["status"] == "INVALID"
        assert "full_name" in recipients[0]["error_message"].lower()


class TestJobStatus:
    def test_get_job_status_returns_correct_fields(
        self, client: TestClient, valid_job_payload: dict
    ):
        job_id = client.post("/jobs", json=valid_job_payload).json()["job_id"]
        resp = client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job_id
        assert body["event_name"] == valid_job_payload["event_name"]
        assert body["issuer"] == valid_job_payload["issuer"]
        assert body["total"] == 2
        assert "status" in body
        assert "succeeded" in body
        assert "failed" in body
        assert "invalid" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_get_nonexistent_job_returns_404(self, client: TestClient):
        resp = client.get("/jobs/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_get_recipients_returns_list(
        self, client: TestClient, valid_job_payload: dict
    ):
        job_id = client.post("/jobs", json=valid_job_payload).json()["job_id"]
        resp = client.get(f"/jobs/{job_id}/recipients")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job_id
        assert body["total"] == 2
        assert len(body["recipients"]) == 2

    def test_get_recipients_for_nonexistent_job_returns_404(
        self, client: TestClient
    ):
        resp = client.get("/jobs/nonexistent-id/recipients")
        assert resp.status_code == 404

    def test_all_invalid_recipients_job_status_reflects_invalid_count(
        self, client: TestClient
    ):
        resp = client.post("/jobs", json={
            "event_name": "Test",
            "issuer": "Corp",
            "recipients": [
                {"full_name": "", "email": "bad"},
                {"full_name": "X", "email": "also-bad"},
            ],
        })
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        # Wait briefly for background task to finish
        time.sleep(0.5)
        status_resp = client.get(f"/jobs/{job_id}")
        assert status_resp.json()["invalid"] == 2
