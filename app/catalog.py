"""Service catalog — maps K8s deployments to Confluence BHB pages.

The catalog is populated by:
1. Confluence sync (crawls spaces, discovers BHBs)
2. K8s env-var parsing (auto-discovers dependencies)
3. LLM bootstrap matching (fuzzy-matches deployment names to BHB titles)

The agent queries this at investigation time via lookup_service / search_runbook tools.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# --- DB Schema ---

CATALOG_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS service_catalog (
    name            TEXT NOT NULL,
    namespace       TEXT NOT NULL DEFAULT '',
    cluster         TEXT NOT NULL DEFAULT '',
    team            TEXT DEFAULT '',
    tech            TEXT DEFAULT '',
    dependencies    JSONB DEFAULT '[]',
    health_path     TEXT DEFAULT '',
    bhb_page_id     TEXT DEFAULT '',
    bhb_title       TEXT DEFAULT '',
    bhb_number      TEXT DEFAULT '',
    bhb_sections    JSONB DEFAULT '{}',
    match_confidence TEXT DEFAULT '',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (name, namespace, cluster)
);

CREATE TABLE IF NOT EXISTS bhb_index (
    page_id         TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    space           TEXT NOT NULL,
    bhb_number      TEXT NOT NULL,
    service_name    TEXT NOT NULL,
    sections        JSONB DEFAULT '{}',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def init_catalog_schema() -> None:
    """Create catalog tables if they don't exist."""
    from app.db import _get_pool
    pool = _get_pool()
    await pool.execute(CATALOG_SCHEMA_SQL)
    logger.info("Service catalog schema initialized")


# --- Confluence Sync ---


async def sync_confluence() -> dict[str, Any]:
    """Crawl configured Confluence spaces and index all BHBs.

    Returns summary of what was found/updated.
    """
    from app.tools.confluence import list_bhb_pages
    from app.db import _get_pool

    pool = _get_pool()
    bhbs = list_bhb_pages()

    upserted = 0
    for bhb in bhbs:
        await pool.execute(
            """
            INSERT INTO bhb_index (page_id, title, space, bhb_number, service_name, sections, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, now())
            ON CONFLICT (page_id) DO UPDATE SET
                title = EXCLUDED.title,
                service_name = EXCLUDED.service_name,
                sections = EXCLUDED.sections,
                updated_at = now()
            """,
            bhb["id"],
            bhb["title"],
            bhb["space"],
            bhb["bhb_number"],
            bhb["service_name"],
            json.dumps(bhb.get("sections", {})),
        )
        upserted += 1

    logger.info("Confluence sync complete: %d BHBs indexed", upserted)
    return {"bhbs_indexed": upserted, "spaces": settings.confluence_space_list}


# --- K8s Env-Var Discovery ---

# Patterns that indicate a dependency in env var names/values
_DEP_PATTERNS = [
    (re.compile(r"postgres|DATABASE_URL|PGHOST", re.I), "postgres"),
    (re.compile(r"REDIS|CACHE_URL", re.I), "redis"),
    (re.compile(r"MONGO|MONGODB", re.I), "mongodb"),
    (re.compile(r"MARIADB|MYSQL", re.I), "mariadb"),
    (re.compile(r"RABBIT|AMQP", re.I), "rabbitmq"),
    (re.compile(r"KAFKA|BOOTSTRAP_SERVERS", re.I), "kafka"),
    (re.compile(r"ELASTICSEARCH|ELASTIC_URL|OPENSEARCH", re.I), "elasticsearch"),
    (re.compile(r"MINIO|S3_ENDPOINT", re.I), "s3"),
]

_HOST_PORT_RE = re.compile(r"(?:(?:tcp|https?|amqps?|redis|mongodb(?:\+srv)?|postgresql)://)?([a-zA-Z0-9._-]+):(\d+)")

# Tech detection from container image names
_TECH_PATTERNS = [
    (re.compile(r"openjdk|spring|maven|gradle|jdk", re.I), "java"),
    (re.compile(r"dotnet|aspnet|csharp", re.I), "dotnet"),
    (re.compile(r"python|uvicorn|gunicorn|django|flask|fastapi", re.I), "python"),
    (re.compile(r"node|next|nuxt|angular|vue|react|bun", re.I), "node"),
    (re.compile(r"golang|go\d", re.I), "go"),
    (re.compile(r"ruby|rails", re.I), "ruby"),
    (re.compile(r"php|laravel", re.I), "php"),
    (re.compile(r"nginx|envoy|haproxy|traefik", re.I), "proxy"),
    (re.compile(r"rabbitmq", re.I), "rabbitmq"),
    (re.compile(r"postgres", re.I), "postgres"),
    (re.compile(r"redis", re.I), "redis"),
    (re.compile(r"mongo", re.I), "mongodb"),
]


