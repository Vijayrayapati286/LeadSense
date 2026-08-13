"""Build Sales Navigator contact Excel workbooks (.xlsx).

Separate from app.services.excel_service (prospect uploads) so existing
upload/export behavior stays untouched.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = ("Name", "About", "Company")
OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"


class SalesNavExcelService:
    """Generate and optionally persist Sales Navigator contact spreadsheets."""

    def build_workbook(
        self,
        contacts: list[dict[str, Any]],
        *,
        save_to_disk: bool = True,
    ) -> tuple[bytes, str]:
        rows = [
            {
                "Name": self._cell(c.get("name")),
                "About": self._cell(c.get("about")),
                "Company": self._cell(c.get("company")),
            }
            for c in contacts
        ]
        df = pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS))
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Contacts")
        content = buffer.getvalue()

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"salesnav_contacts_{stamp}.xlsx"

        if save_to_disk:
            try:
                OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
                path = OUTPUTS_DIR / filename
                path.write_bytes(content)
                logger.info("Saved Sales Navigator Excel to %s (%s rows)", path, len(rows))
            except OSError:
                logger.exception("Could not save Sales Navigator Excel to disk")

        return content, filename

    @staticmethod
    def _cell(value: Any) -> str | None:
        """Empty / missing fields become null in the workbook."""
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() in {"none", "null", "n/a"}:
            return None
        return text
