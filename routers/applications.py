import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import AsyncSessionLocal
from dependencies import get_db, get_current_user, require_role
from models import LoanApplication, ApplicationStatus
from schemas.application import LoanApplicationCreate, LoanApplicationSummary, LoanApplicationResponse, LoanStatusUpdate, PaginatedApplications
from services.credit_bureau import CreditBureauClient
from services.eligibility import EligibilityService
from services.scoring import ScoringEngine
from services.audit import AuditLogger

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Submit a new application -------------------------------------------

@router.post(
    "/",
    response_model=LoanApplicationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a loan application",
    description="Creates a loan application record and immediately returns 202. The credit checck runs asynchronously in the background -- the client should poll GET /{id} to check the final decision."
)
async def create_application(
    payload: LoanApplicationCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # 1. Duplicate PAN check -- one active application per PAN at a time
    existing = await db.execute(
        select(LoanApplication).where(
            LoanApplication.pan_number == payload.pan_number,
            LoanApplication.status.not_in([
                ApplicationStatus.REJECTED,
                ApplicationStatus.DISBURSED,
                ApplicationStatus.CANCELLED,
            ]),
        )
    )

    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"An active application already exists for PAN ***{payload.pan_number[-4:]}."
                "Please wait for the existing application to be processed."
            ),
        )

    # 2. Eligibility check -- business rules from DB
    eligibility = EligibilityService(db)
    is_eligible, reason = await eligibility.check(payload)
    if not is_eligible:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "eligibility_failed", "reason": reason},
        )

    # 3. Persist application -- status starts as CREDIT_CHECK_PENDING
    application = LoanApplication(
        **payload.model_dump(),
        status=ApplicationStatus.CREDIT_CHECK_PENDING,
        submitted_by=current_user["user_id"],
    )
    db.add(application)
    await db.flush()  # getting the UUID without committing yet
    await db.refresh(application)

    # 4. Initial audit log entry
    auditor = AuditLogger(db)
    await auditor.log(
        application_id=application.id,
        action="application_submitted",
        performed_by=current_user["user_id"],
        new_status=ApplicationStatus.CREDIT_CHECK_PENDING.value,
        notes="Application submitted and passed eligibility checks",
    )

    # 5. Schedule async credit check -- runs AFTER 202 is sent to client
    background_tasks.add_task(
        _run_credit_check,
        application_id=application.id,
        pan_number=application.pan_number,
        date_of_birth=str(application.date_of_birth),
        monthly_income=float(application.monthly_income),
        requested_amount=float(application.requested_amount),
        employment_type=application.employment_type,
        submitted_by=current_user["user_id"],
    )

    logger.info(
        f"Application {application.id} submitted by {current_user['user_id']}."
        f"Credit check queued."
    )
    return application

# --- List applications (paginated) -----------------------------------------------

