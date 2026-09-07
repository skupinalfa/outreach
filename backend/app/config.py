from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    database_url: str = Field(...)
    fernet_key: SecretStr = Field(...)
    session_secret: SecretStr = Field(...)

    @field_validator("fernet_key")
    @classmethod
    def _validate_fernet_key(cls, value: SecretStr) -> SecretStr:
        """Fail-fast at startup on an invalid Fernet key (Constitution IV).

        Without this, the app boots happily and only errors on the first `encrypt` call
        (e.g. saving a Hunter key), which surfaces as an opaque 500 in the UI.
        """
        try:
            Fernet(value.get_secret_value().encode())
        except Exception as exc:
            raise ValueError(
                "FERNET_KEY is not a valid Fernet key. Generate one with:\n"
                '  python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            ) from exc
        return value

    initial_master_password: SecretStr | None = None

    hunter_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    sender_display_name: str | None = None
    sender_email: str | None = None

    session_ttl_hours: int = 24 * 7
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cookie_secure: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
