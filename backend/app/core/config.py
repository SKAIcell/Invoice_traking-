
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Invoice Tracking"
    app_version: str = "1.0.0"

    # Database and application security
    database_url: str
    secret_key: str

    # SMTP email configuration
    smtp_host: str = "smtp.office365.com"
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str

    email_sender: str
    it_head_email: str | None = None
    accounts_email: str | None = None

    # Outlook actionable message configuration
    public_backend_url: str | None = None
    actionable_message_originator: str | None = None

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
