# Bulk Email Campaign Manager — Project Status

Internal Feuji Sales tool for building prospect lists, writing merge-field
templates, and running bulk email campaigns (with scheduled follow-ups)
through Amazon SES. FastAPI backend, React (Vite) frontend, PostgreSQL in
production (SQLite fallback for quick local dev).

Repo: https://github.com/Vijayrayapati286/LeadSense (private) — the shared
center repo for dev + devops. `upstream` remote still points at the
original open-source project this was cloned from.

## Architecture

- **Campaign → Template(s) → CampaignRecipient → Recipient / RecipientGroup**
  A campaign can hold multiple templates, each independently tag-able to a
  named prospect list ("group"). `CampaignRecipient` is the per-campaign
  join row carrying status, which template a recipient is tagged to, and
  scheduling state.
- **Merge fields**: 15 standard headers (Name, Email, Company, Designation,
  Designation Level, Industry, Department, Country, State, City, Company
  Size, Years of Experience, Skills, Source, Status) resolve automatically.
  Anything else used as `{{Field}}` in a template is a *custom field* —
  requires explicit approval on first use, and a per-prospect value
  (`RecipientCustomValue`) before a send to that prospect is allowed; a
  prospect missing a required custom value is skipped (not the whole
  batch), with the reason surfaced back in the send response.
- **Sending**: `ses_service.py` wraps boto3 SES, with a mock fallback
  (`USE_MOCK_SES`). From-display-name and Reply-To are set per campaign
  owner — mail appears to come from the sender's real name, with replies
  routed to their real corporate mailbox (see the separate deliverability
  design doc for the fuller subdomain-isolation plan; the `go.feuji.com`
  isolated-subdomain piece there is not yet live — sending is still on the
  root `feuji.com` verified identity).
- **Scheduling**: a campaign can be sent immediately, scheduled for a
  future date/time (`campaign.scheduled_at`), and/or gated to only send
  within each prospect's local business hours
  (`campaign.use_recipient_timezone`, recipient timezone auto-derived from
  Country/State at Excel-import time). All surfaced in the Prospects tab's
  "Preview & Send" dialog.
