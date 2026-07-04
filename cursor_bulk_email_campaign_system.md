# Bulk email campaign system
_Exported on 7/5/2026 at 01:02:19 GMT+5:30 from Cursor (3.9.16)_

---

**User**

You are a Senior Full Stack Engineer and Software Architect.

Build a production-quality MVP of a Bulk Email Campaign Management System.

The code should be clean, modular, scalable and follow best software engineering practices.

========================================================
TECH STACK
========================================================

Frontend:
- React
- JavaScript
- React Router
- Axios
- TailwindCSS
- React Icons

Backend:
- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- Alembic
- Pandas
- Boto3
- MSAL (Microsoft Authentication)
- OpenAI API (AI Email Generation)

Project Structure should separate frontend and backend.

========================================================
APPLICATION OVERVIEW
========================================================

The application is an internal company tool used by sales teams to send bulk cold emails.

Workflow:

Microsoft Login

↓

Dashboard

↓

Create Campaign

↓

Choose Email Template

↓

Select Recipients

↓

Preview Email

↓

Send using AWS SES

↓

View Logs

========================================================
AUTHENTICATION
========================================================

Implement Microsoft SSO Authentication.

After login:

Store user session.

Display:

- Name
- Email
- Department (placeholder)

Protect all routes.

Create login page.

========================================================
SIDEBAR
========================================================

Create a professional collapsible sidebar.

Pages:

Dashboard

Campaigns

Recipients

Templates

Email Logs

Settings

Logout

========================================================
DASHBOARD
========================================================

Build a modern dashboard.

Cards:

Total Campaigns

Emails Sent

Pending Emails

Failed Emails

Active Campaigns

AI Generated Emails

Recent Activity

Charts:

Emails sent per day

Campaign status

Recent campaigns table

Use dummy backend data.

Structure code so dashboard becomes dynamic later.

========================================================
CAMPAIGNS PAGE
========================================================

Campaign list page.

Table columns:

Campaign Name

Campaign ID

Owner

Created Date

Status

Emails Sent

Actions

Buttons:

Create Campaign

Edit

Delete

View

========================================================
CREATE CAMPAIGN PAGE
========================================================

Create a multi-step form.

Step 1

Campaign Information

Campaign Name

Campaign ID

Campaign Description

Owner

Department

Target Audience

Subject

Step 2

Choose Template

Three options:

1 Manual

Rich Text Editor

2 Placeholder Template

Choose from hardcoded templates.

Example:

Hello {{Name}}

We noticed {{Company}} ...

Automatically detect placeholders.

Generate input boxes.

Live Preview updates while typing.

3 AI Template

User enters campaign details.

Send prompt to OpenAI.

Generate:

Subject

Email Body

Closing

CTA

User can edit generated email.

========================================================
RECIPIENT PAGE
========================================================

Upload Excel (.xlsx)

Read using Pandas.

Columns:

Name

Email

Company

Designation

Industry

Display data in searchable table.

Features:

Search

Filter

Checkbox selection

Select All

Deselect All

Pagination

Selected count

========================================================
EMAIL PREVIEW
========================================================

Show:

Subject

Recipient Name

Rendered Email

Desktop email preview card.

========================================================
EMAIL SENDING
========================================================

Create backend service using AWS SES.

For now:

Keep credentials in .env.

Create service class.

Function:

send_bulk_email()

Loop through selected recipients.

Replace placeholders.

Call AWS SES.

Return:

Sent

Failed

Pending

Log all responses.

========================================================
EMAIL LOGS PAGE
========================================================

Table:

Recipient

Campaign

Date

Status

Error Message

Search

Filter

Pagination

========================================================
DATABASE
========================================================

Create SQLAlchemy models.

User

id

name

email

department

Campaign

id

campaign_name

campaign_id

description

owner

status

created_at

Template

id

campaign_id

type

subject

body

Recipient

id

name

email

company

designation

industry

EmailLog

id

campaign_id

recipient_id

status

error_message

sent_at

Generate migrations.

========================================================
API ENDPOINTS
========================================================

Auth

GET /login

GET /callback

Dashboard

GET /dashboard/stats

Campaign

POST /campaign

GET /campaigns

PUT /campaign/{id}

DELETE /campaign/{id}

Recipients

POST /upload-excel

GET /recipients

POST /select-recipients

Templates

POST /generate-ai-template

POST /preview-template

Email

POST /send

Logs

GET /logs

========================================================
AI EMAIL GENERATION
========================================================

Create service:

ai_service.py

Function:

generate_email(campaign_data)

Prompt should generate:

Professional sales email

Catchy subject

CTA

Formal tone

Short

Personalized

Editable output

========================================================
SERVICES
========================================================

Create separate services.

auth_service.py

ses_service.py

ai_service.py

excel_service.py

campaign_service.py

dashboard_service.py

========================================================
FRONTEND
========================================================

Professional SaaS Admin Dashboard.

Responsive.

Modern spacing.

Rounded cards.

Professional colors.

Loading animations.

Toast notifications.

Modals.

Confirmation dialogs.

Reusable components.

Component folders.

========================================================
BACKEND
========================================================

Use FastAPI best practices.

Dependency Injection.

Routers.

Services.

Models.

Schemas.

Validation.

Exception Handling.

Logging.

.env support.

========================================================
FOLDER STRUCTURE
========================================================

backend/

app/

routers/

models/

schemas/

services/

database/

middleware/

utils/

main.py

frontend/

src/

pages/

components/

layouts/

hooks/

services/

utils/

========================================================
DUMMY DATA
========================================================

Until integrations are completed:

Generate dummy dashboard statistics.

Generate dummy campaign list.

Generate sample recipients.

Generate sample email logs.

========================================================
CODE QUALITY
========================================================

Follow SOLID principles.

Avoid duplicated code.

Comment important logic.

Use reusable components.

Do NOT leave TODO placeholders unless absolutely necessary.

========================================================
OUTPUT
========================================================

Generate the ENTIRE project.

Create all folders.

Create all files.

Write complete code.

Generate backend and frontend together.

The application should compile and run after installing dependencies, even if AWS SES and OpenAI credentials are not yet configured.

When external services are unavailable, use mocked responses so the application remains fully navigable.

---

**Cursor**

This is a full-stack MVP — I'll map the workspace first, then build backend and frontend in parallel with mocked integrations so it runs without AWS/OpenAI credentials.


The workspace is empty — I'll scaffold the full backend and frontend from scratch.


Fixing the campaign routes path, then scaffolding the frontend.


Scaffolding the frontend: config, core app files, and shared utilities.


Creating all pages and the App router.


Fixing the database fallback, adding README and .gitignore, then verifying the build.


---

**User**

Review the current project and determine which features from the original specification have already been implemented. Do not recreate existing code.

