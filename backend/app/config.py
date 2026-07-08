"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Bulk Email Campaign Manager"
    debug: bool = True
    secret_key: str = "dev-secret-key-change-in-production"
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    database_url: str = "postgresql://postgres:postgres@localhost:5432/bulk_email_db"
    use_sqlite_fallback: bool = True

    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_tenant_id: str = "common"
    azure_redirect_uri: str = "http://localhost:8000/api/auth/callback"

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    aws_ses_sender_email: str = "noreply@example.com"
    use_mock_ses: bool = True
    test_email_override: str = "d.nikhileswar.reddy@gmail.com"

    groq_api_key: str = ""
    use_mock_groq: bool = True

    @property
    def azure_authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.azure_tenant_id}"

    @property
    def azure_scopes(self) -> list[str]:
        return ["User.Read"]

    @property
    def is_azure_configured(self) -> bool:
        return bool(self.azure_client_id and self.azure_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