def detect_tech(image: str) -> str:
    """Guess the tech stack from a container image name."""
    for pattern, tech in _TECH_PATTERNS:
        if pattern.search(image):
            return tech
    return ""


def parse_dependencies_from_env(env_vars: dict[str, str]) -> list[str]:
    """Extract dependency endpoints from env var names and values."""
    deps: list[str] = []
    seen: set[str] = set()

    for name, value in env_vars.items():
        combined = f"{name}={value}"
        for pattern, dep_type in _DEP_PATTERNS:
            if pattern.search(combined):
                # Try to extract host:port from the value
                match = _HOST_PORT_RE.search(value)
                if match:
                    endpoint = f"{match.group(1)}:{match.group(2)}"
                    if endpoint not in seen:
                        deps.append(endpoint)
                        seen.add(endpoint)
                elif dep_type not in seen:
                    deps.append(dep_type)
                    seen.add(dep_type)
    return deps


async def sync_k8s_deployments(cluster: str = "") -> dict[str, Any]:
    """Scan K8s deployments and upsert into service_catalog.

    Extracts: name, namespace, team label, tech from image,
    dependencies from env vars.
    """
    from app.db import _get_pool
    from app.tools.k8s import _apps_v1

    pool = _get_pool()
    cluster_name = cluster or settings.cluster_name or "default"

    api = _apps_v1()
    if settings.watch_namespace_list:
        all_deps = []
        for ns in settings.watch_namespace_list:
            result = api.list_namespaced_deployment(namespace=ns)
            all_deps.extend(result.items)
    else:
        result = api.list_deployment_for_all_namespaces()
        all_deps = result.items

    upserted = 0
    for dep in all_deps:
        name = dep.metadata.name
        namespace = dep.metadata.namespace
        labels = dep.metadata.labels or {}
        team = labels.get("team", labels.get("app.kubernetes.io/part-of", ""))

        # Get image for tech detection
        images = [c.image for c in dep.spec.template.spec.containers or []]
        tech = ""
        for img in images:
            tech = detect_tech(img)
            if tech:
                break

        # Parse env vars for dependencies
        env_vars: dict[str, str] = {}
        for container in dep.spec.template.spec.containers or []:
            for env in container.env or []:
                if env.value:
                    env_vars[env.name] = env.value

        dependencies = parse_dependencies_from_env(env_vars)

        # Health path from readiness probe
        health_path = ""
        for container in dep.spec.template.spec.containers or []:
            probe = container.readiness_probe or container.liveness_probe
            if probe and probe.http_get:
                health_path = probe.http_get.path or ""
                break

        await pool.execute(
            """
            INSERT INTO service_catalog (name, namespace, cluster, team, tech, dependencies, health_path, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, now())
            ON CONFLICT (name, namespace, cluster) DO UPDATE SET
                team = COALESCE(NULLIF(EXCLUDED.team, ''), service_catalog.team),
                tech = COALESCE(NULLIF(EXCLUDED.tech, ''), service_catalog.tech),
                dependencies = EXCLUDED.dependencies,
                health_path = COALESCE(NULLIF(EXCLUDED.health_path, ''), service_catalog.health_path),
                updated_at = now()
            """,
            name, namespace, cluster_name, team, tech,
            json.dumps(dependencies), health_path,
        )
        upserted += 1

    logger.info("K8s sync complete: %d deployments indexed for cluster %s", upserted, cluster_name)
    return {"deployments_indexed": upserted, "cluster": cluster_name}


# --- LLM Bootstrap Matching ---


