from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    webhook_secret: str = ""
    mimir_endpoint: str = ""  # Prometheus: http://prometheus:9090, Mimir: http://mimir:9009/prometheus
    watch_namespaces: list[str] = []
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    database_url: str = "postgresql://klarsicht:klarsicht@localhost:5432/klarsicht"

    model_config = {"env_prefix": "KLARSICHT_"}


settings = Settings()
