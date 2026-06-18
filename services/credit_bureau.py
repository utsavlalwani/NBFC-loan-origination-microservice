import random, logging, httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings

logger = logging.getLogger(__name__)


class CreditBureauClient:
    """
    Wraps the Credit Bureau API call.

    In production: calls the real CIBIL/Experian API. With USE_REAL_CREDIT_BUREAU=False: returns a simulated score deterministically derived from the PAN number -- same PAN always gets the same score, which makes manual testing predictable.

    Retry logic: 3 attempts with exponential backoff (1s, 2s, 4s).
    """

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def fetch_score(self, pan_number: str, date_of_birth: str) -> int:
        if not settings.USE_REAL_CREDIT_BUREAU:
            return self._mock_score(pan_number)

        async with httpx.AsyncClient(timeout=settings.CREDIT_BUREAU_TIMEOUT) as client:
            response = await client.post(
                f"{settings.CREDIT_BUREAU_URL}/score",
                json={"pan": pan_number, "dob": date_of_birth},
                headers={
                    "Authorization": f"Bearer {settings.CREDIT_BUREAU_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
            score = data.get("credit_score") or data.get("score")
            if not score:
                raise ValueError(f"No score in bureau responses: {data}")
            logger.info(f"Bureau score for PAN ***{pan_number[-4]}: {score}")
            return int(score)

    def _mock_score(self, pan_number: str) -> int:
        """
        Deterministic mock -- same PAN always returns the same score. Range 550-850, seeded from PAN characters.
        """
        seed = sum(ord(c) for c in pan_number)
        rng = random.Random(seed)
        score = rng.randint(550, 850)
        logger.info(f"Mock bureau score for PAN ***{pan_number[-4]}: {score}")
        return score
