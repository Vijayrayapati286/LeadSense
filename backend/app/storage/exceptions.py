"""Storage / S3 errors."""


class StorageError(Exception):
    """Base storage failure."""


class S3StorageError(StorageError):
    """AWS S3 operation failed."""


class FileValidationError(StorageError):
    """Uploaded file failed validation."""


class FileNotFoundStorageError(StorageError):
    """Requested stored file does not exist."""


class UnauthorizedFileAccess(StorageError):
    """Caller does not own the batch/file."""
