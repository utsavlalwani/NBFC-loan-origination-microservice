import logging, random
from decimal import Decimal

logger = logging.getLogger(__name__)


class ScoringEngine:
    """
    Derives a final credit score and loan terms from:
    - bureau_score (from credit bureau API)
    - monthly_income
    - requested_amount
    - employment_type

    Score tiers:
    >= 750 -> full amount, lowest rate
    700 - 749 -> 90% amount, standard rate
    650 - 699 -> 75% amount, elevated rate  -> UNDER_REVIEW
    600 - 649 -> 60% amount, high rate -> UNDER_REVIEW
    < 600 -> REJECTED
    """

    def calculate(self, bureau_score: int, monthly_income: float, requested_amount: float, employment_type: str) -> dict:
        score = bureau_score

        # Income-based modifier
        if monthly_income >= 100_000:
            score = min(score + 20, 900)
        elif monthly_income >= 50_000:
            score = min(score + 10, 900)

        # Employment Stability Modifier
        if employment_type == "salaried":
            score = min(score + 10, 900)

        # Loan-to-Income Modifier
        ratio = requested_amount / monthly_income
        if ratio <= 2.0:
            score = min(score + 15, 900)
        elif ratio > 4.0:
            score = max(score - 20, 300)

        # Determining the terms based on final score
        if score >= 750:
            return {
                "final_score": score,
                "approved_amount": Decimal(str(requested_amount)).quantize(Decimal("0.01")),
                "interest_rate": Decimal("10.50"),
                "tenure_months": 60,
                "decision": "approved",
            }
        elif score >= 700:
            return {
                "final_score": score,
                "approved_amount": (Decimal(str(requested_amount)) * Decimal("0.90")).quantize(Decimal("0.01")),
                "interest_rate": Decimal("12.00"),
                "tenure_months": 48,
                "decision": "approved",
            }
        elif score >= 650:
            return {
                "final_score": score,
                "approved_amount": (Decimal(str(requested_amount)) * Decimal("0.75")).quantize(Decimal("0.01")),
                "interest_rate": Decimal("14.50"),
                "tenure_months": 36,
                "decision": "under_review",
            }
        elif score >= 600:
            return {
                "final_score": score,
                "approved_amount": (Decimal(str(requested_amount)) * Decimal("0.60")).quantize(Decimal("0.01")),
                "interest_rate": Decimal("16.00"),
                "tenure_months": 24,
                "decision": "under_review",
            }
        else:
            return {
                "final_score": score,
                "approved_amount": Decimal("0"),
                "interest_rate": Decimal("0"),
                "tenure_months": 0,
                "decision": "rejected",
            }

