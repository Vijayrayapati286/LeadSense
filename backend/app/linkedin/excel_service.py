"""Excel export for LinkedIn Profile Extractor (isolated from Sales Nav)."""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = ("Full Name", "Company", "Designation", "About")
OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"


class LinkedInExcelService:
    """Generate profile workbooks with only the four allowed columns."""

    def build_workbook(
        self,
        profile: dict[str, Any],
        *,
        save_to_disk: bool = True,
    ) -> tuple[bytes, str, str]:
        """
        Returns (content_bytes, filename, relative_path).

        relative_path is like outputs/profile_YYYYMMDD_HHMMSS.xlsx for API clients.
        """
        row = {
            "Full Name": self._cell(profile.get("full_name")),
            "Company": self._cell(profile.get("company")),
            "Designation": self._cell(profile.get("job_title")),
            "About": self._cell(profile.get("about")),
        }
        df = pd.DataFrame([row], columns=list(OUTPUT_COLUMNS))
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Profile")
        content = buffer.getvalue()

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"profile_{stamp}.xlsx"
        relative = f"outputs/{filename}"

        if save_to_disk:
            try:
                OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
                path = OUTPUTS_DIR / filename
                path.write_bytes(content)
                logger.info("Saved LinkedIn profile Excel to %s", path)
            except OSError:
                logger.exception("Could not save LinkedIn profile Excel to disk")

        return content, filename, relative

    def resolve_safe_path(self, filename: str) -> Path | None:
        """Resolve a download filename under outputs/; reject path traversal."""
        name = (filename or "").strip()
        if not name or "/" in name or "\\" in name or ".." in name:
            return None
        if not re.fullmatch(r"profile_\d{8}_\d{6}\.xlsx", name):
            return None
        path = (OUTPUTS_DIR / name).resolve()
        try:
            path.relative_to(OUTPUTS_DIR.resolve())
        except ValueError:
            return None
        if not path.is_file():
            return None
        return path

    @staticmethod
    def _cell(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() in {"none", "null", "n/a"}:
            return None
        return text
