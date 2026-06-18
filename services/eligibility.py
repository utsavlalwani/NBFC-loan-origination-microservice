import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import EligibilityConfig
from schemas.application import LoanApplicationCreate

logger = logging.getLogger(__name__)


class EligibilityService:
    """
    Checks a loan application against configurable business rules.

    Rules are loaded from the eligibility_config table, so the business team can update the thresholds(e.g., raise MIN_MONTHLY_INCOME from 15000 to 20000) without any code deployment -- just a DB row update.

    Falls back to hardcoded defaults if a rule is not in the DB.
    """

    DEFAULT_RULES: dict[str, str] = {
        "MIN_MONTHLY_INCOME": "15000",
        "MAX_LOAN_AMOUNT": "5000000",
        "MIN_LOAN_AMOUNT": "10000",
        "MAX_LOAN_TO_INCOME_RATIO": "5.0",
        "MIN_AGE_YEARS": "21",
        "MAX_AGE_YEARS": "60",
        "ALLOWED_EMPLOYMENT_TYPES": "salaried, self_employed",
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self._rules: dict[str, str] = {}

    async def _load_rules(self):
        result = await self.db.execute(select(EligibilityConfig))
        db_rules = {row.rule_key: row.rule_value for row in result.scalars().all()}
        # DB Rules override defaults -- business team has final say
        self._rules = {**self.DEFAULT_RULES, **db_rules}
        logger.debug(f"Loaded {len(self._rules)} eligibility rules")

    async def check(self, application: LoanApplicationCreate) -> tuple[bool, str]:
        """
        Return (is_eligible: bool, fail_reason: str)
        is_eligible=True means all rules passed.
        """
        await self._load_rules()
        import datetime

        # 1. Income floor
        min_income = float(self._rules["MIN_MONTHLY_INCOME"])
        if float(application.monthly_income) < min_income:
            return False, (
                f"Montly Income Rs. {application.monthly_income:,.0f} is below the minimum requirement of Rs. {min_income:,.0f}."
            )

        # 2. Loan amount range
        min_amt = float(self._rules["MIN_LOAN_AMOUNT"])
        max_amt = float(self._rules["MAX_LOAN_AMOUNT"])
        req_amt = float(application.requested_amount)
        if req_amt < min_amt:
            return False, f"Requested amount Rs. {req_amt:,.0f} is below minimum Rs. {min_amt:,.0f}."
        if req_amt > max_amt:
            return False, f"Requested amount Rs. {req_amt:,.0f} is exceeds maximum Rs. {max_amt:,.0f}."

        # 3. Loan-to-Income Ratio
        max_ratio = float(self._rules["MAX_LOAN_TO_INCOME_RATIO"])
        actual_ratio = req_amt / float(application.monthly_income)
        if actual_ratio > max_ratio:
            return False, (
                f"Loan-to-Income Ratio {actual_ratio:.1f}x exceeds the maximum allowed {max_ratio}x."
            )

        # 4. Age Window
        today = datetime.date.today()
        age = today.year - application.date_of_birth.year - ((today.month, today.day) < (application.date_of_birth.month, application.date_of_birth.day))
        min_age = int(self._rules["MIN_AGE_YEARS"])
        max_age = int(self._rules["MAX_AGE_YEARS"])

        if age < min_age:
            return False, f"Applicant age {age} is below the minimum of {min_age} years."
        if age > max_age:
            return False, f"Applicant age {age} exceeds the maximum of {max_age} years."

        # 5. Employment Type Whitelist
        allowed = [e.strip() for e in self._rules["ALLOWED_EMPLOYMENT_TYPES"].split(",")]
        if application.employment_type.value not in allowed:
            return False, f"Employment type '{application.employment_type.value}' is not eligible."

        return True, "All Eligibility Checks Passed."

