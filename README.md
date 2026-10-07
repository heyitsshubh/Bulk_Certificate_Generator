# Bulk Certificate Generator

A production-grade FastAPI backend that accepts bulk certificate generation requests, validates recipients, generates PDF certificates from a predefined template, tracks job progress in a relational database, and serves the generated files for download.

---

## Table of Contents

1. [Features](#features)
2. [Architecture & Design Decisions](#architecture--design-decisions)
3. [Project Structure](#project-structure)
4. [Setup & Installation](#setup--installation)
5. [Running the Application](#running-the-application)
6. [Running Tests](#running-tests)
7. [API Reference](#api-reference)
8. [Submitting a Certificate Generation Request](#submitting-a-certificate-generation-request)
9. [Retrieving Generated Certificates](#retrieving-generated-certificates)

---

## Features

- **Bulk generation** — one request, many recipients (up to 1,000 per job)
- **Failure isolation** — one bad recipient never aborts the rest
- **Per-recipient status** — each recipient is tracked individually (PENDING → SUCCESS / FAILED / INVALID)
- **Background processing** — API returns immediately (HTTP 202); generation runs asynchronously
- **Job progress polling** — clients poll `GET /jobs/{job_id}` to check progress and counters
- **PDF download** — `GET /jobs/{job_id}/certificates/{recipient_id}` streams the PDF
- **Interactive API docs** — auto-generated at `http://localhost:8000/docs`

---

## Architecture & Design Decisions

### Why FastAPI?

FastAPI provides async-first routing, built-in `BackgroundTasks`, automatic OpenAPI documentation, and native Pydantic v2 integration — all with minimal boilerplate.

### Background Processing — BackgroundTasks vs. Celery

**Choice:** FastAPI's built-in `BackgroundTasks`.

The API returns HTTP 202 immediately with a `job_id`. Generation runs in a background thread. The client polls for progress.

**Rationale:**
- Zero infrastructure overhead (no Redis, no worker processes).
- Adequate for the use-case: certificate generation is CPU-light and the expected job frequency is low (per-event, not continuous).

**Trade-off:** `BackgroundTasks` runs in the same process. Under high concurrency (hundreds of simultaneous jobs), a dedicated task queue (Celery + Redis) would be more resilient. The generator code is completely decoupled from the transport mechanism, so swapping to Celery requires changing only `job_service.py`.

### SOLID Principles Applied

| Principle | Where |
|---|---|
| **S**ingle Responsibility | `JobService` (orchestration), `RecipientValidator` (validation), `PillowReportLabGenerator` (rendering) each do one thing |
| **O**pen/Closed | `CertificateGeneratorFactory.register()` adds new backends without modifying existing code |
| **L**iskov Substitution | Any `AbstractCertificateGenerator` subclass can replace another |
| **I**nterface Segregation | `BaseRepository` exposes only the operations models actually need |
| **D**ependency Inversion | `JobService` depends on `AbstractCertificateGenerator`, not on `PillowReportLabGenerator` |

### Design Patterns

| Pattern | Where | Purpose |
|---|---|---|
| **Singleton** | `get_settings()` via `@lru_cache` | Single `Settings` instance across the app |
| **Repository** | `BaseRepository[T]`, `JobRepository`, `RecipientRepository` | Decouple data-access from business logic |
| **Strategy** | `AbstractCertificateGenerator` → `PillowReportLabGenerator` | Swap PDF backends without touching service code |
| **Factory** | `CertificateGeneratorFactory` | Create the right generator from a config key |
| **Builder** | `CertificateDataBuilder` | Fluent, validated construction of `CertificateData` |
| **Value Object** | `CertificateData` (frozen dataclass) | Immutable, safe to pass between layers |

### Validation Strategy

Pydantic validates the **job envelope** (event_name, issuer, recipients list bounds).  
`RecipientValidator` validates each **recipient's fields** in the service layer — this allows the API to accept the full batch and mark individual bad rows as `INVALID` rather than rejecting the whole request with a 422.

### Certificate Generation

Certificates are rendered in-memory using **Pillow** (pixel-level text drawing onto a procedurally generated canvas) and then wrapped as a **PDF** by **ReportLab**. No external binary dependencies (like a headless browser) are required.

The date on the certificate is always set to the current date at generation time.

Font loading uses a priority-ordered fallback chain: bundled TTF fonts → common system fonts (Windows/macOS/Linux) → Pillow's built-in bitmap font.

---

## Project Structure

```
cert-generator/
├── app/
│   ├── main.py                          # FastAPI app, lifespan, router registration
│   ├── core/
│   │   ├── config.py                    # Singleton settings (pydantic-settings)
│   │   ├── database.py                  # SQLAlchemy engine + session factory
│   │   └── exceptions.py               # Typed HTTP exception hierarchy
│   ├── models/
│   │   └── db.py                        # Job + Recipient ORM models, status enums
│   ├── schemas/
│   │   ├── job.py                       # Pydantic request/response schemas for jobs
│   │   └── recipient.py                 # Pydantic schemas for recipients
│   ├── repositories/
│   │   ├── base.py                      # Generic BaseRepository[T]
│   │   ├── job_repository.py            # Job CRUD + status helpers
│   │   └── recipient_repository.py      # Recipient CRUD + status helpers
│   ├── services/
│   │   ├── certificate/
│   │   │   ├── base.py                  # AbstractCertificateGenerator (Strategy)
│   │   │   ├── data.py                  # CertificateData + CertificateDataBuilder
│   │   │   ├── factory.py              # CertificateGeneratorFactory (Factory)
│   │   │   └── pillow_generator.py      # Pillow + ReportLab implementation
│   │   ├── validators.py               # RecipientValidator
│   │   └── job_service.py              # JobService + process_job background task
│   └── routers/
│       ├── jobs.py                      # POST /jobs, GET /jobs/{id}, GET /jobs/{id}/recipients
│       └── certificates.py             # GET /jobs/{id}/certificates/{rid}
├── storage/
│   └── certificates/                    # Generated PDFs stored here
├── tests/
│   ├── conftest.py                      # Fixtures (in-memory DB, TestClient)
│   ├── test_jobs.py                     # Job creation + status endpoint tests
│   ├── test_generation.py               # Unit tests: builder, validator, factory, generator
│   └── test_certificates.py            # Certificate download endpoint tests
├── .env.example
├── requirements.txt
└── README.md
```

---

## Setup & Installation

### Prerequisites

- Python 3.11 or newer
- pip

### Steps

```bash
# 1. Clone or navigate to the project directory
cd cert-generator

# 2. Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Copy the example environment file
copy .env.example .env      # Windows
cp  .env.example .env       # macOS / Linux
```

No additional setup is required. The SQLite database file and the `storage/` directory are created automatically on first run.

---

## Running the Application

```bash
uvicorn app.main:app --reload
```

The API is available at **http://localhost:8000**.  
Interactive docs (Swagger UI): **http://localhost:8000/docs**  
Alternative docs (ReDoc): **http://localhost:8000/redoc**

---

## Running Tests

```bash
pytest tests/ -v --tb=short
```

All tests use an in-memory SQLite database — no external services required.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/jobs` | Submit a bulk generation job (202 Accepted) |
| `GET` | `/jobs/{job_id}` | Get job status + counters |
| `GET` | `/jobs/{job_id}/recipients` | List all recipients with individual statuses |
| `GET` | `/jobs/{job_id}/certificates/{recipient_id}` | Download a generated certificate PDF |
| `GET` | `/health` | Health check |

---

## Submitting a Certificate Generation Request

### Request

```http
POST /jobs
Content-Type: application/json
```

```json
{
  "event_name": "Python Bootcamp 2026",
  "issuer": "Acme Corp",
  "recipients": [
    { "full_name": "Alice Smith", "email": "alice@example.com" },
    { "full_name": "Bob Jones",   "email": "bob@example.com" },
    { "full_name": "",            "email": "bad-email" }
  ]
}
```

### Response (202 Accepted)

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "PENDING",
  "total": 3,
  "message": "Job accepted. 3 recipients queued (1 failed validation). Poll GET /jobs/3fa85f64... for progress."
}
```

**Validation rules:**
- `event_name` — non-empty string, max 200 characters
- `issuer` — non-empty string, max 200 characters
- `recipients` — non-empty list, maximum 1,000 entries
- Per recipient:
  - `full_name` — non-empty after stripping whitespace, max 150 characters
  - `email` — must match a standard email pattern

Recipients that fail validation are persisted as `INVALID` (with an error message) and skipped during generation. The job continues for all valid recipients.

### Checking Progress

```http
GET /jobs/{job_id}
```

```json
{
  "job_id": "3fa85f64-...",
  "event_name": "Python Bootcamp 2026",
  "issuer": "Acme Corp",
  "status": "PARTIAL",
  "total": 3,
  "succeeded": 2,
  "failed": 0,
  "invalid": 1,
  "created_at": "2026-10-07T04:20:00+00:00",
  "updated_at": "2026-10-07T04:20:03+00:00"
}
```

**Job status values:**

| Status | Meaning |
|---|---|
| `PENDING` | Accepted, background task not yet started |
| `PROCESSING` | Background task is actively generating |
| `COMPLETED` | All valid recipients succeeded |
| `PARTIAL` | At least one succeeded; some failed or were invalid |
| `FAILED` | All valid recipients failed (or a system error occurred) |

### Listing Recipients

```http
GET /jobs/{job_id}/recipients
```

Returns each recipient's `id`, `full_name`, `email`, `status`, and `error_message` (if applicable).

---

## Retrieving Generated Certificates

```http
GET /jobs/{job_id}/certificates/{recipient_id}
```

- Returns the PDF as a binary download (`application/pdf`).
- The `Content-Disposition` header includes the filename: `certificate_Alice_Smith.pdf`.
- Returns 404 if: the job doesn't exist, the recipient doesn't exist, the recipient belongs to a different job, or the certificate has not been generated yet (status ≠ SUCCESS).

### Example (curl)

```bash
# 1. Submit a job
curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Python Bootcamp 2026",
    "issuer": "Acme Corp",
    "recipients": [
      {"full_name": "Alice Smith", "email": "alice@example.com"}
    ]
  }' | python -m json.tool

# 2. Check status (replace JOB_ID)
curl http://localhost:8000/jobs/{JOB_ID} | python -m json.tool

# 3. List recipients to get recipient IDs
curl http://localhost:8000/jobs/{JOB_ID}/recipients | python -m json.tool

# 4. Download the certificate
curl -OJ http://localhost:8000/jobs/{JOB_ID}/certificates/{RECIPIENT_ID}
```
