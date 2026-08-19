"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pydantic import Field
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
    frontend_url: str = "http://localhost:5180"
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
    # Domain used for the personalized From address (local part swapped for
    # the sending rep's, e.g. vijay.rayapati@mail.feuji.com) — see
    # SESService._build_source. Deliberately a distinct, dedicated
    # SES-verified domain rather than the org's real mail domain (from
    # aws_ses_sender_email), so bulk sends don't affect that domain's sender
    # reputation/DMARC alignment. Falls back to aws_ses_sender_email's own
    # domain when unset.
    aws_ses_sending_domain: str = ""
    use_mock_ses: bool = True
    test_email_override: str = "d.nikhileswar.reddy@gmail.com"

    # SES-specific credentials, for when the sending identity (e.g.
    # mail.feuji.com) is verified in a different AWS account than the one
    # the compute's IAM role belongs to — the role has no access to another
    # account's SES identities regardless of its permissions. Falls back to
    # AWS_ACCESS_KEY_ID/SECRET (then the instance role) when left blank, so
    # same-account setups are unaffected.
    ses_aws_access_key_id: str = ""
    ses_aws_secret_access_key: str = ""
    ses_region: str = ""

    groq_api_key: str = ""
    use_mock_groq: bool = True

    # Soft bounces (transient delivery failures) are retried; after this many
    # soft bounces for the same address, it gets suppressed too.
    soft_bounce_threshold: int = 3

    # JSON object mapping each core_users.CORE_USERS email to its password,
    # e.g. {"name@feuji.com": "..."}. Kept out of source (core_users.py has
    # no passwords) since that file is committed to a shared repo.
    core_user_passwords_json: str = Field("{}", validation_alias="CORE_USER_PASSWORDS")

    # LinkedIn Sales Navigator extraction (Apify + Playwright session check)
    apify_token: str = ""
    apify_actor_id: str = ""
    # Optional actor for /in/ profile scrape (LinkedIn Profile Extractor fallback).
    # When empty, profile Apify fallback uses apify_actor_id.
    apify_profile_actor_id: str = ""
    linkedin_li_at: str = ""
    # Optional full cookie-array JSON from a "Copy Cookies" browser extension.
    # When set, preferred over building a single li_at cookie for Apify.
    linkedin_cookies_json: str = ""

    # Bulk LinkedIn extract: concurrent Apify batch processing
    max_concurrent_apify_runs: int = Field(10, validation_alias="MAX_CONCURRENT_APIFY_RUNS")
    apify_batch_size: int = Field(10, validation_alias="APIFY_BATCH_SIZE")
    # Max extraction attempts per URL (attempt 1 + retries). Success stops immediately.
    apify_max_retries: int = Field(5, validation_alias="APIFY_MAX_RETRIES")
    max_bulk_urls: int = Field(250, validation_alias="MAX_BULK_URLS")
    bulk_retry_base_delay_seconds: float = Field(5.0, validation_alias="BULK_RETRY_BASE_DELAY_SECONDS")
    bulk_retry_backoff_multiplier: float = Field(2.0, validation_alias="BULK_RETRY_BACKOFF_MULTIPLIER")
    bulk_stale_processing_seconds: int = Field(900, validation_alias="BULK_STALE_PROCESSING_SECONDS")
    # Comma-separated substrings; matching errors skip further retries.
    bulk_non_retryable_errors: str = Field(
        "invalid url,malformed,permanently unavailable,profile not found,not a linkedin",
        validation_alias="BULK_NON_RETRYABLE_ERRORS",
    )

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
