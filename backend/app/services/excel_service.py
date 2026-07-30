"""Spreadsheet/tabular file processing service using Pandas.

Accepts Excel (.xlsx/.xlsm/.xls/.xlsb), OpenDocument (.ods), and delimited
text (.csv/.tsv/.txt) prospect-list uploads."""

import csv
import io
import logging
import re
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.models import CustomField, Recipient, RecipientCustomValue, SuppressionEntry
from app.utils.timezone_lookup import lookup_timezone

logger = logging.getLogger(__name__)


def _normalize_header(header: str) -> str:
    """Lowercase and strip non-alphanumerics, so a "Phone Number" column
    matches an approved custom field named "PhoneNumber", and so required-
    column matching is insensitive to case/spacing (e.g. "Email ID",
    "EmailID", and "email id" all normalize to the same key)."""
    return re.sub(r"[^a-z0-9]", "", str(header).lower())


class MissingColumnsError(ValueError):
    """Raised when a required column (Name / Email) isn't present in the
    uploaded file. Carries the human-readable missing labels so the API/UI
    can list them individually instead of just showing a generic message."""

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Required column(s) missing: {', '.join(missing)}")


# Extensions accepted for prospect-list upload, and the pandas engine used to
# read each Excel-family format. CSV/TSV/TXT are handled separately since
# they're delimited text rather than a workbook.
EXCEL_ENGINES = {
    ".xlsx": "openpyxl",
    ".xlsm": "openpyxl",
    ".xls": "xlrd",
    ".xlsb": "pyxlsb",
    ".ods": "odf",
}
DELIMITED_EXTENSIONS = {".csv", ".tsv", ".txt"}
SUPPORTED_EXTENSIONS = set(EXCEL_ENGINES) | DELIMITED_EXTENSIONS

# Normalized header aliases that satisfy each required field. Matching is
# done against `_normalize_header` output, so "Email ID", "EmailID", and
# "Email Address" all resolve here regardless of the casing/spacing/
# punctuation used in the source file.
REQUIRED_EMAIL_ALIASES = ("email", "emailid", "emailaddress")
REQUIRED_NAME_ALIASES = {"name"}
REQUIRED_FIRST_NAME_ALIASES = {"firstname"}
REQUIRED_LAST_NAME_ALIASES = {"lastname"}


def _read_delimited(file_content: bytes, suffix: str) -> pd.DataFrame:
    """.tsv is always tab-separated; .csv/.txt sniff the delimiter since
    exports from Google Sheets/regional Excel locales sometimes use ';' or
    '|' instead of ','."""
    text = file_content.decode("utf-8-sig", errors="replace")
    if suffix == ".tsv":
        sep = "\t"
    else:
        try:
            sep = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
        except csv.Error:
            sep = ","
    return pd.read_csv(io.StringIO(text), sep=sep, engine="python")


def _read_dataframe(file_content: bytes, filename: str) -> pd.DataFrame:
    """Read a spreadsheet/delimited upload into a DataFrame based on its file
    extension, raising a friendly ValueError (rather than a raw stack trace)
    for anything empty, corrupted, or in an unsupported format."""
    if not file_content:
        raise ValueError("This file is empty. Please upload a file with prospect data.")

    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"Unsupported file type '{suffix or 'unknown'}'. Supported formats: {supported}"
        )

    try:
        if suffix in EXCEL_ENGINES:
            df = pd.read_excel(io.BytesIO(file_content), engine=EXCEL_ENGINES[suffix])
        else:
            df = _read_delimited(file_content, suffix)
    except Exception as exc:
        logger.warning("Failed to parse uploaded file %r: %s", filename, exc)
        raise ValueError(
            f"Could not read this file — it may be corrupted or not a valid {suffix} file."
        ) from exc

    if df.shape[1] == 0 or df.shape[0] == 0:
        raise ValueError("This file is empty. Please upload a file with prospect data.")

    return df

