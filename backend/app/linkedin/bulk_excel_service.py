"""Read LinkedIn URLs from uploaded spreadsheets and write enriched results."""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import get_settings
from app.linkedin.bulk_models import ITEM_SUCCESS
from app.linkedin.validator import is_linkedin_in_profile_url, normalize_profile_url, validate_profile_url
from app.services.excel_service import SUPPORTED_EXTENSIONS, _normalize_header, _read_dataframe

logger = logging.getLogger(__name__)

LINKEDIN_IN_RE = re.compile(
    r"https?://(?:www\.)?linkedin\.com/in/[^/?#\s\"']+",
    re.I,
)

URL_COLUMN_ALIASES = {
    "linkedinurl",
    "linkedin",
    "profileurl",
    "url",
    "link",
    "linkedinprofileurl",
    "linkedinprofile",
    "linkedinprofilelink",
    "linkedinlink",
    "personlinkedinurl",
    "personlinkedin",
}

OUTPUT_COLUMNS = (
    "LinkedIn URL",
    "Name",
    "Headline",
    "Company",
    "Job Title",
    "Location",
    "Summary",
    "Followers",
    "Connections",
    "Image",
    "Status",
    "Error",
)

OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"


def _max_bulk_urls() -> int:
    return max(get_settings().max_bulk_urls, 1)


class BulkExcelError(ValueError):
    """User-facing bulk Excel parse/validation error."""


