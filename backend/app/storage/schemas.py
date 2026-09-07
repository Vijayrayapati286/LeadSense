"""API schemas for stored files / batch downloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StoredFileOut(BaseModel):
    id: int
    user_id: int | None = None
    batch_id: str
    file_type: str = Field(alias="type")
    original_filename: str = Field(alias="filename")
    s3_bucket: str | None = None
    s3_key: str | None = None
    mime_type: str | None = None
    file_size: int = 0
    status: str
    content_version: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"populate_by_name": True, "from_attributes": True}


class BatchFilesResponse(BaseModel):
    batch_id: str
    files: list[StoredFileOut]


class DownloadUrlResponse(BaseModel):
    download_url: str
    filename: str
    file_id: int | None = None
    expires_in: int = 3600
    reused: bool = False


class FileUploadResponse(BaseModel):
    file_id: int
    batch_id: str
    filename: str
    file_type: str
    status: str
    s3_key: str
    file_size: int