# Maps accepted spreadsheet column headers -> Recipient model field names.
# Several headers can map to the same field to stay compatible with older
# sheets (e.g. "Company" and "Company Name" both map to `company`), and
# lookups against this map are always done via `_normalize_header`, so the
# exact casing/spacing of a canonical header below doesn't need to match the
# source file's header verbatim.
COLUMN_MAP = {
    "Name": "name",
    "First name": "first_name",
    "Last name": "last_name",
    "Email": "email",
    "Email id": "email",
    "Email Address": "email",
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
        self, file_content: bytes, filename: str, custom_field_names: set[str] | None = None
    ) -> list[tuple[dict, dict]]:
        """Parse an uploaded prospect-list file (Excel/ODS/CSV/TSV/TXT — see
        SUPPORTED_EXTENSIONS). Returns a list of (recipient_data,
        custom_values) pairs — custom_values maps an approved CustomField
        name to this row's value, for any spreadsheet column outside
        COLUMN_MAP whose (normalized) header matches one of
        `custom_field_names`."""
        df = _read_dataframe(file_content, filename)

        # Normalize column names (strip whitespace)
        df.columns = [str(c).strip() for c in df.columns]

        # Map of normalized header -> actual (as-uploaded) header, so required
        # and optional column matching is case/whitespace/punctuation-insensitive
        # and independent of column order.
        header_by_normalized = {_normalize_header(h): h for h in df.columns}

        has_email = any(alias in header_by_normalized for alias in REQUIRED_EMAIL_ALIASES)
        has_name = any(alias in header_by_normalized for alias in REQUIRED_NAME_ALIASES) or (
            any(alias in header_by_normalized for alias in REQUIRED_FIRST_NAME_ALIASES)
            and any(alias in header_by_normalized for alias in REQUIRED_LAST_NAME_ALIASES)
        )
        missing = []
        if not has_name:
            missing.append("Name")
        if not has_email:
            missing.append("Email ID")
        if missing:
            raise MissingColumnsError(missing)

        email_col = next(
            header_by_normalized[alias] for alias in REQUIRED_EMAIL_ALIASES if alias in header_by_normalized
        )
        df = df.dropna(subset=[email_col])
        df[email_col] = df[email_col].astype(str).str.strip().str.lower()

        # Match unmapped spreadsheet columns to approved custom fields by a
        # normalized header comparison (case/whitespace/punctuation-insensitive).
        known_headers = {_normalize_header(h) for h in COLUMN_MAP}
        custom_columns: dict[str, str] = {}  # spreadsheet header -> CustomField name
        if custom_field_names:
            normalized_custom = {_normalize_header(name): name for name in custom_field_names}
            for header in df.columns:
                normalized = _normalize_header(header)
                if normalized in known_headers:
                    continue
                match = normalized_custom.get(normalized)
                if match:
                    custom_columns[header] = match

        rows = []
        for _, row in df.iterrows():
            data = {}
            for canonical_header, field in COLUMN_MAP.items():
                actual_header = header_by_normalized.get(_normalize_header(canonical_header))
                if actual_header is None:
                    continue
                value = row.get(actual_header)
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

    def preview_duplicates(self, db: Session, parsed: list[tuple[dict, dict]]) -> tuple[int, int]:
        """Row-level duplicate count against prospects already in the system
        (any prospect list) — returns (total_rows, duplicate_rows). Used to
        warn the user before an upload is committed, since a recipient row is
        shared across lists (a re-uploaded email upserts the same underlying
        Recipient rather than forking it), so a heavily-overlapping upload
        would otherwise silently merge into existing prospects instead of
        forming an obviously-new list."""
        emails = [data["email"] for data, _ in parsed]
        if not emails:
            return 0, 0
        existing_emails = {
            e for (e,) in db.query(Recipient.email).filter(Recipient.email.in_(set(emails))).all()
        }
        duplicate_count = sum(1 for e in emails if e in existing_emails)
        return len(emails), duplicate_count

    def import_recipients(
        self, db: Session, file_content: bytes, filename: str
    ) -> tuple[int, int, list[int]]:
        """Convenience one-shot import — parses the file and writes it
        straight to the database with no duplicate-confirmation step. The
        upload-excel endpoint instead calls parse_excel/preview_duplicates/
        import_parsed separately so it can pause for user confirmation
        between parsing and writing."""
        custom_fields = db.query(CustomField).all()
        field_ids_by_name = {f.name: f.id for f in custom_fields}
        parsed = self.parse_excel(file_content, filename, custom_field_names=set(field_ids_by_name))
        return self.import_parsed(db, parsed, field_ids_by_name)

    def import_parsed(
        self, db: Session, parsed: list[tuple[dict, dict]], field_ids_by_name: dict[str, int]
    ) -> tuple[int, int, list[int]]:
        """Write already-parsed rows (see parse_excel) to the database. A new
        email is inserted; an email that already exists is upserted — its
        profile fields (name, company, designation, etc.) are refreshed from
        this row instead of being left stale, since the same address is often
        re-uploaded later with corrected or additional details. Suppression
        status is never touched by an upsert; any active (non-overridden)
        suppression entry is only applied to newly-created rows, so a
        blacklisted address can't sneak back into sends without an explicit
        admin override.

        Returns (imported_count, updated_count, recipient_ids) where
        recipient_ids covers every recipient touched by this upload — new,
        updated, and unchanged — so callers (e.g. group assignment) can act
        on the full uploaded set, not just new rows."""
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