class BulkExcelService:
    def read_upload(self, file_content: bytes, filename: str) -> pd.DataFrame:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise BulkExcelError(
                f"Unsupported file type '{suffix or 'unknown'}'. Supported: {supported}"
            )
        try:
            return _read_dataframe(file_content, filename)
        except ValueError as exc:
            raise BulkExcelError(str(exc)) from exc

    def extract_url_rows(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Return one dict per spreadsheet row that has a URL (including duplicates)."""
        url_col = self._find_url_column(df)
        rows: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        columns = [str(c) for c in df.columns]

        for pos, (idx, series) in enumerate(df.iterrows()):
            raw = self._url_from_row(series, url_col)
            extra = {}
            for col in columns:
                extra[col] = self._cell(series[col] if col in series.index else None)
            if not raw:
                rows.append(
                    {
                        "row_index": int(idx) if str(idx).isdigit() or isinstance(idx, int) else pos,
                        "source_row_number": pos + 1,
                        "raw_url": "",
                        "normalized_url": "",
                        "is_valid": False,
                        "is_duplicate": False,
                        "error": "No LinkedIn profile URL on this row",
                        "source_row_json": extra,
                        "input_columns": columns,
                    }
                )
                continue
            error = None
            is_valid = True
            try:
                normalized = validate_profile_url(raw)
            except ValueError as exc:
                is_valid = False
                normalized = normalize_profile_url(raw) if is_linkedin_in_profile_url(raw) else ""
                error = str(exc)
            duplicate_of_row = seen.get(normalized) if normalized else None
            if normalized and normalized not in seen:
                seen[normalized] = pos
            rows.append(
                {
                    "row_index": int(idx) if str(idx).isdigit() or isinstance(idx, int) else pos,
                    "source_row_number": pos + 1,
                    "raw_url": raw,
                    "normalized_url": normalized,
                    "is_valid": is_valid,
                    "is_duplicate": duplicate_of_row is not None,
                    "error": error,
                    "source_row_json": extra,
                    "input_columns": columns,
                }
            )

        if not any(r.get("normalized_url") or r.get("raw_url") for r in rows):
            raise BulkExcelError(
                "No LinkedIn profile URLs found. Add a column like 'LinkedIn URL' "
                "with links such as https://www.linkedin.com/in/username/"
            )
        max_urls = _max_bulk_urls()
        if len(rows) > max_urls:
            raise BulkExcelError(
                f"Too many URLs ({len(rows)}). Maximum allowed per upload is {max_urls}."
            )
        return rows

    def input_columns(self, df: pd.DataFrame) -> list[str]:
        return [str(c) for c in df.columns]

    def build_result_workbook(
        self,
        *,
        job_id: str,
        url_rows: list[dict[str, Any]],
        results_by_url: dict[str, dict[str, Any]],
        processed_only: bool = False,
    ) -> tuple[bytes, str, str]:
        """Write profile rows to outputs/bulk_{job_id}.xlsx (overwritten on each save)."""
        rows_to_write = url_rows
        if processed_only:
            rows_to_write = [
                entry
                for entry in url_rows
                if entry["normalized_url"] in results_by_url
            ]

        out_rows: list[dict[str, Any]] = []
        for entry in rows_to_write:
            url = entry["normalized_url"]
            result = results_by_url.get(url, {})
            data = result.get("data") or {}
            status = result.get("status", "pending" if not processed_only else "failed")
            error = result.get("error") or ""

            out_rows.append(
                {
                    "LinkedIn URL": url,
                    "Name": self._cell(data.get("name")),
                    "Headline": self._cell(data.get("headline")),
                    "Company": self._cell(data.get("company")),
                    "Job Title": self._cell(data.get("job_title")),
                    "Location": self._cell(data.get("location")),
                    "Summary": self._cell(data.get("summary")),
                    "Followers": data.get("followers") if data.get("followers") is not None else "",
                    "Connections": data.get("connections") if data.get("connections") is not None else "",
                    "Image": self._cell(data.get("image")),
                    "Status": status,
                    "Error": error or None,
                }
            )

        result_df = pd.DataFrame(out_rows, columns=list(OUTPUT_COLUMNS))
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            result_df.to_excel(writer, index=False, sheet_name="Profiles")

            # Style rows: mark any profile that wasn't extracted (`status != "ok"`)
            # as red so users can immediately see which URLs still need retry.
            from openpyxl.styles import Font, PatternFill

            ws = writer.sheets.get("Profiles")
            if ws is not None:
                red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                red_font = Font(color="9C0006")

                # Excel rows start at 1; header is at row=1, first data row is row=2.
                for i, out in enumerate(out_rows):
                    excel_row = i + 2
                    status = str(out.get("Status") or "").strip().lower()
                    if status != "ok":
                        # Color the full row (all columns) red.
                        for excel_col in range(1, len(OUTPUT_COLUMNS) + 1):
                            cell = ws.cell(row=excel_row, column=excel_col)
                            cell.fill = red_fill
                            cell.font = red_font

        content = buffer.getvalue()
        filename = self.job_filename(job_id)
        relative = f"outputs/{filename}"

        try:
            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            (OUTPUTS_DIR / filename).write_bytes(content)
            logger.info(
                "Saved bulk LinkedIn Excel to outputs/%s (%s rows, partial=%s)",
                filename,
                len(out_rows),
                processed_only,
            )
        except OSError:
            logger.exception("Could not save bulk LinkedIn Excel to disk")

        return content, filename, relative

    def build_result_workbook_from_items(
        self,
        *,
        job_id: str,
        items: list[Any],
        input_columns: list[str],
    ) -> tuple[bytes, str, str]:
        from app.linkedin.verification import original_fields

        # Exact download columns: 6 uploaded + 8 extracted/match.
        # input_columns kept for caller compatibility; extra upload cols are not exported.
        _ = input_columns
        columns = [
            "Original Name",
            "Original Email",
            "Original LinkedIn URL",
            "Original Designation",
            "Original Company",
            "Original Location",
            "Extracted Name",
            "Extracted Designation",
            "Extracted Company",
            "Extracted Location",
            "Extracted Headline",
            "Company Match",
            "Location Match",
            "Verification Status",
        ]
        def _match_label(value: Any) -> str:
            if value is True:
                return "true"
            if value is False:
                return "false"
            return ""

        out_rows: list[dict[str, Any]] = []
        extraction_statuses: list[str] = []
        for item in items:
            source = item.source_row_json if isinstance(getattr(item, "source_row_json", None), dict) else {}
            originals = original_fields(source)
            extracted_company = getattr(item, "company", None)
            # If sheet had no company, show LinkedIn company so Original Company is filled.
            original_company = originals.get("company") or extracted_company
            row: dict[str, Any] = {
                "Original Name": originals.get("name"),
                "Original Email": originals.get("email"),
                "Original LinkedIn URL": getattr(item, "normalized_url", None)
                or getattr(item, "profile_url", None),
                "Original Designation": originals.get("designation"),
                "Original Company": original_company,
                "Original Location": originals.get("location"),
                "Extracted Name": getattr(item, "name", None),
                "Extracted Designation": getattr(item, "designation", None),
                "Extracted Company": extracted_company,
                "Extracted Location": getattr(item, "location", None),
                "Extracted Headline": getattr(item, "headline", None),
                "Company Match": _match_label(getattr(item, "company_match", None)),
                "Location Match": _match_label(getattr(item, "location_match", None)),
                "Verification Status": getattr(item, "verification_status", "") or "",
            }
            out_rows.append(row)
            extraction_statuses.append(str(getattr(item, "status", "") or "").strip().upper())

        from app.linkedin.conflict_service import serialize_audit_row

        audit_entries = []
        for item in items:
            for audit_row in list(getattr(item, "resolutions", None) or []):
                audit_entries.append(serialize_audit_row(audit_row, item))
        if not audit_entries:
            try:
                from app.database.connection import SessionLocal
                from app.linkedin.conflict_service import list_job_audit

                db = SessionLocal()
                try:
                    audit_entries = list_job_audit(db, job_id)
                finally:
                    db.close()
            except Exception:
                audit_entries = []

        result_df = pd.DataFrame(out_rows, columns=columns)
        audit_columns = [
            "When",
            "Who",
            "Email",
            "Sheet row",
            "Profile URL",
            "Field",
            "Action",
            "Uploaded (from)",
            "Extracted",
            "Chosen value",
            "Summary",
        ]
        audit_rows = [
            {
                "When": e.get("resolved_at"),
                "Who": e.get("actor"),
                "Email": e.get("resolved_by_email"),
                "Sheet row": e.get("source_row_number"),
                "Profile URL": e.get("url"),
                "Field": e.get("field"),
                "Action": e.get("resolution"),
                "Uploaded (from)": e.get("uploaded_value"),
                "Extracted": e.get("extracted_value"),
                "Chosen value": e.get("resolved_value"),
                "Summary": e.get("change_summary"),
            }
            for e in audit_entries
        ]
        audit_df = pd.DataFrame(audit_rows, columns=audit_columns)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            result_df.to_excel(writer, index=False, sheet_name="Profiles")
            audit_df.to_excel(writer, index=False, sheet_name="Audit log")
            from openpyxl.styles import Font, PatternFill

            ws = writer.sheets.get("Profiles")
            if ws is not None:
                red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                red_font = Font(color="9C0006")
                for i, status in enumerate(extraction_statuses):
                    excel_row = i + 2
                    if status and status != ITEM_SUCCESS and status != "OK":
                        for excel_col in range(1, len(columns) + 1):
                            cell = ws.cell(row=excel_row, column=excel_col)
                            cell.fill = red_fill
                            cell.font = red_font

        content = buffer.getvalue()
        filename = self.job_filename(job_id)
        relative = f"outputs/{filename}"
        try:
            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            (OUTPUTS_DIR / filename).write_bytes(content)
        except OSError:
            logger.exception("Could not save bulk LinkedIn Excel to disk")
        return content, filename, relative

    @staticmethod
    def job_filename(job_id: str) -> str:
        return f"bulk_{job_id}.xlsx"

    def resolve_safe_path(self, filename: str) -> Path | None:
        name = (filename or "").strip()
        if not name or "/" in name or "\\" in name or ".." in name:
            return None
        if not re.fullmatch(r"bulk_[0-9a-f-]{36}\.xlsx", name) and not re.fullmatch(
            r"bulk_profile_\d{8}_\d{6}\.xlsx", name
        ):
            return None
        path = (OUTPUTS_DIR / name).resolve()
        try:
            path.relative_to(OUTPUTS_DIR.resolve())
        except ValueError:
            return None
        if not path.is_file():
            return None
        return path

    def _find_url_column(self, df: pd.DataFrame) -> str | None:
        for col in df.columns:
            if _normalize_header(str(col)) in URL_COLUMN_ALIASES:
                return str(col)

        best_col: str | None = None
        best_count = 0
        for col in df.columns:
            count = sum(1 for v in df[col] if self._extract_url_from_text(v))
            if count > best_count:
                best_count = count
                best_col = str(col)
        return best_col if best_count > 0 else None

    def _url_from_row(self, series: pd.Series, url_col: str | None) -> str:
        if url_col and url_col in series.index:
            found = self._extract_url_from_text(series[url_col])
            if found:
                return found
        for value in series.values:
            found = self._extract_url_from_text(value)
            if found:
                return found
        return ""

    @staticmethod
    def _extract_url_from_text(value: Any) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        text = str(value).strip()
        if not text:
            return ""
        if is_linkedin_in_profile_url(text):
            return text
        match = LINKEDIN_IN_RE.search(text)
        return match.group(0) if match else ""

    @staticmethod
    def _cell(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() in {"none", "null", "n/a"}:
            return None
        return text


def refresh_job_result_excel(db: Session, job, *, excel_service: BulkExcelService | None = None) -> None:
    """Rebuild the verified Excel workbook from current job items and persist to S3."""
    from app.linkedin.bulk_models import BulkJobItemRow
    from app.linkedin.s3_persist import persist_verified_excel

    excel = excel_service or BulkExcelService()
    items = (
        db.query(BulkJobItemRow)
        .filter(BulkJobItemRow.job_id == job.id)
        .order_by(BulkJobItemRow.source_row_number.asc())
        .all()
    )
    content, filename, relative = excel.build_result_workbook_from_items(
        job_id=job.id,
        items=items,
        input_columns=list(job.input_columns or []),
    )
    job.result_file_path = relative
    job.excel_finalized = True
    persist_verified_excel(db, job=job, content=content, filename=filename)
