"""Reusable Amazon S3 client with local mock fallback (mirrors SES mock pattern)."""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path
from typing import Any
from app.config import get_settings
from app.storage.exceptions import S3StorageError

logger = logging.getLogger(__name__)

_MOCK_ROOT = Path(__file__).resolve().parents[2] / "outputs" / "s3_mock"


class S3Service:
    """Upload / download / presign / delete against S3 or a local mock store."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any | None = None
        self._lock = threading.Lock()

    @property
    def bucket(self) -> str:
        return (self.settings.s3_bucket_name or "").strip()

    @property
    def use_mock(self) -> bool:
        if self.settings.use_mock_s3:
            return True
        # No bucket configured → mock so local/dev still works.
        return not bool(self.bucket)

    def _get_client(self):
        if self.use_mock:
            return None
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                import boto3
                from botocore.client import Config

                kwargs: dict[str, Any] = {
                    "region_name": self.settings.aws_region or "ap-south-1",
                    "config": Config(signature_version="s3v4"),
                }
                access = (self.settings.aws_access_key_id or "").strip()
                secret = (self.settings.aws_secret_access_key or "").strip()
                # Prefer explicit keys when set; otherwise IAM role / env / instance profile.
                if access and secret:
                    kwargs["aws_access_key_id"] = access
                    kwargs["aws_secret_access_key"] = secret
                self._client = boto3.client("s3", **kwargs)
            except Exception as exc:
                logger.exception("Failed to initialize S3 client")
                raise S3StorageError(f"Invalid or unavailable AWS credentials: {exc}") from exc
            return self._client

    def _mock_path(self, key: str) -> Path:
        safe = key.replace("\\", "/").lstrip("/")
        parts = [p for p in safe.split("/") if p]
        if not parts or any(p == ".." for p in parts):
            raise S3StorageError("Invalid S3 key")
        path = (_MOCK_ROOT.joinpath(*parts)).resolve()
        try:
            path.relative_to(_MOCK_ROOT.resolve())
        except ValueError as exc:
            raise S3StorageError("Invalid S3 key") from exc
        return path

    def upload_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        if not key or ".." in key:
            raise S3StorageError("Invalid S3 key")
        bucket = self.bucket or "mock-local-bucket"
        try:
            if self.use_mock:
                path = self._mock_path(key)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                meta_path = path.with_suffix(path.suffix + ".meta")
                meta_path.write_text(
                    (content_type or "application/octet-stream") + "\n",
                    encoding="utf-8",
                )
                logger.info("Mock S3 upload key=%s bytes=%s", key, len(data))
                return bucket

            client = self._get_client()
            extra: dict[str, Any] = {}
            if content_type:
                extra["ContentType"] = content_type
            if metadata:
                extra["Metadata"] = {str(k): str(v)[:256] for k, v in metadata.items()}
            client.put_object(Bucket=bucket, Key=key, Body=data, **extra)
            logger.info("S3 upload ok bucket=%s key=%s bytes=%s", bucket, key, len(data))
            return bucket
        except S3StorageError:
            raise
        except Exception as exc:
            logger.exception("S3 upload failed key=%s", key)
            raise S3StorageError(f"S3 upload failed: {exc}") from exc

    def upload_file(
        self,
        *,
        key: str,
        file_path: str | Path,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        path = Path(file_path)
        if not path.is_file():
            raise S3StorageError(f"Local file not found: {file_path}")
        return self.upload_bytes(
            key=key,
            data=path.read_bytes(),
            content_type=content_type,
            metadata=metadata,
        )

    def download_file(self, *, key: str, dest_path: str | Path) -> Path:
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = self.download_bytes(key=key)
        dest.write_bytes(data)
        return dest

    def download_bytes(self, *, key: str) -> bytes:
        if not key:
            raise S3StorageError("Invalid S3 key")
        try:
            if self.use_mock:
                path = self._mock_path(key)
                if not path.is_file():
                    raise S3StorageError("File not found in S3")
                return path.read_bytes()

            client = self._get_client()
            resp = client.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read()
        except S3StorageError:
            raise
        except Exception as exc:
            logger.exception("S3 download failed key=%s", key)
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise S3StorageError("File not found in S3") from exc
            raise S3StorageError(f"S3 download failed: {exc}") from exc

    def generate_presigned_download_url(
        self,
        *,
        key: str,
        expires_in: int | None = None,
        filename: str | None = None,
        mock_content_url: str | None = None,
    ) -> str:
        """Return a temporary GET URL. In mock mode, returns ``mock_content_url``."""
        expires = expires_in or int(getattr(self.settings, "s3_presign_expires_seconds", 3600) or 3600)
        if self.use_mock:
            if not mock_content_url:
                raise S3StorageError("Mock S3 requires mock_content_url for downloads")
            return mock_content_url
        try:
            client = self._get_client()
            params: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
            if filename:
                safe = filename.replace('"', "")
                params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'
            url = client.generate_presigned_url(
                ClientMethod="get_object",
                Params=params,
                ExpiresIn=expires,
            )
            return url
        except Exception as exc:
            logger.exception("Presigned URL generation failed key=%s", key)
            raise S3StorageError(f"Failed to generate download URL: {exc}") from exc

    def delete_file(self, *, key: str) -> None:
        if not key:
            return
        try:
            if self.use_mock:
                path = self._mock_path(key)
                if path.is_file():
                    path.unlink()
                meta = path.with_suffix(path.suffix + ".meta")
                if meta.is_file():
                    meta.unlink()
                return
            client = self._get_client()
            client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            logger.exception("S3 delete failed key=%s", key)
            raise S3StorageError(f"S3 delete failed: {exc}") from exc

    def file_exists(self, *, key: str) -> bool:
        if not key:
            return False
        try:
            if self.use_mock:
                return self._mock_path(key).is_file()
            client = self._get_client()
            client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchKey", "NotFound", "405"}:
                return False
            # botocore ClientError 404
            if getattr(exc, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            logger.warning("S3 exists check failed key=%s err=%s", key, exc)
            return False

    def clear_mock_store(self) -> None:
        if _MOCK_ROOT.exists():
            shutil.rmtree(_MOCK_ROOT, ignore_errors=True)


_s3_singleton: S3Service | None = None


def get_s3_service() -> S3Service:
    global _s3_singleton
    if _s3_singleton is None:
        _s3_singleton = S3Service()
    return _s3_singleton


def reset_s3_service() -> None:
    """Test helper — drop the singleton so settings changes take effect."""
    global _s3_singleton
    _s3_singleton = None