@router.get(
    "/",
    response_model=PaginatedApplications,
    summary="List applications -- ops/admin only",
)
async def list_applications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[ApplicationStatus] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin", "ops")),
):
    base_query = select(LoanApplication)
    if status_filter:
        base_query = base_query.where(LoanApplication.status == status_filter)

    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar()

    result = await db.execute(
        base_query.order_by(LoanApplication.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    applications = result.scalars().all()

    return PaginatedApplications(
        total=total,
        page=page,
        page_size=page_size,
        items=[LoanApplicationSummary.model_validate(a) for a in applications],
    )


# --- Get single applications ---------------------------------------------

@router.get(
    "/{application_id}",
    response_model=LoanApplicationResponse,
    summary="Get full application details",
)
async def get_application(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(LoanApplication).where(LoanApplication.id == application_id)
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found.",
        )
    return application


# --- Manual status update (ops/admin)---------------------------------------

@router.patch(
    "/{application_id}/status",
    response_model=LoanApplicationResponse,
    summary="Manually update application status -- ops/admin only",
)
async def update_status(
    application_id: UUID,
    payload: LoanStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin", "ops")),
):
    result = await db.execute(
        select(LoanApplication).where(LoanApplication.id == application_id)
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found.")

    old_status = application.status.value

    application.status = payload.status
    if payload.rejection_reason:
        application.rejection_reason = payload.rejection_reason
    if payload.approved_amount is not None:
        application.approved_amount = payload.approved_amount

    auditor = AuditLogger(db)
    await auditor.log(
        application_id=application_id,
        action="manual_status_override",
        performed_by=current_user["user_id"],
        old_status=old_status,
        new_status=payload.status.value,
        notes=payload.notes or "Manual override by ops team",
    )

    await db.flush()
    await db.refresh(application)
    return application


# --- Background credit check task ------------------------------------
async def _run_credit_check(
    application_id: UUID,
    pan_number: str,
    date_of_birth: str,
    monthly_income: float,
    requested_amount: float,
    employment_type: str,
    submitted_by: str,
):
    """
    Runs after the 202 response is sent. Uses its own DB session -- cannot reuse the request session, which is already closed by the time this function executes.

    Steps:
        1. Call credit bureau API (with retry)
        2. Run scoring engine
        3. Update application status in DB
        4. Write audit log
        5. (Optional) publish SQS event for downstream consumers
    """
    logger.info(f"Background credit check started for {application_id}")

    async with AsyncSessionLocal() as db:
        try:
            # Fetching application
            result = await db.execute(
                select(LoanApplication).where(LoanApplication.id == application_id)
            )
            application = result.scalar_one_or_none()
            if not application:
                logger.error(f"Application {application_id} not found in background task")
                return

            old_status = application.status.value

            # Step 1: Credit Bureau call
            bureau = CreditBureauClient()
            try:
                bureau_score = await bureau.fetch_score(pan_number, date_of_birth)
            except Exception as exc:
                logger.error(f"Bureau call failed for {application_id}: {exc}")
                application.status = ApplicationStatus.UNDER_REVIEW
                application.rejection_reason = "Credit bureau unavailable -- manual review required"
                auditor = AuditLogger(db)
                await auditor.log(
                    application_id=application_id,
                    action="bureau_call_failed",
                    performed_by="system",
                    old_status=old_status,
                    new_status=ApplicationStatus.UNDER_REVIEW.value,
                    notes=str(exc),
                )
                await db.commit()
                return

            # Step 2: Scoring Engineer
            engine = ScoringEngine()
            result_data = engine.calculate(
                bureau_score=bureau_score,
                monthly_income=monthly_income,
                requested_amount=requested_amount,
                employment_type=employment_type,
            )

            # Step 3: Map decision to status
            decision = result_data["decision"]
            if decision == "approved":
                new_status = ApplicationStatus.APPROVED
            elif decision == "under_review":
                new_status = ApplicationStatus.UNDER_REVIEW
            else:
                new_status = ApplicationStatus.REJECTED

            application.status = new_status
            application.credit_score = result_data["final_score"]
            application.approved_amount = result_data["approved_amount"]
            application.interest_rate = result_data["interest_rate"]
            application.loan_tenure_months = result_data["tenure_months"]
            if new_status == ApplicationStatus.REJECTED:
                application.rejection_reason = (
                    f"Credit score {result_data['final_score']} is below the minimum threshold of 600."
                )

            # Step 4: Audit Log
            auditor = AuditLogger(db)
            await auditor.log(
                application_id=application_id,
                action="credit_check_completed",
                performed_by="system",
                old_status=old_status,
                new_status=new_status,
                notes=(
                    f"Bureau score: {bureau_score} | Final score: {result_data['final_score']} | Decision: {decision}"
                ),
            )

            await db.commit()
            logger.info(
                f"Credit check done: application={application_id} score={result_data['final_score']} decision={decision}"
            )

            # Step 5: Publish SQS event (optional)
            from config import settings
            if settings.USE_AWS_SQS:
                await _publish_sqs_event(
                    application_id=str(application_id),
                    new_status=new_status.value,
                    credit_score=result_data["final_score"],
                )

        except Exception as exc:
            await db.rollback()
            logger.error(
                f"Background credit check failed for {application_id}: {exc}",
                exc_info=True,
            )


async def _publish_sqs_event(application_id: str, new_status: str, credit_score: int):
    """Publishes a status change event to AWS SQS for downstream consumers."""
    import boto3, json
    from datetime import datetime
    from config import settings

    try:
        sqs = boto3.client(
            "sqs",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        sqs.send_message(
            QueueUrl=settings.SQS_QUEUE_URL,
            MessageBody=json.dumps({
                "event_type": "loan_status_changed",
                "application_id": application_id,
                "new_status": new_status,
                "credit_score": credit_score,
                "timestamp": datetime.utcnow().isoformat(),
            }),
        )
        logger.info(f"SQS event published for {application_id}: {new_status}")
    except Exception as exc:
        # SQS failure must never break the main flow
        logger.error(f"SQS publish failed for {application_id}: {exc}")

