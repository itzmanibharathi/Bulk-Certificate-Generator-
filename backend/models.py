import os
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, validator
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# Database engine & session configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./certificates.db")
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ============================================================================
# SQLAlchemy ORM Models
# ============================================================================

class Job(Base):
    """
    Represents a bulk certificate generation job.
    Tracks overall progress, lifecycle states, and recipient counts.
    """
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, default="Bulk Certificate Generation", nullable=False)
    status = Column(String, default="PENDING", nullable=False, index=True)
    # Statuses: PENDING, PROCESSING, COMPLETED, PARTIAL_FAILURE, FAILED

    total_count = Column(Integer, default=0, nullable=False)
    processed_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    certificates = relationship(
        "CertificateRecord",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="CertificateRecord.created_at"
    )


class CertificateRecord(Base):
    """
    Represents an individual certificate generation record within a job.
    Isolates per-recipient status, file storage paths, and error details.
    """
    __tablename__ = "certificates"

    id = Column(String, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_name = Column(String, nullable=False)
    recipient_email = Column(String, nullable=False)
    course_name = Column(String, nullable=False)
    issue_date = Column(String, nullable=False)

    status = Column(String, default="PENDING", nullable=False, index=True)
    # Statuses: PENDING, SUCCESS, FAILED

    file_path = Column(String, nullable=True)
    file_name = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    job = relationship("Job", back_populates="certificates")


def init_db():
    """Create database tables if they do not already exist."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency generator for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# Pydantic Schemas for Request Validation & Responses
# ============================================================================

class RecipientInput(BaseModel):
    """
    Validation schema for an individual certificate recipient.
    Enforces non-empty strings and valid email format.
    """
    name: str = Field(..., min_length=2, max_length=120, description="Recipient full name")
    email: EmailStr = Field(..., description="Valid recipient email address")
    course_name: str = Field(..., min_length=2, max_length=150, description="Course or award title")
    issue_date: Optional[str] = Field(
        default=None,
        description="Date of completion/issue (e.g., 'YYYY-MM-DD' or 'October 10, 2026')"
    )

    @validator("name")
    def validate_name_not_blank(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Recipient name cannot be blank or whitespace only")
        return clean

    @validator("course_name")
    def validate_course_not_blank(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Course name cannot be blank or whitespace only")
        return clean

    @validator("issue_date", pre=True, always=True)
    def validate_or_default_date(cls, v: Optional[str]) -> str:
        if v is None or not str(v).strip():
            return datetime.utcnow().strftime("%B %d, %Y")
        return str(v).strip()


class BulkJobCreate(BaseModel):
    """
    Validation schema for bulk certificate generation requests.
    Enforces a non-empty recipient list.
    """
    title: Optional[str] = Field(
        default="Bulk Certificate Generation",
        max_length=200,
        description="Optional title or label for this batch job"
    )
    recipients: List[RecipientInput] = Field(
        ...,
        min_items=1,
        description="List of recipients to generate certificates for"
    )
    # Optional testing hook to explicitly simulate isolated failure on selected emails
    simulate_failure_emails: Optional[List[str]] = Field(
        default=None,
        description="List of recipient emails that should simulate rendering failures for fault tolerance testing"
    )


class CertificateRecordResponse(BaseModel):
    """Schema for individual certificate status and download links."""
    id: str
    job_id: str
    recipient_name: str
    recipient_email: str
    course_name: str
    issue_date: str
    status: str
    file_name: Optional[str] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True


class JobResponse(BaseModel):
    """Schema for complete bulk job status and tracking."""
    id: str
    title: str
    status: str
    total_count: int
    processed_count: int
    success_count: int
    failed_count: int
    progress_percentage: float
    created_at: datetime
    updated_at: datetime
    zip_download_url: Optional[str] = None
    certificates: List[CertificateRecordResponse] = []

    class Config:
        orm_mode = True


class JobListSummary(BaseModel):
    """Lightweight summary schema for listing jobs."""
    id: str
    title: str
    status: str
    total_count: int
    processed_count: int
    success_count: int
    failed_count: int
    progress_percentage: float
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

