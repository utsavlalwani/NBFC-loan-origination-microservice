import logging
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from models import AuditLog

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Records every state change and key action to the audit_logs table. This is append-only -- rows are never updated or deleted.
    Required for RBI Digital Lending Compliance, which mandates a complete Audit Trail of every decision made on a loan application.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(self, application_id: UUID, action: str, performed_by: str, old_status: str = None, new_status: str = None, notes: str = None):
        entry = AuditLog(
            application_id=application_id,
            action=action,
            old_status=old_status,
            new_status=new_status,
            performed_by=performed_by,
            notes=notes,
        )
        self.db.add(entry)
        # Note: caller is responsible for committing the session.
        logger.info(
            f"Audit: application={application_id} action={action} old={old_status} new={new_status} by={performed_by}"
        )

