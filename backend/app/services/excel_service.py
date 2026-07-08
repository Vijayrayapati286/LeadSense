"""Excel file processing service using Pandas."""

import io
import logging

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Recipient

logger = logging.getLogger(__name__)

# Maps accepted spreadsheet column headers -> Recipient model field names.
# Several headers can map to the same field to stay compatible with older
# sheets (e.g. "Company" and "Company Name" both map to `company`).
COLUMN_MAP = {
    "Name": "name",
    "First name": "first_name",
    "Last name": "last_name",
    "Email": "email",
    "Email id": "email",
    "Company": "company",
    "Company Name": "company",
    "Designation": "designation",
    "Designation Level": "designation_level",
    "Industry": "industry",
    "Create Date": "create_date",
    "Fresh mail": "fresh_mail",
    "Follow up 1": "follow_up_1",
    "Follow up 2": "follow_up_2",
    "Follow up 3": "follow_up_3",
    "Grouping": "grouping",
    "Vertical": "vertical",
    "Sub Vertical": "sub_vertical",
    "Revenue": "revenue",
    "Revenue Range": "revenue_range",
    "Website": "website",
    "State": "state",
    "Region": "region",
    "Contact Location": "contact_location",
    "Campaign": "campaign_tag",
    "LinkedIn Message/InMail": "linkedin_message",
    "LinkedIn Connection Request": "linkedin_connection_request",
    "Response 1": "response_1",
    "Response 2": "response_2",
    "Status": "status",
    "Comments": "comments",
}

DATE_FIELDS = {"create_date"}


class ExcelService:
    def parse_excel(self, file_content: bytes) -> list[dict]:
        """Parse Excel file and return list of recipient dicts."""
        df = pd.read_excel(io.BytesIO(file_content), engine="openpyxl")

        # Normalize column names (strip whitespace)
        df.columns = [str(c).strip() for c in df.columns]

        has_email = "Email" in df.columns or "Email id" in df.columns
        has_name = "Name" in df.columns or (
            "First name" in df.columns and "Last name" in df.columns
        )
        if not has_email or not has_name:
            raise ValueError(
                "Missing required columns: an email column (Email / Email id) and "
                "a name column (Name, or First name + Last name) are required"
            )

        email_col = "Email" if "Email" in df.columns else "Email id"
        df = df.dropna(subset=[email_col])
        df[email_col] = df[email_col].astype(str).str.strip().str.lower()

        recipients = []
        for _, row in df.iterrows():
            data = {}
            for header, field in COLUMN_MAP.items():
                if header not in df.columns:
                    continue
                value = row.get(header)
                if pd.isna(value):
                    continue
                if field in DATE_FIELDS:
                    parsed = pd.to_datetime(value, errors="coerce")
                    data[field] = parsed.date() if not pd.isna(parsed) else None
                else:
                    text = str(value).strip()
                    data[field] = text or None

            if not data.get("name"):
                first = data.get("first_name") or ""
                last = data.get("last_name") or ""
                combined = f"{first} {last}".strip()
                if combined:
                    data["name"] = combined

            if not data.get("name") or not data.get("email"):
                continue

            recipients.append(data)

        return recipients

    def import_recipients(self, db: Session, file_content: bytes) -> int:
        """Import recipients from Excel, skipping duplicates by email."""
        parsed = self.parse_excel(file_content)
        imported = 0

        existing_emails = {
            r.email for r in db.query(Recipient.email).all()
        }

        for data in parsed:
            if data["email"] in existing_emails:
                continue
            recipient = Recipient(**data)
            db.add(recipient)
            existing_emails.add(data["email"])
            imported += 1

        db.commit()
        return imported

    def generate_sample_excel(self) -> bytes:
        """Generate a sample Excel file for download."""
        data = {
            "Name": ["John Smith", "Jane Doe", "Robert Johnson", "Emily Chen", "Michael Brown"],
            "Email": [
                "john.smith@acme.com",
                "jane.doe@techcorp.io",
                "robert.j@globalinc.com",
                "emily.chen@startup.co",
                "michael.b@enterprise.com",
            ],
            "Company": ["Acme Corp", "TechCorp", "Global Inc", "StartupCo", "Enterprise Ltd"],
            "Designation": ["CEO", "CTO", "VP Sales", "Founder", "Director"],
            "Industry": ["Technology", "Software", "Finance", "SaaS", "Manufacturing"],
        }
        df = pd.DataFrame(data)
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)
        return buffer.getvalue()
