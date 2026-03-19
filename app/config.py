from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    webhook_secret: str = ""
    mimir_endpoint: str = ""  # Prometheus: http://prometheus:9090, Mimir: http://mimir:9009/prometheus
    watch_namespaces: list[str] = []
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    database_url: str = ""

    model_config = {"env_prefix": "KLARSICHT_"}

    @field_validator("watch_namespaces", mode="before")
    @classmethod
    def parse_namespaces(cls, v):
        if isinstance(v, str):
            return [ns.strip() for ns in v.split(",") if ns.strip()]
        return v


settings = Settings()
