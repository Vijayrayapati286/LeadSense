"""Excel export for Profile Extractor (isolated)."""

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


class ProfileExcelService:
    def build_workbook(self, profile: dict[str, Any]) -> tuple[bytes, str, Path]:
        row = {
            "Full Name": self._cell(profile.get("full_name")),
            "Company": self._cell(profile.get("company")),
            "Designation": self._cell(profile.get("designation")),
            "About": self._cell(profile.get("about")),
        }
        df = pd.DataFrame([row], columns=list(OUTPUT_COLUMNS))
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Profile")
        content = buffer.getvalue()

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"linkedin_profile_{stamp}.xlsx"
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUTS_DIR / filename
        path.write_bytes(content)
        logger.info("Wrote profile Excel %s", filename)
        return content, filename, path

    def resolve_safe_path(self, filename: str) -> Path | None:
        name = (filename or "").strip()
        if not name or "/" in name or "\\" in name or ".." in name:
            return None
        if not re.fullmatch(r"linkedin_profile_\d{8}_\d{6}\.xlsx", name):
            return None
        path = (OUTPUTS_DIR / name).resolve()
        try:
            path.relative_to(OUTPUTS_DIR.resolve())
        except ValueError:
            return None
        return path if path.is_file() else None

    def delete_file(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete temp Excel %s", path)

    @staticmethod
    def _cell(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() in {"none", "null", "n/a"}:
            return None
        return text
