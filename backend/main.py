import os
import sys
import re
import uuid
import csv
import io
import shutil
from datetime import datetime
from typing import List, Optional

# Ensure current directory is in sys.path for relative imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from models import (
    init_db,
    get_db,
    SessionLocal,
    Job,
    CertificateRecord,
    RecipientInput,
    BulkJobCreate,
    JobResponse,
    CertificateRecordResponse,
    JobListSummary
)
from utils import generate_certificate, create_job_zip

# Base storage directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_STORAGE_DIR = os.path.join(BASE_DIR, "certificates")
os.makedirs(CERT_STORAGE_DIR, exist_ok=True)

# Initialize FastAPI application
app = FastAPI(
    title="Bulk Certificate Generator API",
    description=(
        "Production-ready backend API for asynchronous bulk certificate generation, "
        "real-time status polling, individual failure isolation, and single/ZIP downloads."
    ),
    version="1.0.0"
)

# Enable CORS for local React/Vite development and multi-origin frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    """Ensure database schema is provisioned on application start."""
    init_db()


# ============================================================================
# Asynchronous Background Processing Worker
# ============================================================================
# DESIGN REASONING:
# Bulk certificate generation involves heavy image rendering (high-res Pillow 
# drawing, geometric matrices, QR code encoding, PNG compression).
# Running this synchronously in the HTTP request thread would block the HTTP 
# client, leading to request timeouts under bulk loads (e.g., 50-500 recipients).
#
# By leveraging FastAPI's `BackgroundTasks`, the HTTP request returns an immediate
# HTTP 202 Accepted with a unique Job ID. The background task executes out-of-band,
# updating the database incrementally after each recipient is drawn.
# This enables:
# 1. Non-blocking HTTP responsiveness.
# 2. Live progress polling from web clients (smooth progress bar animations).
# 3. Complete failure isolation: a failure on recipient #4 does not stop recipient #5.
# ============================================================================

