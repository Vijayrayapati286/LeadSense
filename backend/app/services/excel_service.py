"""Excel file processing service using Pandas."""

import io
import logging

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Recipient

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"Name", "Email"}
OPTIONAL_COLUMNS = {"Company", "Designation", "Industry"}
ALL_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS


class ExcelService:
    def parse_excel(self, file_content: bytes) -> list[dict]:
        """Parse Excel file and return list of recipient dicts."""
        df = pd.read_excel(io.BytesIO(file_content), engine="openpyxl")

        # Normalize column names (strip whitespace)
        df.columns = [str(c).strip() for c in df.columns]

        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")

        df = df.dropna(subset=["Name", "Email"])
        df["Email"] = df["Email"].astype(str).str.strip().str.lower()

        recipients = []
        for _, row in df.iterrows():
            recipients.append({
                "name": str(row["Name"]).strip(),
                "email": str(row["Email"]).strip(),
                "company": str(row.get("Company", "")).strip() or None,
                "designation": str(row.get("Designation", "")).strip() or None,
                "industry": str(row.get("Industry", "")).strip() or None,
            })

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
