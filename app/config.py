from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    webhook_secret: str = ""
    mimir_endpoint: str = ""  # Prometheus: http://prometheus:9090, Mimir: http://mimir:9009/prometheus
    watch_namespaces: str = ""  # comma-separated list of namespaces, empty = all
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    database_url: str = ""

    model_config = {"env_prefix": "KLARSICHT_"}

    @property
    def watch_namespace_list(self) -> list[str]:
        if not self.watch_namespaces:
            return []
        return [ns.strip() for ns in self.watch_namespaces.split(",") if ns.strip()]


settings = Settings()