async def bootstrap_llm_matching() -> dict[str, Any]:
    """Use the configured LLM to fuzzy-match deployments to BHB pages.

    Fetches all unmatched deployments from service_catalog and all BHBs
    from bhb_index, sends them to the LLM for matching, and stores results.
    """
    from app.db import _get_pool
    from app.agent.rca_agent import _build_llm

    pool = _get_pool()

    # Get unmatched deployments
    deployments = await pool.fetch(
        "SELECT name, namespace, cluster, tech, dependencies FROM service_catalog WHERE bhb_page_id = '' OR bhb_page_id IS NULL"
    )
    if not deployments:
        return {"matched": 0, "message": "No unmatched deployments"}

    # Get all BHBs
    bhbs = await pool.fetch(
        "SELECT page_id, title, bhb_number, service_name FROM bhb_index"
    )
    if not bhbs:
        return {"matched": 0, "message": "No BHBs indexed — run Confluence sync first"}

    # Format for LLM
    dep_list = [
        {"name": r["name"], "namespace": r["namespace"], "tech": r["tech"],
         "dependencies": json.loads(r["dependencies"]) if r["dependencies"] else []}
        for r in deployments
    ]
    bhb_list = [
        {"page_id": r["page_id"], "title": r["title"], "service_name": r["service_name"]}
        for r in bhbs
    ]

    prompt = f"""Match each Kubernetes deployment to its corresponding Confluence BHB (operations handbook) page.

Hints:
- Names may differ: "msg-broker-prod" might be BHB "RabbitMQ"
- Use the tech/dependencies field as hints (e.g. tech=rabbitmq → BHB "RabbitMQ")
- Some deployments may have no matching BHB → use page_id "NONE"
- Some BHBs may match multiple deployments (e.g. shared database)
- Be conservative: if unsure, use confidence "low"

Deployments:
{json.dumps(dep_list, indent=2)}

BHB Pages:
{json.dumps(bhb_list, indent=2)}

Respond with ONLY a JSON array:
[
  {{"deployment": "name", "namespace": "ns", "bhb_page_id": "id or NONE", "bhb_title": "title", "confidence": "high|medium|low"}}
]"""

    llm = _build_llm()
    from langchain_core.messages import HumanMessage
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    raw = response.content

    # Parse LLM output
    try:
        # Extract JSON array from response
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            raise ValueError("No JSON array found")
        matches = json.loads(raw[start:end + 1])
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse LLM matching output: %s", e)
        return {"matched": 0, "error": str(e), "raw": raw[:500]}

    # Store matches
    matched = 0
    for m in matches:
        bhb_page_id = m.get("bhb_page_id", "NONE")
        if bhb_page_id == "NONE":
            continue

        await pool.execute(
            """
            UPDATE service_catalog
            SET bhb_page_id = $1, bhb_title = $2, match_confidence = $3, updated_at = now()
            WHERE name = $4 AND namespace = $5
            """,
            bhb_page_id,
            m.get("bhb_title", ""),
            m.get("confidence", "low"),
            m["deployment"],
            m.get("namespace", ""),
        )
        matched += 1

    # Also store BHB sections on matched entries
    for m in matches:
        if m.get("bhb_page_id", "NONE") == "NONE":
            continue
        bhb_row = await pool.fetchrow(
            "SELECT sections FROM bhb_index WHERE page_id = $1", m["bhb_page_id"]
        )
        if bhb_row and bhb_row["sections"]:
            await pool.execute(
                "UPDATE service_catalog SET bhb_sections = $1 WHERE name = $2 AND namespace = $3",
                bhb_row["sections"], m["deployment"], m.get("namespace", ""),
            )

    logger.info("LLM matching complete: %d deployments matched to BHBs", matched)
    return {"matched": matched, "total_deployments": len(dep_list), "total_bhbs": len(bhb_list)}


# --- Query helpers (used by agent tools) ---


async def lookup_service_info(service_name: str, namespace: str = "") -> dict[str, Any] | None:
    """Look up a service in the catalog by name (fuzzy)."""
    from app.db import _get_pool
    pool = _get_pool()

    # Try exact match first
    if namespace:
        row = await pool.fetchrow(
            "SELECT * FROM service_catalog WHERE name = $1 AND namespace = $2",
            service_name, namespace,
        )
    else:
        row = await pool.fetchrow(
            "SELECT * FROM service_catalog WHERE name = $1 LIMIT 1",
            service_name,
        )

    # Fallback: ILIKE fuzzy match
    if not row:
        row = await pool.fetchrow(
            "SELECT * FROM service_catalog WHERE name ILIKE $1 LIMIT 1",
            f"%{service_name}%",
        )

    if not row:
        return None

    return {
        "name": row["name"],
        "namespace": row["namespace"],
        "cluster": row["cluster"],
        "team": row["team"],
        "tech": row["tech"],
        "dependencies": json.loads(row["dependencies"]) if row["dependencies"] else [],
        "health_path": row["health_path"],
        "bhb_title": row["bhb_title"],
        "bhb_page_id": row["bhb_page_id"],
        "bhb_sections": json.loads(row["bhb_sections"]) if row["bhb_sections"] else {},
        "match_confidence": row["match_confidence"],
    }


async def get_runbook_content(
    service_name: str, section: str = "operations", namespace: str = "",
) -> dict[str, Any] | None:
    """Fetch a BHB section for a service from Confluence.

    Args:
        service_name: Deployment name.
        section: BHB section name (operations, monitoring, recovery, etc.).
        namespace: K8s namespace (optional, for disambiguation).
    """
    info = await lookup_service_info(service_name, namespace)
    if not info or not info.get("bhb_page_id"):
        # No catalog match — try searching Confluence directly
        from app.tools.confluence import search_pages
        results = search_pages(service_name, limit=3)
        if not results:
            return None
        # Return the first search result's content
        from app.tools.confluence import get_page_content
        return get_page_content(results[0]["id"])

    sections = info.get("bhb_sections", {})
    page_id = sections.get(section)
    if not page_id:
        # Section not found — return available sections
        return {
            "error": f"Section '{section}' not found for {service_name}",
            "available_sections": list(sections.keys()),
            "bhb_title": info["bhb_title"],
        }

    from app.tools.confluence import get_page_content
    return get_page_content(page_id)
