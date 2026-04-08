"""Tests for service catalog: Confluence client, dependency parsing, tool selection."""

import pytest
from unittest.mock import patch, MagicMock

from app.config import settings
from app.catalog import detect_tech, parse_dependencies_from_env
from app.tools.confluence import _strip_html, _parse_bhb_sections, BHB_SECTION_MAP


# --- HTML stripping ---


def test_strip_html_basic():
    html = "<p>Hello <b>world</b></p><p>Second paragraph</p>"
    result = _strip_html(html)
    assert "Hello world" in result
    assert "Second paragraph" in result


def test_strip_html_lists():
    html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
    result = _strip_html(html)
    assert "- Item 1" in result
    assert "- Item 2" in result


def test_strip_html_headings():
    html = "<h2>Title</h2><p>Content</p>"
    result = _strip_html(html)
    assert "## Title" in result
    assert "Content" in result


def test_strip_html_entities():
    html = "<p>A &amp; B &lt; C</p>"
    result = _strip_html(html)
    assert "A & B < C" in result


# --- BHB section parsing ---


def test_parse_bhb_sections():
    children = [
        {"id": "100", "title": "026 - 0 RACI RabbitMQ"},
        {"id": "101", "title": "026 - 1 Beschreibung der Lösung"},
        {"id": "102", "title": "026 - 2 Architektur"},
        {"id": "103", "title": "026 - 3 Applikations-Installation und -Konfiguration"},
        {"id": "104", "title": "026 - 4 Betriebsaufgaben"},
        {"id": "105", "title": "026 - 5 Monitoring pro Umgebung"},
        {"id": "106", "title": "026 - 6 Applikationsspezifische Verfahren"},
        {"id": "107", "title": "026 - 7 Kontakte und Ansprechpartner"},
        {"id": "108", "title": "026 - 8 Information Security"},
        {"id": "109", "title": "026 - 99 Inventx interner Anhang"},
        {"id": "110", "title": "026 - 100 Mutationsauftrag / Wiederanlaufplan"},
    ]
    sections = _parse_bhb_sections(children, "026")
    assert sections["raci"] == "100"
    assert sections["description"] == "101"
    assert sections["architecture"] == "102"
    assert sections["installation"] == "103"
    assert sections["operations"] == "104"
    assert sections["monitoring"] == "105"
    assert sections["procedures"] == "106"
    assert sections["contacts"] == "107"
    assert sections["security"] == "108"
    assert sections["internal"] == "109"
    assert sections["recovery"] == "110"


def test_parse_bhb_sections_different_prefix():
    children = [
        {"id": "200", "title": "041 - 4 Betriebsaufgaben"},
        {"id": "201", "title": "041 - 5 Monitoring"},
    ]
    sections = _parse_bhb_sections(children, "041")
    assert sections["operations"] == "200"
    assert sections["monitoring"] == "201"


def test_parse_bhb_sections_ignores_other_prefix():
    children = [
        {"id": "300", "title": "026 - 4 Betriebsaufgaben"},
        {"id": "301", "title": "027 - 4 Betriebsaufgaben"},  # different BHB
    ]
    sections = _parse_bhb_sections(children, "026")
    assert sections["operations"] == "300"
    assert len(sections) == 1


# --- Tech detection ---


def test_detect_tech_java():
    assert detect_tech("ghcr.io/company/payment:latest") == ""
    assert detect_tech("openjdk:17-slim") == "java"
    assert detect_tech("eclipse-temurin:21-jdk-alpine") == "java"  # matched via "jdk"
    assert detect_tech("company/spring-boot-app:1.0") == "java"


def test_detect_tech_dotnet():
    assert detect_tech("mcr.microsoft.com/dotnet/aspnet:8.0") == "dotnet"


def test_detect_tech_python():
    assert detect_tech("python:3.12-slim") == "python"
    assert detect_tech("tiangolo/uvicorn-gunicorn-fastapi:latest") == "python"


def test_detect_tech_node():
    assert detect_tech("node:20-alpine") == "node"
    assert detect_tech("company/next-frontend:2.1") == "node"


def test_detect_tech_infra():
    assert detect_tech("rabbitmq:3.12-management") == "rabbitmq"
    assert detect_tech("postgres:16") == "postgres"
    assert detect_tech("redis:7-alpine") == "redis"


