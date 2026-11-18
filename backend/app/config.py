from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str | None = None
    postgres_host: str | None = None
    postgres_db: str = "oem"
    postgres_user: str = "oem"
    postgres_password: str | None = None
    minifi_probe_agent_id: str = ""
    minifi_flow_agent_id: str = ""

    def database_connection(self) -> str | URL:
        if self.database_url:
            return self.database_url
        if self.postgres_host:
            return URL.create(
                "postgresql+psycopg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                database=self.postgres_db,
            )
        return "sqlite:///./oem-dev.db"


settings = Settings()
