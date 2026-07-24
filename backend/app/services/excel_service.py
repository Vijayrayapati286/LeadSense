"""Excel file processing service using Pandas."""

import io
import logging
import re

import pandas as pd
from sqlalchemy.orm import Session

from app.models import CustomField, Recipient, RecipientCustomValue, SuppressionEntry
from app.utils.timezone_lookup import lookup_timezone

logger = logging.getLogger(__name__)


def _normalize_header(header: str) -> str:
    """Lowercase and strip non-alphanumerics, so a "Phone Number" column
    matches an approved custom field named "PhoneNumber"."""
    return re.sub(r"[^a-z0-9]", "", header.lower())

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
    "Department": "department",
    "Company Size": "company_size",
    "Years of Experience": "years_of_experience",
    "Skills": "skills",
    "Country": "country",
    "City": "city",
    "Source": "source",
}

DATE_FIELDS = {"create_date"}


class ExcelService:
    def parse_excel(
        self, file_content: bytes, custom_field_names: set[str] | None = None
    ) -> list[tuple[dict, dict]]:
        """Parse Excel file. Returns a list of (recipient_data, custom_values)
        pairs — custom_values maps an approved CustomField name to this row's
        value, for any spreadsheet column outside COLUMN_MAP whose
        (normalized) header matches one of `custom_field_names`."""
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

        # Match unmapped spreadsheet columns to approved custom fields by a
        # normalized header comparison (case/whitespace/punctuation-insensitive).
        custom_columns: dict[str, str] = {}  # spreadsheet header -> CustomField name
        if custom_field_names:
            normalized_custom = {_normalize_header(name): name for name in custom_field_names}
            for header in df.columns:
                if header in COLUMN_MAP:
                    continue
                match = normalized_custom.get(_normalize_header(header))
                if match:
                    custom_columns[header] = match

        rows = []
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

            custom_values = {}
            for header, field_name in custom_columns.items():
                value = row.get(header)
                if pd.isna(value):
                    continue
                text = str(value).strip()
                if text:
                    custom_values[field_name] = text

            rows.append((data, custom_values))

        return rows

    def import_recipients(self, db: Session, file_content: bytes) -> tuple[int, int, list[int]]:
        """Import recipients from Excel. A new email is inserted; an email
        that already exists is upserted — its profile fields (name, company,
        designation, etc.) are refreshed from this row instead of being left
        stale, since the same address is often re-uploaded later with
        corrected or additional details. Suppression status is never touched
        by an upsert; any active (non-overridden) suppression entry is only
        applied to newly-created rows, so a blacklisted address can't sneak
        back into sends without an explicit admin override.

        Returns (imported_count, updated_count, recipient_ids) where
        recipient_ids covers every recipient touched by this upload — new,
        updated, and unchanged — so callers (e.g. group assignment) can act
        on the full uploaded set, not just new rows."""
        custom_fields = db.query(CustomField).all()
        field_ids_by_name = {f.name: f.id for f in custom_fields}
        parsed = self.parse_excel(file_content, custom_field_names=set(field_ids_by_name))
        imported = 0
        updated = 0
        touched_ids: list[int] = []

        existing = {r.email: r.id for r in db.query(Recipient.email, Recipient.id).all()}
        suppressed_reasons: dict[str, str] = {}
        active_entries = (
            db.query(SuppressionEntry)
            .filter(SuppressionEntry.overridden_at.is_(None))
            .order_by(SuppressionEntry.created_at.asc())
            .all()
        )
        for entry in active_entries:
            suppressed_reasons[entry.email] = entry.reason

        for data, custom_values in parsed:
            if data["email"] in existing:
                recipient_id = existing[data["email"]]
                recipient = db.query(Recipient).filter(Recipient.id == recipient_id).first()
                for field, value in data.items():
                    if field == "email":
                        continue
                    setattr(recipient, field, value)
                touched_ids.append(recipient_id)
                updated += 1
            else:
                if data["email"] in suppressed_reasons:
                    data["is_suppressed"] = True
                    data["suppression_reason"] = suppressed_reasons[data["email"]]
                data["timezone"] = lookup_timezone(data.get("country"), data.get("state"))
                recipient = Recipient(**data)
                db.add(recipient)
                db.flush()
                recipient_id = recipient.id
                existing[data["email"]] = recipient_id
                touched_ids.append(recipient_id)
                imported += 1

            self._upsert_custom_values(db, recipient_id, custom_values, field_ids_by_name)

        db.commit()
        return imported, updated, touched_ids

    def _upsert_custom_values(
        self, db: Session, recipient_id: int, custom_values: dict[str, str], field_ids_by_name: dict[str, int]
    ) -> None:
        for field_name, value in custom_values.items():
            custom_field_id = field_ids_by_name.get(field_name)
            if custom_field_id is None:
                continue
            existing_value = (
                db.query(RecipientCustomValue)
                .filter(
                    RecipientCustomValue.recipient_id == recipient_id,
                    RecipientCustomValue.custom_field_id == custom_field_id,
                )
                .first()
            )
            if existing_value:
                existing_value.value = value
            else:
                db.add(RecipientCustomValue(
                    recipient_id=recipient_id, custom_field_id=custom_field_id, value=value
                ))

    def create_single_recipient(self, db: Session, data: dict) -> tuple[Recipient, bool]:
        """Create-or-upsert a single recipient by email, for the "Add
        Manually" prospect form — same upsert behavior as import_recipients,
        just for a single call site instead of a whole sheet. A matching
        email updates that recipient's non-empty fields with the new values
        rather than being a no-op (blank fields in the form never overwrite
        existing data); suppression status is left untouched either way.
        Returns (recipient, created)."""
        email = data["email"].strip().lower()
        existing = db.query(Recipient).filter(Recipient.email == email).first()
        if existing:
            for field, value in data.items():
                if field == "email":
                    continue
                if isinstance(value, str):
                    value = value.strip() or None
                if value:
                    setattr(existing, field, value)
            db.commit()
            db.refresh(existing)
            return existing, False

        record = {**data, "email": email}
        active_entry = (
            db.query(SuppressionEntry)
            .filter(SuppressionEntry.email == email, SuppressionEntry.overridden_at.is_(None))
            .order_by(SuppressionEntry.created_at.desc())
            .first()
        )
        if active_entry:
            record["is_suppressed"] = True
            record["suppression_reason"] = active_entry.reason
        record["timezone"] = lookup_timezone(record.get("country"), record.get("state"))

        recipient = Recipient(**record)
        db.add(recipient)
        db.commit()
        db.refresh(recipient)
        return recipient, True

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