def process_bulk_job(job_id: str, simulate_failure_emails: Optional[List[str]] = None):
    """
    Background worker loop that processes each recipient sequentially within a job,
    updating progress in the database and isolating failures per recipient.
    """
    db: Session = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return

        job.status = "PROCESSING"
        job.updated_at = datetime.utcnow()
        db.commit()

        records = db.query(CertificateRecord).filter(CertificateRecord.job_id == job_id).all()
        sim_failures = set(e.strip().lower() for e in (simulate_failure_emails or []))

        job_dir = os.path.join(CERT_STORAGE_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)

        for record in records:
            try:
                # Sanitize recipient name for filename
                clean_name = re.sub(r'[^a-zA-Z0-9_\- ]', '', record.recipient_name).strip().replace(' ', '_')
                file_name = f"{clean_name}_{record.id}.png"
                file_path = os.path.join(job_dir, file_name)

                # Check if this recipient was targeted for simulated failure (fault tolerance test)
                simulate_this = record.recipient_email.strip().lower() in sim_failures

                # Draw certificate
                generate_certificate(
                    cert_id=record.id,
                    recipient_name=record.recipient_name,
                    course_name=record.course_name,
                    issue_date=record.issue_date,
                    output_path=file_path,
                    simulate_failure=simulate_this
                )

                # Record success
                record.status = "SUCCESS"
                record.file_path = file_path
                record.file_name = file_name
                record.error_message = None
                job.success_count += 1

            except Exception as exc:
                # FAULT TOLERANCE ISOLATION:
                # An exception during one certificate's generation MUST NOT
                # crash the worker or stop sibling certificates from completing.
                record.status = "FAILED"
                record.error_message = str(exc)
                record.file_path = None
                record.file_name = None
                job.failed_count += 1

            # Increment processed count and persist step progress to database
            job.processed_count += 1
            job.updated_at = datetime.utcnow()
            db.commit()

        # Update final aggregate job lifecycle state
        if job.failed_count == 0:
            job.status = "COMPLETED"
        elif job.success_count > 0:
            job.status = "PARTIAL_FAILURE"
        else:
            job.status = "FAILED"

        job.updated_at = datetime.utcnow()
        db.commit()

    except Exception as fatal_exc:
        # Catch unexpected infrastructure issues (e.g. database disconnect)
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "FAILED"
                job.updated_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _format_job_response(job: Job) -> JobResponse:
    """Helper to convert a Job ORM entity into JobResponse with computed links."""
    pct = 0.0
    if job.total_count > 0:
        pct = round((job.processed_count / job.total_count) * 100.0, 1)

    has_successes = any(c.status == "SUCCESS" for c in job.certificates)
    zip_url = f"/api/jobs/{job.id}/download-zip" if has_successes else None

    cert_responses = []
    for c in job.certificates:
        cert_responses.append(CertificateRecordResponse(
            id=c.id,
            job_id=c.job_id,
            recipient_name=c.recipient_name,
            recipient_email=c.recipient_email,
            course_name=c.course_name,
            issue_date=c.issue_date,
            status=c.status,
            file_name=c.file_name,
            download_url=f"/api/jobs/{job.id}/certificates/{c.id}/download" if c.status == "SUCCESS" else None,
            preview_url=f"/api/jobs/{job.id}/certificates/{c.id}/preview" if c.status == "SUCCESS" else None,
            error_message=c.error_message,
            created_at=c.created_at
        ))

    return JobResponse(
        id=job.id,
        title=job.title,
        status=job.status,
        total_count=job.total_count,
        processed_count=job.processed_count,
        success_count=job.success_count,
        failed_count=job.failed_count,
        progress_percentage=pct,
        created_at=job.created_at,
        updated_at=job.updated_at,
        zip_download_url=zip_url,
        certificates=cert_responses
    )


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/health")
def health_check():
    """Health check endpoint to verify backend status."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_bulk_job(
    job_in: BulkJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Submits a bulk certificate generation job.
    Accepts a single payload containing multiple recipients.
    Validates data strictly, persists initial records, and triggers background processing.
    """
    if not job_in.recipients:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The recipients list must contain at least one recipient."
        )

    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        title=job_in.title or "Bulk Certificate Generation",
        status="PENDING",
        total_count=len(job_in.recipients),
        processed_count=0,
        success_count=0,
        failed_count=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(job)

    # Pre-populate certificate records in PENDING status
    for idx, r in enumerate(job_in.recipients, start=1):
        cert_id = f"CERT-{job_id[:8].upper()}-{idx:04d}"
        cert_rec = CertificateRecord(
            id=cert_id,
            job_id=job_id,
            recipient_name=r.name,
            recipient_email=r.email,
            course_name=r.course_name,
            issue_date=r.issue_date,
            status="PENDING",
            created_at=datetime.utcnow()
        )
        db.add(cert_rec)

    db.commit()
    db.refresh(job)

    # Dispatch asynchronous execution via BackgroundTasks
    background_tasks.add_task(
        process_bulk_job,
        job_id=job_id,
        simulate_failure_emails=job_in.simulate_failure_emails
    )

    return _format_job_response(job)


