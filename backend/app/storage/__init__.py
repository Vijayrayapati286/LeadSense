"""S3-backed file storage: metadata in PostgreSQL, binaries in S3 (or local mock)."""

from app.storage.s3_service import S3Service, get_s3_service

__all__ = ["S3Service", "get_s3_service"]