- **Engagement Studio** (formerly "Follow-up Sequence", `EngagementStudioStage`
  / `EngagementStudioList` models): per-campaign automation of stages 1+
  (stage 0 is always the Template tab's immediate send). Each stage either
  references a reusable library template (`Mailer`, via `mailer_id` — a live
  reference, so edits are picked up on the next send) or has its own inline
  content, fires after a configurable delay, and can be set to skip prospects
  who already have a manual response tag (`skip_if_tagged`). Optionally
  scoped to a subset of the campaign's prospect lists
  (`EngagementStudioList`; no rows = whole campaign). The Engagement Studio
  tab also shows a responded vs. non-responsive breakdown for whatever scope
  is configured.
- **Background jobs**: APScheduler running in-process inside the FastAPI
  app (`scheduler_service.py`) — polls every 5s for queued sends, every
  300s for due Engagement Studio stages. **No distributed lock** — see
  Critical Constraints below.

## Auth

Three login paths, all funneling through the same allowlist gate:

- **Password login** (`POST /auth/login`) — email + password, bcrypt-hashed.
- **Dev login** (`POST /auth/dev-login`) — type an email (and optionally a
  name); used before Azure AD is wired up.
- **Azure AD SSO** — not yet configured (`AZURE_CLIENT_ID`/`SECRET` still
  placeholders); the app falls back to dev-login when unconfigured.

**Allowlist gate**: `app/services/core_users.py` (`CORE_USERS`, committed —
names/emails only) is the single source of truth for who can authenticate
*at all*, checked in `AuthService._upsert_user`, the choke point both
dev-login and the Azure AD callback pass through. Anyone not on this list
gets a 403, regardless of login path.

**Passwords are not in source.** They're supplied via the
`CORE_USER_PASSWORDS` env var (JSON `{email: password}`), read by
`seed_service.provision_core_users`, which runs unconditionally on every
startup — get-or-creates each `CORE_USERS` entry and (re)hashes its
password from that env var. A user with no entry in the env var still gets
created (so the allowlist/identity works) but has no usable password until
one's configured. Real passwords for the 9 current accounts exist only in
`backend/.env` (gitignored) — distributed to each person out of band, not
recorded in this repo.

## Deployment

- **Local (day-to-day dev)**: `docker compose up db` for Postgres only,
  backend/frontend run natively (`uvicorn --reload`, `npm run dev`) —
  Docker Desktop's bind-mount hot-reload is slow on Windows, so running the
  full stack in containers for every save isn't worth it. `db` is exposed
  on `localhost:5432` for this reason (see `docker-compose.yml`).
  `backend/.env`'s `DATABASE_URL` already targets `localhost`, and
  `connection.py` auto-falls-back to SQLite if Postgres isn't reachable.
- **Local (full-stack verification)**: `docker compose up` (all three
  services) — `db` (Postgres), `backend` (FastAPI/uvicorn), `frontend`
  (nginx serving the Vite build, reverse-proxying `/api/` to the backend —
  this is what lets an L4 load balancer with no path routing of its own sit
  in front of one origin). Copy `.env.example` → `.env` (compose-level
  Postgres creds) and `backend/.env.example` → `backend/.env` (app
  secrets/config) to run it. This is the same shape the k8s pods will run
  in, so it's the right check before shipping a container change — not the
  loop to use on every save. Verified working end-to-end (build + boot +
  real request through the full chain) as of this write-up.
- **AWS target**: cost-optimized Kubernetes-based stack — NLB (TCP
  passthrough) → ingress-nginx (does the path routing NLB can't) →
  pods; cert-manager + Let's Encrypt instead of ACM; GoDaddy DNS instead
  of Route 53; native Kubernetes Secrets instead of Secrets Manager; no
  CloudWatch. RDS PostgreSQL still recommended over running Postgres
  in-cluster. SES plan: **Essentials** tier (no inbound Mail Manager
  features needed — replies route to the rep's real mailbox via
  Reply-To, never through SES).

## Critical constraints — read before touching scaling or auto-scaling

- **Backend must run as exactly one replica/task, always.** The Engagement
  Studio and queued-send scheduler is in-process with no distributed lock —
  running more than one backend instance means every due prospect gets
  duplicated sends. Fix requires moving to a real queue (e.g. SQS or
  similar) before this can change.
- **The backend process must stay up continuously** for scheduled sends
  and business-hours gating to fire — don't scale it to zero overnight for
  cost savings.

## Known gaps / not yet done

- Azure AD app registration not created — SSO is dev-login-only for now.
- Nothing deployed to AWS yet — Dockerfiles/compose exist and are verified
  locally, but no RDS/cluster/DNS has actually been provisioned.
- No monitoring/alerting wired up anywhere (matches the "no CloudWatch"
  decision — if the SES bounce/complaint circuit breaker from the
  deliverability doc is still wanted, it needs a different mechanism, e.g.
  a small scheduled job polling SES stats).
- No self-service password change/reset flow — rotating a password today
  means updating `CORE_USER_PASSWORDS` and restarting.
- LeadSense repo currently lives under a personal GitHub account
  (Vijayrayapati286) — whether it moves to an org is still an open
  decision.
- The `go.feuji.com` subdomain-isolation sending identity (separate DKIM,
  reputation isolation from the root domain) is designed but not set up —
  needs DNS access to feuji.com's zone, likely outside this team.

## Where things live (quick map)

- `backend/app/routers/` — API endpoints, one file per resource
- `backend/app/services/` — business logic (`campaign_service`,
  `auth_service`, `ses_service`, `scheduler_service`, `excel_service`,
  `seed_service`, `core_users`)
- `backend/app/models/models.py` — SQLAlchemy models
- `backend/alembic/versions/` — schema migrations (run via
  `alembic upgrade head`; not run automatically at container startup)
- `frontend/src/pages/` — `CampaignDetailPage.jsx` is the largest/most
  central file (prospects, templates, sending, Engagement Studio all live here)
- `frontend/src/utils/mergeFields.js` — the 15 standard merge-field
  definitions, mirrored server-side in `backend/app/utils/helpers.py`
