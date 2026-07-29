# Bulk Email Campaign Management System

A production-quality MVP for managing bulk cold email campaigns. Built for internal sales teams with Microsoft SSO, AI-powered email generation, AWS SES delivery, and comprehensive analytics.

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Frontend | React, Vite, TailwindCSS, React Router, Axios, Recharts |
| Backend | Python, FastAPI, SQLAlchemy, Alembic, Pandas |
| Auth | Microsoft SSO (MSAL) with dev-mode fallback |
| Email | AWS SES (Boto3) with mock fallback |
| AI | Groq API (Llama 3.3 70B) with mock fallback |
| Database | PostgreSQL with SQLite fallback |

## Project Structure

```
Bulk_Email_Project/
├── backend/
│   ├── app/
│   │   ├── routers/        # API route handlers
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic validation schemas
│   │   ├── services/       # Business logic layer
│   │   ├── database/       # DB connection & session
│   │   ├── middleware/     # Auth middleware
│   │   ├── utils/          # Helper functions
│   │   └── main.py         # FastAPI entry point
│   ├── alembic/            # Database migrations
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/          # Route pages
│   │   ├── components/     # Reusable UI components
│   │   ├── layouts/        # Sidebar & main layout
│   │   ├── hooks/          # Auth & toast hooks
│   │   ├── services/       # API client layer
│   │   └── utils/          # Frontend helpers
│   └── package.json
└── README.md
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (for local Postgres — see below)

### Local Postgres (recommended over the SQLite fallback)

```bash
copy .env.example .env       # Windows, only needed the first time (Postgres creds)
docker compose up db         # starts only the "db" service, leaves it running
```

Backend and frontend still run natively (`uvicorn --reload`, `npm run dev`) — full
`docker compose up` (all three services) is for validating the container build, not
day-to-day iteration; Docker Desktop's bind-mount hot-reload is slow on Windows.
`backend/.env`'s `DATABASE_URL` already points at `localhost:5432`, so once the `db`
container is up the backend connects to real Postgres automatically (falls back to
SQLite only if Postgres is unreachable).

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux

# Start the server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000` with docs at `http://localhost:8000/docs`.

On first startup, the database is auto-created (SQLite fallback) and seeded with sample data.

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

The app will be available at `http://localhost:5180`.

### Login

Click **"Dev Login (Demo)"** on the login page to authenticate without Azure AD credentials. All external services run in mock mode by default.

## Features

- **Microsoft SSO** — Full OAuth flow with dev-mode fallback
- **Dashboard** — Stats cards, bar/pie charts, recent activity feed
- **Campaign Management** — CRUD with multi-step creation wizard
- **Email Templates** — Manual editor, placeholder templates, AI generation
- **Recipient Management** — Excel upload, search, filter, bulk selection
- **Email Preview** — Desktop-style email preview card
- **Bulk Sending** — AWS SES integration with mock fallback
- **Email Logs** — Searchable, filterable delivery log table
- **Collapsible Sidebar** — Professional navigation with user profile

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/login` | Get Microsoft login URL |
| GET | `/api/auth/callback` | OAuth callback |
| POST | `/api/auth/dev-login` | Development login |
| GET | `/api/dashboard/stats` | Dashboard statistics |
| POST | `/api/campaign` | Create campaign |
| GET | `/api/campaigns` | List campaigns |
| PUT | `/api/campaign/{id}` | Update campaign |
| DELETE | `/api/campaign/{id}` | Delete campaign |
| POST | `/api/recipients/upload-excel` | Upload Excel file |
| GET | `/api/recipients` | List recipients |
| POST | `/api/recipients/select-recipients` | Select/deselect recipients |
| POST | `/api/templates/generate-ai-template` | AI email generation |
| POST | `/api/templates/preview-template` | Preview rendered template |
| POST | `/api/email/send` | Send bulk emails |
| GET | `/api/logs` | Email delivery logs |

## Configuration

Copy `backend/.env.example` to `backend/.env` and configure:

| Variable | Description | Default |
|----------|-------------|---------|
| `USE_SQLITE_FALLBACK` | Use SQLite when PostgreSQL unavailable | `true` |
| `USE_MOCK_SES` | Mock AWS SES sending | `true` |
| `USE_MOCK_GROQ` | Mock Groq generation | `true` |
| `AZURE_CLIENT_ID` | Microsoft Azure app client ID | — |
| `AWS_ACCESS_KEY_ID` | AWS credentials for SES | — |
| `GROQ_API_KEY` | Groq API key | — |

Set mock flags to `false` and provide real credentials to enable live integrations.

## Database Migrations

The app itself creates the full current schema on startup (`init_db()` →
`Base.metadata.create_all()`), so a **fresh** database needs stamping, not
upgrading:

```bash
cd backend
uvicorn app.main:app --port 8000   # first run: creates all tables, then Ctrl+C
alembic stamp head                 # tells Alembic this DB is already at head
```

Only after that does the normal flow apply for actual schema changes going
forward:

```bash
alembic revision --autogenerate -m "..."
alembic upgrade head
```

Running `alembic upgrade head` against a brand-new empty database fails —
the migration files are incremental diffs assuming tables already exist.

## License

Internal use only.
