from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    webhook_secret: str = ""
    webhook_basic_auth_user: str = ""  # optional HTTP Basic Auth on /alert
    webhook_basic_auth_password: str = ""
    mimir_endpoint: str = ""  # Prometheus: http://prometheus:9090, Mimir: http://mimir:9009/prometheus
    watch_namespaces: str = ""  # comma-separated list of namespaces, empty = all
    llm_provider: str = "anthropic"  # anthropic, openai, ollama, watsonx
    llm_model: str = ""  # auto-detected if empty (claude-sonnet-4-20250514, gpt-4o, llama3, granite-3-8b, etc.)
    llm_api_key: str = ""
    llm_base_url: str = ""  # ollama/custom/watsonx: http://ollama:11434/v1 or internal watsonx URL
    watsonx_project_id: str = ""  # watsonx only: IBM project ID
    llm_profile: str = "auto"  # auto, full, compact — compact for small models (<30B)
    llm_max_tool_calls: int = 0  # 0 = auto (full: 20, compact: 8)
    database_url: str = ""

    # GitLab integration
    gitlab_url: str = ""  # https://gitlab.com or self-hosted
    gitlab_token: str = ""  # Personal/Project Access Token (read_api scope)
    gitlab_project: str = ""  # project path e.g. "outcept/klarsicht" or numeric ID

    # Notifications
    teams_webhook_url: str = ""  # Microsoft Teams Incoming Webhook URL
    slack_webhook_url: str = ""  # Slack Incoming Webhook URL
    discord_webhook_url: str = ""  # Discord Webhook URL

    # Dashboard URL (for links in notifications)
    dashboard_url: str = ""  # e.g. https://klarsicht.dev

    # Peer instances for alert fan-out and comparison
    peer_webhook_urls: str = ""  # comma-separated: http://klarsicht-gamma-agent.klarsicht-gamma.svc:8000

    # OIDC Authentication
    auth_enabled: bool = False
    oidc_issuer_url: str = ""  # https://login.microsoftonline.com/{tenant}/v2.0
    oidc_client_id: str = ""
    oidc_client_secret: str = ""  # optional, for confidential clients
    oidc_scopes: str = "openid profile email"
    # Claim mapping: JSON {"department": "team"} — maps OIDC claim → alert label
    auth_claim_mapping: str = ""
    # Team mappings: JSON {"XY-Z": ["XY-Z1", "XY-Z2"]} — expand team to multiple tag values
    auth_team_mappings: str = ""
    # Admin teams: comma-separated — these teams see all alerts unfiltered
    auth_admin_teams: str = ""

    # Confluence integration (BHB / operations handbooks)
    confluence_url: str = ""  # https://company.atlassian.net/wiki or https://confluence.company.com
    confluence_token: str = ""  # API token (Cloud) or PAT (Server/DC)
    confluence_user: str = ""  # Cloud: email address, Server: leave empty for PAT
    confluence_spaces: str = ""  # comma-separated space keys: "OPS,INFRA,PLATFORM"

    # Multi-cluster mode
    mode: str = "standalone"  # standalone, backend, agent
    cluster_name: str = ""  # agent mode: identifies this cluster (e.g. "prod-eu-1")
    join_token: str = ""  # shared secret — agent uses it to register with backend
    backend_url: str = ""  # agent mode: URL of the central backend (e.g. http://backend:8000)

    model_config = {"env_prefix": "KLARSICHT_"}

    @property
    def watch_namespace_list(self) -> list[str]:
        if not self.watch_namespaces:
            return []
        return [ns.strip() for ns in self.watch_namespaces.split(",") if ns.strip()]

    @property
    def peer_url_list(self) -> list[str]:
        if not self.peer_webhook_urls:
            return []
        return [u.strip() for u in self.peer_webhook_urls.split(",") if u.strip()]

    @property
    def confluence_space_list(self) -> list[str]:
        if not self.confluence_spaces:
            return []
        return [s.strip() for s in self.confluence_spaces.split(",") if s.strip()]

    @property
    def is_backend(self) -> bool:
        return self.mode == "backend"

    @property
    def is_agent(self) -> bool:
        return self.mode == "agent"


settings = Settings()
