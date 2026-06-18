import uuid, enum, datetime
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import (
    String, Numeric, Integer, DateTime, Date, Text, ForeignKey, Enum as SAEnum, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# --- Enums ------------------------------------------

class ApplicationStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    ELIGIBILITY_FAILED = "eligibility_failed"
    CREDIT_CHECK_PENDING = "credit_check_pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISBURSED = "disbursed"
    CANCELLED = "cancelled"


class EmploymentType(str, enum.Enum):
    SALARIED = "salaried"
    SELF_EMPLOYED = "self_employed"


class LoanPurpose(str, enum.Enum):
    HOME_RENOVATION = "home_renovation"
    EDUCATION = "education"
    MEDICAL = "medical"
    VEHICLE = "vehicle"
    WEDDING = "wedding"
    BUSINESS = "business"
    PERSONAL = "personal"


# --- Main Application table -------------------------------------

class LoanApplication(Base):
    __tablename__ = "loan_applications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Application identity
    applicant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    applicant_email: Mapped[str] = mapped_column(String(200), nullable=False)
    mobile_number: Mapped[str] = mapped_column(String(15), nullable=False)
    pan_number: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    date_of_birth: Mapped[datetime.date] = mapped_column(Date, nullable=False)

    # Loan parameters
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    loan_purpose: Mapped[str] = mapped_column(SAEnum(LoanPurpose), nullable=False)
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    employment_type: Mapped[str] = mapped_column(SAEnum(EmploymentType), nullable=False)
    employer_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Decision Fields -- populated by the async credit check
    status: Mapped[str] = mapped_column(
        SAEnum(ApplicationStatus), default=ApplicationStatus.SUBMITTED,
        nullable=False,
        index=True,
    )

    credit_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approved_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    interest_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    loan_tenure_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit metadata
    submitted_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="application", lazy="selectin")

    __table_args__ = (
        Index("ix_loan_app_pan_status", "pan_number", "status"),
    )

# --- Configurable Eligibility Rules ------------------------------


class EligibilityConfig(Base):
    """
    Database-backed business rules. The ops/business team edits rows here -- so no code deployment needed to change the income thresholds, age limits, or loan-to-income ratios.
    """
    __tablename__ = "eligibility_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    rule_value: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )


# --- Immutable audit trail -----------------------------------

class AuditLog(Base):
    """
    Every status change, bureau call, and manual override is recorded here. Required for RBI compliance -- this table is append-only, never updated.
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    old_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    performed_by: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    application: Mapped["LoanApplication"] = relationship("LoanApplication", back_populates="audit_logs")


