import re, datetime
from decimal import Decimal
from typing import Optional, List, Any
from typing_extensions import Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, EmailStr, model_validator

from models import ApplicationStatus, EmploymentType, LoanPurpose


# --- Request Schemas -----------------------------------

class LoanApplicationCreate(BaseModel):
    applicant_name: str = Field(..., min_length=2, max_length=200)
    applicant_email: EmailStr
    mobile_number: str = Field(..., pattern=r"^[6-9]\d{9}$")
    pan_number: str = Field(..., min_length=10, max_length=10)
    date_of_birth: datetime.date
    requested_amount: Decimal = Field(..., ge=10000, le=5000000, description="Amount in INR")
    loan_purpose: LoanPurpose
    monthly_income: Decimal = Field(..., ge=5000)
    employment_type: EmploymentType
    employer_name: Optional[str] = Field(None, max_length=200)

    @field_validator("pan_number")
    @classmethod
    def validate_pan(cls, v: str) -> str:
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", v.upper()):
            raise ValueError("Invalid PAN format. Expected format: ABCDE1234F")
        return v.upper()

    @field_validator("applicant_name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z\s]+$", v):
            raise ValueError("Name must contain only letters and spaces")
        return v.strip().title()

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: datetime.date) -> datetime.date:
        today = datetime.date.today()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        if age < 18:
            raise ValueError("Applicant must be at least 18 years old")
        if age > 70:
            raise ValueError("Applicant must be under 70 years old")
        return v

    @model_validator(mode="after")
    def employer_required_for_salaried(self) -> "LoanApplicationCreate":
        if self.employment_type == EmploymentType.SALARIED and not self.employer_name:
            raise ValueError("employer_name is required for salaried applicants")
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "applicant_name": "Rahul Sharma",
                "applicant_email": "rahul.sharma@example.com",
                "mobile_number": "9876543210",
                "pan_number": "ABCDE1234F",
                "date_of_birth": "1990-06-15",
                "requested_amount": 5000000,
                "loan_purpose": "home_renovation",
                "monthly_income": 75000,
                "employment_type": "salaried",
                "employer_name": "Infosys Ltd"
            }
        }
    }


class LoanStatusUpdate(BaseModel):
    status: ApplicationStatus
    rejection_reason: Optional[str] = Field(None, max_length=500)
    approved_amount: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=1000)


# --- Response Schemas ---------------------------------------

class AuditLogResponse(BaseModel):
    id: UUID
    action: str
    old_status: Optional[str]
    new_status: Optional[str]
    performed_by: str
    notes: Optional[str]
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class LoanApplicationResponse(BaseModel):
    id: UUID
    applicant_name: str
    applicant_email: str
    mobile_number: str
    pan_number: str
    date_of_birth: datetime.date
    requested_amount: Decimal
    loan_purpose: LoanPurpose
    monthly_income: Decimal
    employment_type: EmploymentType
    employer_name: Optional[str]
    status: ApplicationStatus
    credit_score: Optional[int]
    approved_amount: Optional[Decimal]
    interest_rate: Optional[Decimal]
    loan_tenure_months: Optional[int]
    rejection_reason: Optional[str]
    submitted_by: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    audit_logs: List[AuditLogResponse] = []

    model_config = {"from_attributes": True}


class LoanApplicationSummary(BaseModel):
    """
    Lightweight response for paginated list -- excludes the audit logs.
    """
    id: UUID
    applicant_name: str
    pan_number: str
    requested_amount: Decimal
    status: ApplicationStatus
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class PaginatedApplications(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[LoanApplicationSummary]


