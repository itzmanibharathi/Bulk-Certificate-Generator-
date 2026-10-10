# CertiFlow — Bulk Certificate Generator

A production-ready full-stack application for asynchronous bulk certificate generation, real-time status monitoring, individual failure isolation, and single/ZIP downloads. Built with a high-performance **FastAPI** backend and a modern **React (Vite)** frontend featuring a custom glassmorphic design system.

---

## Table of Contents
- [Core Features](#core-features)
- [Architecture & Tech Stack](#architecture--tech-stack)
- [Core Design Decisions & Rationale](#core-design-decisions--rationale)
- [Project Structure](#project-structure)
- [Installation & Setup](#installation--setup)
- [Running the Application](#running-the-application)
- [Running the Test Suite](#running-the-test-suite)
- [API Reference](#api-reference)
- [Fault Tolerance & Error Isolation Demo](#fault-tolerance--error-isolation-demo)

---

## Core Features

- **Bulk Processing Support:** Accepts a single request containing multiple recipients (hundreds or thousands) and processes them asynchronously out-of-band.
- **Strict Data Validation:** Validates recipient data (`name`, `email`, `course_name`, `issue_date`) with strict Pydantic schemas, rejecting invalid formats with HTTP 422.
- **Programmatic Certificate Rendering:** Generates high-resolution (1920×1280) landscape certificates via Python Pillow (PIL) featuring ornamental gold/navy borders, guilloché watermark motifs, auto-scaled typography, cryptographic QR verification codes, and rosette seals.
- **Fault Tolerance & Failure Isolation:** A failure during the generation of one certificate (e.g. malformed unicode, simulated failure) **never** cancels or prevents sibling certificates from completing. The system tracks individual errors and reports `COMPLETED`, `PARTIAL_FAILURE`, or `FAILED` states.
- **Live Progress Polling:** Frontend monitors real-time progress bars and percentage counters via periodic polling against `GET /api/jobs/{job_id}` until completion.
- **Multi-Channel Retrieval:** Download individual certificates as PNG images, preview them inline in an interactive modal, or download all successful certificates in a single compressed ZIP archive.
- **CSV Ingestion:** Ingest recipients via CSV file uploads (`name, email, course_name, issue_date`) with automatic field normalization and validation.

---

## Architecture & Tech Stack

### Backend
- **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
- **Database & ORM:** [SQLAlchemy 2.0](https://www.sqlalchemy.org/) with SQLite (configurable to PostgreSQL via `DATABASE_URL`)
- **Data Validation:** [Pydantic](https://docs.pydantic.dev/) + [email-validator](https://pypi.org/project/email-validator/)
- **Image Generation:** [Pillow (PIL)](https://pillow.readthedocs.io/) + [qrcode](https://pypi.org/project/qrcode/)
- **Testing:** [Pytest](https://docs.pytest.org/) + [HTTPX](https://www.python-httpx.org/) (FastAPI `TestClient`)
- **Server:** [Uvicorn](https://www.uvicorn.org/) ASGI server

### Frontend
- **Framework:** [React 19](https://react.dev/) + [Vite](https://vitejs.dev/)
- **Icons:** [Lucide React](https://lucide.dev/)
- **Design System:** Custom CSS glassmorphism, animated striped progress bars, dark luxury color palette (`#090d16` canvas with glowing radial gradients).

---

## Core Design Decisions & Rationale

### 1. Asynchronous Background Processing (`BackgroundTasks`)
- **Why not synchronous HTTP?** Bulk rendering involves heavy image synthesis (1080p canvas manipulation, QR code generation, PNG encoding). Executing this synchronously in the request thread would block the client and trigger HTTP timeouts for batches with dozens or hundreds of recipients.
- **Why `BackgroundTasks` instead of Celery/Redis?** FastAPI's native `BackgroundTasks` runs in a separate thread pool out-of-band without introducing external infrastructure dependencies (like Redis, RabbitMQ, or Celery worker daemons). For self-contained services, this provides immediate HTTP responsiveness (returning HTTP 202 Accepted with a unique `job_id`) while keeping the operational footprint minimal.
- **Incremental DB updates:** The worker loop commits updates to the database after each recipient is drawn. This powers live progress polling on the frontend with smooth animations and accurate percentage tracking.

### 2. Fault Tolerance & Failure Isolation
- **Per-Recipient Exception Boundary:** Each recipient generation call in `process_bulk_job` is wrapped in an isolated `try/except` block.
- **State Partitioning:** If recipient #2 fails due to a rendering exception:
  - Recipient #2 is marked `FAILED` with the exact diagnostic recorded in `error_message`.
  - Recipient #1 and recipient #3 succeed normally and are marked `SUCCESS`.
  - The job transitions to `PARTIAL_FAILURE` (or `COMPLETED` if 0 errors, `FAILED` if all failed).
  - The bulk ZIP archive generator automatically skips failed records and bundles only valid deliverables.

### 3. Programmatic Canvas Design
- Instead of relying on static HTML-to-PDF rendering engines (like wkhtmltopdf or Puppeteer which require heavy browser runtimes), certificates are generated programmatically using Pillow.
- This results in zero external browser binaries, high generation speed (~20-50ms per certificate), and deterministic pixel-perfect output.

---

## Project Structure

```
Bulk_certificate_generator/
├── backend/
│   ├── main.py              # FastAPI application, background workers, endpoints, ZIP packaging
│   ├── models.py            # SQLAlchemy ORM models & Pydantic validation schemas
│   ├── utils.py             # PIL-based certificate rendering engine & ZIP helper
│   ├── test_main.py         # Pytest test suite covering all functional requirements
│   ├── requirements.txt     # Python backend dependencies
│   └── certificates/        # Storage directory for generated certificates & ZIP archives
├── frontend/                # React (Vite) frontend application
│   ├── package.json
│   ├── vite.config.js       # Vite dev proxy configuration
│   ├── index.html
│   └── src/
│       ├── main.jsx         # React application entrypoint
│       ├── App.jsx          # Dashboard, live polling, recipient editor, CSV upload, modal preview
│       ├── App.css          # Glassmorphic custom styling & animated progress bars
│       └── index.css        # Theme variables & typography
├── main.py                  # Root entrypoint forwarding to backend.main
├── models.py                # Root models forwarding module
├── utils.py                 # Root utils forwarding module
├── test_main.py             # Root test runner forwarding to backend test suite
├── pytest.ini               # Pytest configuration
├── requirements.txt         # Root requirements file
└── README.md                # Comprehensive documentation
```

---

## Installation & Setup

### Prerequisites
- **Python:** 3.10+
- **Node.js:** 18+ & **npm**

### 1. Install Backend Dependencies
From the repository root:
```bash
pip install -r requirements.txt
```

### 2. Install Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

---

## Running the Application

### Option A: Unified Full-Stack Run (Recommended)
Build the frontend once, then run FastAPI. FastAPI will serve both the REST API and the React web application on port 8000:

```bash
# 1. Build frontend production assets
cd frontend
npm run build
cd ..

# 2. Start FastAPI server
python -m uvicorn main:app --port 8000 --host 127.0.0.1 --reload
```
Open your browser at: **`http://127.0.0.1:8000`**

### Option B: Standalone Development Run
Run the backend and frontend development servers concurrently:

**Terminal 1 (Backend API):**
```bash
python -m uvicorn main:app --port 8000 --reload
```
API runs on `http://127.0.0.1:8000` with Swagger docs at `http://127.0.0.1:8000/docs`.

**Terminal 2 (Frontend Dev Server):**
```bash
cd frontend
npm run dev
```
Vite runs on `http://localhost:5173` with automatic API proxying to port 8000.

---

## Running the Test Suite

The test suite thoroughly covers all six core requirements outlined in the specification:
1. **Creating a generation job:** Submitting a bulk job with multiple recipients, receiving HTTP 202 Accepted.
2. **Input validation:** Rejecting invalid emails, empty recipient names, missing course titles, and empty arrays with HTTP 422.
3. **Certificate generation:** Verifying physical PNG creation on disk, image dimensions (1920×1280), and Pillow format integrity.
4. **Job status & progress tracking:** Polling `GET /api/jobs/{job_id}`, checking counts and percentage metrics.
5. **Individual certificate failure isolation:** Submitting a batch where one recipient triggers an error; confirming that sibling certificates succeed, the failing certificate records the error diagnostic, and job status reflects `PARTIAL_FAILURE`.
6. **Retrieving generated certificates:** Downloading individual PNGs, inline previewing, and unpacking bulk ZIP archives in-memory.
7. **CSV bulk ingestion:** Testing multi-row CSV upload endpoint.

To execute the test suite:
```bash
pytest
```
Or with verbose output:
```bash
pytest -v
```

---

## API Reference

Interactive OpenAPI documentation is available at **`http://127.0.0.1:8000/docs`**.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check endpoint returning backend status. |
| `POST` | `/api/jobs` | Enqueue a bulk certificate generation job. Returns HTTP 202 with job tracking ID. |
| `GET` | `/api/jobs` | List recent jobs with aggregate counts and statuses. |
| `GET` | `/api/jobs/{job_id}` | Retrieve real-time progress, counts, and recipient details for a job. |
| `GET` | `/api/jobs/{job_id}/certificates/{cert_id}/download` | Download an individual certificate PNG as an attachment. |
| `GET` | `/api/jobs/{job_id}/certificates/{cert_id}/preview` | Preview an individual certificate PNG inline. |
| `GET` | `/api/jobs/{job_id}/download-zip` | Download a packaged ZIP archive of all valid certificates in the job. |
| `POST` | `/api/jobs/upload-csv` | Upload a CSV file of recipients and immediately enqueue a bulk job. |
| `DELETE` | `/api/jobs/{job_id}` | Delete a job and purge its generated files from storage. |

### Sample Payload for `POST /api/jobs`
```json
{
  "title": "Cloud Native Architecture Cohort 2026",
  "recipients": [
    {
      "name": "Sarah Connor",
      "email": "sarah.connor@example.com",
      "course_name": "Cloud Native Architecture",
      "issue_date": "October 10, 2026"
    },
    {
      "name": "John Connor",
      "email": "john.connor@example.com",
      "course_name": "Cloud Native Architecture",
      "issue_date": "October 10, 2026"
    }
  ]
}
```

---

## Fault Tolerance & Error Isolation Demo

To test or demonstrate failure isolation without manual setup:

1. Open the web interface at `http://127.0.0.1:8000`.
2. Click the **"Simulate Fault Tolerance Test"** button above the recipient table.
3. This automatically populates 3 recipients where the middle recipient (`simulate.fail@demo.com`) is designated to trigger a rendering failure.
4. Click **"Generate 3 Certificates in Bulk"**.
5. Observe the live monitor:
   - The progress bar completes to 100%.
   - Status updates to **`PARTIAL_FAILURE`**.
   - Recipients #1 and #3 show green **SUCCESS** badges with Preview and Download links.
   - Recipient #2 shows a red **FAILED** badge with the isolated error message displayed inline.
   - The **"Bulk ZIP Archive Ready"** button is still active, allowing you to download the ZIP containing the 2 valid certificates.

