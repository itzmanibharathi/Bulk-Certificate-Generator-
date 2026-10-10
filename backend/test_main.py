import os
import io
import zipfile
import pytest
from PIL import Image
from fastapi.testclient import TestClient

# Ensure test database is isolated
os.environ["DATABASE_URL"] = "sqlite:///./test_certificates.db"

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app, CERT_STORAGE_DIR
from models import init_db, engine, Base


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initializes a clean test database and tears it down after tests run."""
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    test_db_file = "test_certificates.db"
    if os.path.exists(test_db_file):
        try:
            os.remove(test_db_file)
        except Exception:
            pass


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


# ============================================================================
# 1. Test Creating a Generation Job
# ============================================================================

def test_create_generation_job(client):
    """
    Verifies that the API accepts a single request containing multiple recipients,
    persists the job, returns HTTP 202 Accepted, and generates certificate records.
    """
    payload = {
        "title": "Full-Stack Web Development Cohort 2026",
        "recipients": [
            {
                "name": "Sarah Connor",
                "email": "sarah.connor@example.com",
                "course_name": "Full-Stack Web Development",
                "issue_date": "October 10, 2026"
            },
            {
                "name": "John Connor",
                "email": "john.connor@example.com",
                "course_name": "Full-Stack Web Development",
                "issue_date": "October 10, 2026"
            }
        ]
    }

    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()

    assert "id" in data
    assert data["title"] == "Full-Stack Web Development Cohort 2026"
    assert data["total_count"] == 2
    assert len(data["certificates"]) == 2
    assert data["certificates"][0]["recipient_name"] == "Sarah Connor"
    assert data["certificates"][1]["recipient_name"] == "John Connor"


# ============================================================================
# 2. Test Input Validation
# ============================================================================

def test_input_validation_invalid_email(client):
    """Tests that malformed email addresses are rejected with HTTP 422."""
    payload = {
        "title": "Validation Test",
        "recipients": [
            {
                "name": "Invalid Email User",
                "email": "not-a-valid-email-string",
                "course_name": "Python Mastery"
            }
        ]
    }
    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 422
    errors = response.json().get("detail", [])
    assert any("email" in str(err).lower() for err in errors)


def test_input_validation_empty_name(client):
    """Tests that empty recipient names are rejected with HTTP 422."""
    payload = {
        "title": "Validation Test",
        "recipients": [
            {
                "name": "   ",
                "email": "test@example.com",
                "course_name": "Python Mastery"
            }
        ]
    }
    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 422


def test_input_validation_empty_recipients_list(client):
    """Tests that an empty recipients array is rejected with HTTP 422."""
    payload = {
        "title": "Empty Recipients Test",
        "recipients": []
    }
    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 422


def test_input_validation_missing_course(client):
    """Tests that missing course name is rejected with HTTP 422."""
    payload = {
        "title": "Missing Course Test",
        "recipients": [
            {
                "name": "Jane Doe",
                "email": "jane@example.com"
            }
        ]
    }
    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 422


# ============================================================================
# 3. Test Certificate Generation (Image File Integrity)
# ============================================================================

def test_certificate_generation_file_creation(client):
    """
    Verifies that the certificate generator renders a valid high-resolution PNG image
    file on disk with expected dimensions and integrity.
    """
    payload = {
        "title": "Image Rendering Test",
        "recipients": [
            {
                "name": "Ada Lovelace",
                "email": "ada.lovelace@example.com",
                "course_name": "Algorithmic Computing Foundations",
                "issue_date": "October 10, 2026"
            }
        ]
    }

    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 202
    job_data = response.json()
    job_id = job_data["id"]

    # In TestClient, BackgroundTasks run synchronously before response returns
    status_resp = client.get(f"/api/jobs/{job_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()

    assert status_data["status"] == "COMPLETED"
    cert = status_data["certificates"][0]
    assert cert["status"] == "SUCCESS"
    assert cert["file_name"] is not None

    # Verify physical file existence
    file_path = os.path.join(CERT_STORAGE_DIR, job_id, cert["file_name"])
    assert os.path.exists(file_path), f"File {file_path} was not created on disk."

    # Verify valid image using Pillow
    with Image.open(file_path) as img:
        assert img.format == "PNG"
        assert img.size == (1920, 1280)
        assert img.mode == "RGB"


# ============================================================================
# 4. Test Job Status and Progress Tracking
# ============================================================================

def test_job_status_and_progress_tracking(client):
    """
    Verifies that job status can be tracked via GET /api/jobs/{job_id},
    confirming accurate counts, 100% progress percentage, and listing in historical jobs.
    """
    payload = {
        "title": "Progress Tracking Batch",
        "recipients": [
            {"name": "Dev One", "email": "dev1@example.com", "course_name": "Cloud Native"},
            {"name": "Dev Two", "email": "dev2@example.com", "course_name": "Cloud Native"},
            {"name": "Dev Three", "email": "dev3@example.com", "course_name": "Cloud Native"}
        ]
    }

    create_resp = client.post("/api/jobs", json=payload)
    assert create_resp.status_code == 202
    job_id = create_resp.json()["id"]

    # Poll status endpoint
    get_resp = client.get(f"/api/jobs/{job_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()

    assert data["id"] == job_id
    assert data["total_count"] == 3
    assert data["processed_count"] == 3
    assert data["success_count"] == 3
    assert data["failed_count"] == 0
    assert data["progress_percentage"] == 100.0
    assert data["status"] == "COMPLETED"

    # Verify listing in GET /api/jobs
    list_resp = client.get("/api/jobs")
    assert list_resp.status_code == 200
    jobs_list = list_resp.json()
    assert any(j["id"] == job_id for j in jobs_list)


# ============================================================================
# 5. Test Individual Certificate Failure Isolation (Fault Tolerance)
# ============================================================================

def test_individual_certificate_failure_isolation(client):
    """
    Critical requirement: A failure while generating one certificate must NOT
    prevent other valid certificates in the same job from being generated.
    The job status must clearly identify successful and failed generations with error messages.
    """
    payload = {
        "title": "Fault Tolerance Isolation Test",
        "recipients": [
            {"name": "Grace Hopper", "email": "grace.hopper@example.com", "course_name": "Compiler Design"},
            {"name": "Failing Recipient", "email": "simulate.fail@example.com", "course_name": "Compiler Design"},
            {"name": "Alan Turing", "email": "alan.turing@example.com", "course_name": "Compiler Design"}
        ],
        "simulate_failure_emails": ["simulate.fail@example.com"]
    }

    create_resp = client.post("/api/jobs", json=payload)
    assert create_resp.status_code == 202
    job_id = create_resp.json()["id"]

    # Retrieve updated job status
    status_resp = client.get(f"/api/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()

    # Job lifecycle must reflect partial failure
    assert data["status"] == "PARTIAL_FAILURE"
    assert data["total_count"] == 3
    assert data["processed_count"] == 3
    assert data["success_count"] == 2
    assert data["failed_count"] == 1
    assert data["progress_percentage"] == 100.0

    certs = {c["recipient_email"]: c for c in data["certificates"]}

    # Grace Hopper must have SUCCEEDED
    assert certs["grace.hopper@example.com"]["status"] == "SUCCESS"
    assert certs["grace.hopper@example.com"]["file_name"] is not None
    assert certs["grace.hopper@example.com"]["download_url"] is not None

    # Failing Recipient must have FAILED with isolated error message
    assert certs["simulate.fail@example.com"]["status"] == "FAILED"
    assert certs["simulate.fail@example.com"]["error_message"] is not None
    assert "Simulated processing error" in certs["simulate.fail@example.com"]["error_message"]
    assert certs["simulate.fail@example.com"]["download_url"] is None

    # Alan Turing must have SUCCEEDED (proving isolation did not interrupt subsequent items)
    assert certs["alan.turing@example.com"]["status"] == "SUCCESS"
    assert certs["alan.turing@example.com"]["file_name"] is not None
    assert certs["alan.turing@example.com"]["download_url"] is not None


# ============================================================================
# 6. Test Retrieving Generated Certificates (Single PNG & Bulk ZIP)
# ============================================================================

def test_retrieving_generated_certificates(client):
    """
    Tests downloading individual certificates, previewing inline,
    and downloading a packaged ZIP archive of all valid certificates in the job.
    """
    payload = {
        "title": "Retrieval Test Batch",
        "recipients": [
            {"name": "Katherine Johnson", "email": "katherine@example.com", "course_name": "Orbital Mechanics"},
            {"name": "Margaret Hamilton", "email": "margaret@example.com", "course_name": "Apollo Systems"}
        ]
    }

    create_resp = client.post("/api/jobs", json=payload)
    assert create_resp.status_code == 202
    job_id = create_resp.json()["id"]

    job_data = client.get(f"/api/jobs/{job_id}").json()
    cert1 = job_data["certificates"][0]
    cert2 = job_data["certificates"][1]

    # 1. Download Individual Certificate
    dl_resp = client.get(f"/api/jobs/{job_id}/certificates/{cert1['id']}/download")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "image/png"
    assert len(dl_resp.content) > 1000  # Valid non-empty binary

    # 2. Preview Individual Certificate Inline
    prev_resp = client.get(f"/api/jobs/{job_id}/certificates/{cert1['id']}/preview")
    assert prev_resp.status_code == 200
    assert prev_resp.headers["content-type"] == "image/png"
    assert "inline" in prev_resp.headers.get("content-disposition", "")

    # 3. Download Bulk ZIP Archive
    zip_resp = client.get(f"/api/jobs/{job_id}/download-zip")
    assert zip_resp.status_code == 200
    assert zip_resp.headers["content-type"] == "application/zip"
    assert "attachment;" in zip_resp.headers.get("content-disposition", "")

    # 4. Verify ZIP content integrity in-memory
    zip_buffer = io.BytesIO(zip_resp.content)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) == 2
        assert any("Katherine_Johnson" in name for name in namelist)
        assert any("Margaret_Hamilton" in name for name in namelist)


def test_download_failed_certificate_returns_400(client):
    """Tests that attempting to download a failed certificate returns HTTP 400."""
    payload = {
        "title": "Failed Download Test",
        "recipients": [
            {"name": "Failing User", "email": "fail.dl@example.com", "course_name": "Testing"}
        ],
        "simulate_failure_emails": ["fail.dl@example.com"]
    }
    create_resp = client.post("/api/jobs", json=payload)
    job_id = create_resp.json()["id"]

    job_data = client.get(f"/api/jobs/{job_id}").json()
    failed_cert_id = job_data["certificates"][0]["id"]

    dl_resp = client.get(f"/api/jobs/{job_id}/certificates/{failed_cert_id}/download")
    assert dl_resp.status_code == 400
    assert "not available" in dl_resp.json()["detail"].lower()


# ============================================================================
# 7. Test CSV Upload Endpoint
# ============================================================================

def test_csv_upload_bulk_job(client):
    """Tests uploading a CSV file of recipients and triggering bulk generation."""
    csv_content = (
        "name,email,course_name,issue_date\n"
        "Linus Torvalds,linus@example.com,Kernel Architecture,October 10, 2026\n"
        "Ken Thompson,ken@example.com,Unix Fundamentals,October 10, 2026\n"
    )

    response = client.post(
        "/api/jobs/upload-csv",
        files={"file": ("recipients.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        data={"title": "CSV Enrolled Cohort"}
    )
    assert response.status_code == 202
    data = response.json()
    assert data["title"] == "CSV Enrolled Cohort"
    assert data["total_count"] == 2

    job_id = data["id"]
    job_resp = client.get(f"/api/jobs/{job_id}")
    assert job_resp.status_code == 200
    assert job_resp.json()["status"] == "COMPLETED"