@app.get("/api/jobs", response_model=List[JobListSummary])
def list_jobs(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    """Lists historical jobs with summary statistics ordered by newest first."""
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(limit).all()
    summaries = []
    for j in jobs:
        pct = 0.0
        if j.total_count > 0:
            pct = round((j.processed_count / j.total_count) * 100.0, 1)
        summaries.append(JobListSummary(
            id=j.id,
            title=j.title,
            status=j.status,
            total_count=j.total_count,
            processed_count=j.processed_count,
            success_count=j.success_count,
            failed_count=j.failed_count,
            progress_percentage=pct,
            created_at=j.created_at,
            updated_at=j.updated_at
        ))
    return summaries


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """
    Returns full details for a bulk job including real-time progress,
    aggregate metrics, and individual certificate statuses with any error messages.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' was not found."
        )
    return _format_job_response(job)


@app.get("/api/jobs/{job_id}/certificates/{cert_id}/download")
def download_certificate(job_id: str, cert_id: str, db: Session = Depends(get_db)):
    """Downloads an individual successfully generated certificate as a PNG file."""
    record = db.query(CertificateRecord).filter(
        CertificateRecord.job_id == job_id,
        CertificateRecord.id == cert_id
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{cert_id}' for Job '{job_id}' not found."
        )

    if record.status != "SUCCESS" or not record.file_path or not os.path.exists(record.file_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Certificate is not available for download. Current status: {record.status}. Reason: {record.error_message or 'File not generated'}"
        )

    return FileResponse(
        path=record.file_path,
        media_type="image/png",
        filename=record.file_name or f"{cert_id}.png",
        headers={"Content-Disposition": f'attachment; filename="{record.file_name or cert_id + ".png"}"'}
    )


@app.get("/api/jobs/{job_id}/certificates/{cert_id}/preview")
def preview_certificate(job_id: str, cert_id: str, db: Session = Depends(get_db)):
    """Previews an individual certificate inline in the browser."""
    record = db.query(CertificateRecord).filter(
        CertificateRecord.job_id == job_id,
        CertificateRecord.id == cert_id
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{cert_id}' not found."
        )

    if record.status != "SUCCESS" or not record.file_path or not os.path.exists(record.file_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Certificate is not rendered yet. Status: {record.status}"
        )

    return FileResponse(
        path=record.file_path,
        media_type="image/png",
        headers={"Content-Disposition": "inline"}
    )


@app.get("/api/jobs/{job_id}/download-zip")
def download_job_zip(job_id: str, db: Session = Depends(get_db)):
    """
    Packages all successfully generated certificates for a job into a single ZIP archive.
    Ignores failed certificates and provides an archive of all valid deliverables.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found."
        )

    successful_records = [
        r for r in job.certificates
        if r.status == "SUCCESS" and r.file_path and os.path.exists(r.file_path)
    ]

    if not successful_records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No successfully generated certificates are available to download in this job."
        )

    zip_filename = f"certificates_{job.id[:8]}.zip"
    zip_path = os.path.join(CERT_STORAGE_DIR, job.id, zip_filename)

    file_mappings = [(r.file_path, r.file_name or f"{r.id}.png") for r in successful_records]
    create_job_zip(job.id, file_mappings, zip_path)

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=zip_filename,
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
    )


@app.post("/api/jobs/upload-csv", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_csv_and_create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form("CSV Bulk Certificate Generation"),
    db: Session = Depends(get_db)
):
    """
    Uploads a CSV file of recipients, parses and validates each row,
    and enqueues the bulk certificate generation job.
    Expected CSV columns: `name`, `email`, `course_name`, `issue_date` (optional).
    """
    if not file.filename.endswith(('.csv', '.txt')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a .csv file."
        )

    contents = await file.read()
    decoded = contents.decode("utf-8-sig")  # handle UTF-8 with BOM
    reader = csv.DictReader(io.StringIO(decoded))

    recipients: List[RecipientInput] = []
    errors: List[str] = []

    for row_idx, row in enumerate(reader, start=2):  # 1 is header
        # Normalize column keys to lowercase stripped
        normalized_row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
        
        name = normalized_row.get("name") or normalized_row.get("recipient_name") or ""
        email = normalized_row.get("email") or normalized_row.get("recipient_email") or ""
        course = normalized_row.get("course_name") or normalized_row.get("course") or ""
        issue_date = normalized_row.get("issue_date") or normalized_row.get("date") or None

        try:
            recipient = RecipientInput(
                name=name,
                email=email,
                course_name=course,
                issue_date=issue_date
            )
            recipients.append(recipient)
        except Exception as e:
            errors.append(f"Row {row_idx}: {str(e)}")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "CSV validation failed", "errors": errors}
        )

    if not recipients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file contains no recipient records."
        )

    # Create job payload
    job_payload = BulkJobCreate(
        title=title or "CSV Bulk Certificate Generation",
        recipients=recipients
    )

    return create_bulk_job(job_payload, background_tasks, db)


@app.delete("/api/jobs/{job_id}", status_code=status.HTTP_200_OK)
def delete_job(job_id: str, db: Session = Depends(get_db)):
    """Deletes a job record and all its associated generated files on disk."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found."
        )

    # Remove files on disk
    job_dir = os.path.join(CERT_STORAGE_DIR, job_id)
    if os.path.exists(job_dir):
        shutil.rmtree(job_dir, ignore_errors=True)

    db.delete(job)
    db.commit()

    return {"message": f"Job {job_id} and all related files deleted successfully."}


# Mount built React frontend if dist directory exists
FRONTEND_DIST_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")
if os.path.exists(FRONTEND_DIST_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")

