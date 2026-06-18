# LoanFlow

An async **loan origination microservice** built with FastAPI. It accepts loan
applications, runs configurable eligibility rules, and performs credit scoring
asynchronously so the API can respond immediately.

## How it works

`POST /api/v1/applications` validates the payload, checks for a duplicate active PAN,
runs DB-backed eligibility rules, persists the application with status
`credit_check_pending`, and returns **202 Accepted** right away. A background task then
calls the credit bureau (mock or real), runs the scoring engine, updates the
application's status and terms, and writes an audit-trail entry. The client polls
`GET /api/v1/applications/{id}` for the final decision.

- **Async stack:** FastAPI + SQLAlchemy 2.0 async (`asyncpg`) on PostgreSQL 16.
- **Auth:** every API route requires a JWT Bearer token.
- **Roles:** `applicant` (submit / read own), `ops` (list all, manual status overrides),
  `admin` (full access). Enforced in `dependencies.py` via `require_role()`.
- **Eligibility rules** live in the `eligibility_config` table (income floor, loan-amount
  range, loan-to-income ratio, age window, employment type), with hardcoded fallbacks.
- **Scoring** (`services/scoring.py`) maps a bureau score to a decision and terms:
  `>= 700` approved, `600–699` under review, `< 600` rejected.
- **Audit trail** (`audit_logs`) is append-only for compliance.
- **Request tracing:** every request/response carries an `X-Request-ID` header.

## Project layout

```
.
├── main.py                 # app, lifespan, middleware, router registration
├── config.py               # Settings (pydantic-settings) + feature flags
├── database.py             # async engine, session factory, table creation
├── models.py               # SQLAlchemy models + enums
├── dependencies.py         # get_db, JWT auth, require_role, token creation
├── middleware/tracing.py   # RequestTracingMiddleware (X-Request-ID + timing)
├── schemas/                # Pydantic request/response models
├── services/               # eligibility, scoring, credit_bureau, audit
├── routers/                # health, auth, applications
└── tests/                  # pytest suite (httpx ASGI client)
```

## API endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET`  | `/health/` | none | Service info |
| `GET`  | `/health/db` | none | DB connectivity check |
| `POST` | `/api/v1/auth/login` | none | Returns a JWT access token |
| `POST` | `/api/v1/applications/` | any role | Submit application → **202** |
| `GET`  | `/api/v1/applications/` | ops / admin | Paginated list |
| `GET`  | `/api/v1/applications/{id}` | any role | Full application detail |
| `PATCH`| `/api/v1/applications/{id}/status` | ops / admin | Manual status override |

Interactive docs are served at `/docs` (Swagger) and `/redoc`.

### Demo login credentials

Auth currently uses a hardcoded user map (`routers/auth.py`):

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin123` | admin |
| `ops_user` | `ops123` | ops |
| `applicant` | `app123` | applicant |

## Setup

Requires **Python 3.11+** and **PostgreSQL 16** (or use Docker, below).

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your environment file and fill in SECRET_KEY (and any AWS/bureau keys)
cp .env.example .env
```

Feature flags in `.env` (`USE_REAL_CREDIT_BUREAU`, `USE_AWS_SQS`, `USE_AWS_S3`) default to
`False`, so the service runs fully against local mocks with no external credentials.

## Run

### With Docker (recommended)

Starts PostgreSQL and the API (with hot reload) together:

```bash
docker-compose up
```

The API is available at <http://localhost:8000> and the database at `localhost:5432`.

### Locally without Docker

With a PostgreSQL instance running and `DATABASE_URL` pointing at it:

```bash
uvicorn main:app --reload
```

Tables are created automatically on startup via `Base.metadata.create_all()`.

## Test

The test suite connects to a separate `loanflow_test` database on `localhost:5432`
(see `tests/conftest.py`). Create it once, then run pytest:

```bash
# create the test database (PostgreSQL must be running and reachable on localhost:5432)
createdb -h localhost -U postgres loanflow_test

# run the suite
python -m pytest

# a single test
python -m pytest tests/test_applications.py::test_submit_application_success -v
```

`pytest.ini` sets `asyncio_mode = auto`, so async tests run without per-test markers.

## Production image

The `Dockerfile` is a multi-stage build (`base` → `builder` → `production`) that runs
Gunicorn with 4 Uvicorn workers:

```bash
docker build -t loanflow .
docker run -p 8000:8000 --env-file .env loanflow
```
