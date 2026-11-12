from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "sqlite:///./electrostock.db"
    jwt_secret: str = "local-only-change-this-secret-before-deploying"
    jwt_access_minutes: int = 15
    cors_origins: str = "http://127.0.0.1:4200"
    cookie_secure: bool = False
    create_schema: bool = True
    scheduler_enabled: bool = True

    @model_validator(mode="after")
    def require_production_secret(self) -> "Settings":
        if self.environment.lower() not in {"local", "test"} and (
            len(self.jwt_secret) < 32 or self.jwt_secret.startswith("local-only")
        ):
            raise ValueError("JWT_SECRET debe tener al menos 32 caracteres fuera del entorno local")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
