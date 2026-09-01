"""S3 object-key helpers — never trust user-provided keys."""

from __future__ import annotations

import re
import uuid
from pathlib import PurePosixPath


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(filename: str, *, default: str = "file.bin") -> str:
    name = (filename or "").strip().replace("\\", "/")
    base = PurePosixPath(name).name
    if not base or base in {".", ".."}:
        return default
    cleaned = _UNSAFE.sub("_", base).strip("._")
    if not cleaned:
        return default
    return cleaned[:200]


def build_upload_key(*, user_id: int | str, batch_id: str, filename: str) -> str:
    safe = sanitize_filename(filename, default="input.xlsx")
    unique = uuid.uuid4().hex[:12]
    return f"uploads/{user_id}/{batch_id}/original/{unique}_{safe}"


def build_verified_key(*, user_id: int | str, batch_id: str, filename: str = "verified.xlsx") -> str:
    safe = sanitize_filename(filename, default="verified.xlsx")
    return f"verified/{user_id}/{batch_id}/{safe}"


def build_export_key(*, user_id: int | str, batch_id: str, filename: str = "final-result.xlsx") -> str:
    safe = sanitize_filename(filename, default="final-result.xlsx")
    unique = uuid.uuid4().hex[:12]
    return f"exports/{user_id}/{batch_id}/{unique}_{safe}"


def build_history_key(*, user_id: int | str, batch_id: str, filename: str) -> str:
    safe = sanitize_filename(filename, default="artifact.bin")
    unique = uuid.uuid4().hex[:12]
    return f"history/{user_id}/{batch_id}/{unique}_{safe}"
