from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    webhook_secret: str = ""
    mimir_endpoint: str = ""  # Prometheus: http://prometheus:9090, Mimir: http://mimir:9009/prometheus
    watch_namespaces: str = ""  # comma-separated list of namespaces, empty = all
    llm_provider: str = "anthropic"  # anthropic, openai, ollama
    llm_model: str = ""  # auto-detected if empty (claude-sonnet-4-20250514, gpt-4o, llama3, etc.)
    llm_api_key: str = ""
    llm_base_url: str = ""  # only for ollama/custom: http://ollama.local:11434/v1
    database_url: str = ""

    model_config = {"env_prefix": "KLARSICHT_"}

    @property
    def watch_namespace_list(self) -> list[str]:
        if not self.watch_namespaces:
            return []
        return [ns.strip() for ns in self.watch_namespaces.split(",") if ns.strip()]


settings = Settings()
