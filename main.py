import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import create_tables
from middleware.tracing import RequestTracingMiddleware
from routers import applications, auth, health

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")
    await create_tables()
    logger.info("Database tables verified.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    **LoanFlow is a digital loan origination API.
    
    ## How it works:-
    1. Client submits a loan application via `POST /api/v1/applications`
    2. API validates, checks eligibility, persists, and returns **202 Accepted** immediately
    3. A background task calls the credit bureau, runs the scoring engine, and updates the application
    4. Client polls `GET /api/v1/applications/{id}` to get the final decision
    
    ## Authentication
    All end-points require a **Bearer JWT** token. Get one form `POST /api/v1/auth/login`.
    
    ## Roles
    - `applicant` -- submit and view own applications
    - `ops` -- view all applications, manual status updates
    - `admin` -- full access
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- Middleware --------------------------------------------

app.add_middleware(RequestTracingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # locking down to our frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Global Exception Handlers ------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        f"Unhandled exception [{request_id}]: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again.",
            "request_id": request_id,
        },
    )


# --- Routers ----------------------------------------------------

app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(applications.router, prefix="/api/v1/applications", tags=["Loan Applications"])

# --- Dev Entrypoint ----------------------------------------------

if __name__ == '__main__':
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