# --- Dependency parsing from env vars ---


def test_parse_deps_postgres():
    deps = parse_dependencies_from_env({
        "DATABASE_URL": "postgresql://user:pass@db.prod.svc:5432/payments",
    })
    assert "db.prod.svc:5432" in deps


def test_parse_deps_redis():
    deps = parse_dependencies_from_env({
        "REDIS_URL": "redis://redis.cache.svc:6379/0",
    })
    assert "redis.cache.svc:6379" in deps


def test_parse_deps_multiple():
    deps = parse_dependencies_from_env({
        "DATABASE_URL": "postgresql://db:5432/app",
        "REDIS_URL": "redis://redis:6379",
        "RABBITMQ_URL": "amqp://mq:5672",
    })
    assert len(deps) == 3
    assert "db:5432" in deps
    assert "redis:6379" in deps
    assert "mq:5672" in deps


def test_parse_deps_no_port_fallback():
    deps = parse_dependencies_from_env({
        "REDIS_HOST": "redis-cluster",
    })
    # No port extractable, falls back to type name
    assert "redis" in deps


def test_parse_deps_deduplication():
    deps = parse_dependencies_from_env({
        "DATABASE_URL": "postgresql://db:5432/app",
        "PGHOST": "db:5432",  # same endpoint
    })
    # Should not duplicate
    assert deps.count("db:5432") == 1


def test_parse_deps_mongo():
    deps = parse_dependencies_from_env({
        "MONGODB_URI": "mongodb://mongo.data.svc:27017/mydb",
    })
    assert "mongo.data.svc:27017" in deps


# --- Tool selection with Confluence ---


def test_get_tools_includes_catalog_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "mode", "standalone")
    monkeypatch.setattr(settings, "mimir_endpoint", "")
    monkeypatch.setattr(settings, "database_url", "postgres://localhost/test")
    monkeypatch.setattr(settings, "confluence_url", "https://company.atlassian.net/wiki")
    monkeypatch.setattr(settings, "gitlab_url", "")
    monkeypatch.setattr(settings, "gitlab_token", "")
    monkeypatch.setattr(settings, "gitlab_project", "")

    from app.agent.tools import get_tools
    tools = get_tools()
    tool_names = [t.name for t in tools]
    assert "lookup_service" in tool_names
    assert "search_runbook" in tool_names


def test_get_tools_no_catalog_without_confluence(monkeypatch):
    monkeypatch.setattr(settings, "mode", "standalone")
    monkeypatch.setattr(settings, "mimir_endpoint", "")
    monkeypatch.setattr(settings, "database_url", "postgres://localhost/test")
    monkeypatch.setattr(settings, "confluence_url", "")
    monkeypatch.setattr(settings, "gitlab_url", "")
    monkeypatch.setattr(settings, "gitlab_token", "")
    monkeypatch.setattr(settings, "gitlab_project", "")

    from app.agent.tools import get_tools
    tools = get_tools()
    tool_names = [t.name for t in tools]
    assert "lookup_service" not in tool_names
    assert "search_runbook" not in tool_names


def test_get_tools_no_catalog_without_db(monkeypatch):
    monkeypatch.setattr(settings, "mode", "standalone")
    monkeypatch.setattr(settings, "mimir_endpoint", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "confluence_url", "https://company.atlassian.net/wiki")
    monkeypatch.setattr(settings, "gitlab_url", "")
    monkeypatch.setattr(settings, "gitlab_token", "")
    monkeypatch.setattr(settings, "gitlab_project", "")

    from app.agent.tools import get_tools
    tools = get_tools()
    tool_names = [t.name for t in tools]
    assert "lookup_service" not in tool_names


def test_compact_tools_includes_lookup_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "mode", "standalone")
    monkeypatch.setattr(settings, "database_url", "postgres://localhost/test")
    monkeypatch.setattr(settings, "confluence_url", "https://company.atlassian.net/wiki")

    from app.agent.tools import get_compact_tools
    tools = get_compact_tools()
    tool_names = [t.name for t in tools]
    assert "lookup_service" in tool_names
    # search_runbook NOT in compact — too many tools for small models
    assert "search_runbook" not in tool_names
