"""Tests for connectivity check tool."""

import socket
from unittest.mock import MagicMock, patch

import pytest

from app.tools.connectivity import check_endpoint


# --- HTTP checks ---


@patch("app.tools.connectivity.requests.get")
def test_http_endpoint_reachable(mock_get):
    """HTTP endpoint returns status code and response time."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp

    result = check_endpoint("http://my-api:8080/healthz")

    assert result["reachable"] is True
    assert result["status_code"] == 200
    assert "response_time_ms" in result
    assert "error" not in result
    mock_get.assert_called_once_with(
        "http://my-api:8080/healthz", timeout=5, allow_redirects=True, verify=True,
    )


@patch("app.tools.connectivity.requests.get")
def test_http_endpoint_500(mock_get):
    """HTTP endpoint returning 500 is still reachable."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_get.return_value = mock_resp

    result = check_endpoint("http://my-api:8080/healthz")

    assert result["reachable"] is True
    assert result["status_code"] == 500


@patch("app.tools.connectivity.requests.get")
def test_http_connection_refused(mock_get):
    """Connection refused produces error with reachable=False."""
    import requests as req_lib
    mock_get.side_effect = req_lib.exceptions.ConnectionError("Connection refused")

    result = check_endpoint("http://my-api:8080/healthz")

    assert result["reachable"] is False
    assert "Connection refused" in result["error"]


@patch("app.tools.connectivity.requests.get")
def test_http_timeout(mock_get):
    """Timeout produces error with reachable=False."""
    import requests as req_lib
    mock_get.side_effect = req_lib.exceptions.Timeout("timed out")

    result = check_endpoint("http://my-api:8080/healthz", timeout=3)

    assert result["reachable"] is False
    assert "Timed out" in result["error"]


# --- HTTPS with TLS ---


@patch("app.tools.connectivity._get_tls_info")
@patch("app.tools.connectivity.requests.get")
def test_https_with_tls_info(mock_get, mock_tls):
    """HTTPS endpoint returns status code + TLS info."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp
    mock_tls.return_value = {
        "subject": "payment-api.example.com",
        "issuer": "Let's Encrypt",
        "not_after": "Mar 19 10:00:00 2027 GMT",
        "valid": True,
        "days_until_expiry": 365,
    }

    result = check_endpoint("https://payment-api:8443/healthz")

    assert result["reachable"] is True
    assert result["status_code"] == 200
    assert result["tls"]["valid"] is True
    assert result["tls"]["issuer"] == "Let's Encrypt"
    mock_tls.assert_called_once_with("payment-api", 8443, 5)


@patch("app.tools.connectivity._get_tls_info")
@patch("app.tools.connectivity.requests.get")
def test_https_default_port(mock_get, mock_tls):
    """HTTPS without explicit port defaults to 443 for TLS check."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp
    mock_tls.return_value = {"valid": True}

    result = check_endpoint("https://example.com/health")

    mock_tls.assert_called_once_with("example.com", 443, 5)


@patch("app.tools.connectivity._get_tls_info")
@patch("app.tools.connectivity.requests.get")
def test_https_ssl_error_still_gets_tls_info(mock_get, mock_tls):
    """SSL errors still attempt to get TLS cert info."""
    import requests as req_lib
    mock_get.side_effect = req_lib.exceptions.SSLError("certificate verify failed")
    mock_tls.return_value = {"valid": False, "error": "Certificate verification failed"}

    result = check_endpoint("https://expired.example.com")

    assert result["reachable"] is False
    assert "TLS/SSL error" in result["error"]
    assert result["tls"]["valid"] is False


# --- TCP checks ---


@patch("app.tools.connectivity.socket.create_connection")
def test_tcp_reachable(mock_conn):
    """TCP endpoint returns reachable + response time."""
    mock_sock = MagicMock()
    mock_conn.return_value = mock_sock

    result = check_endpoint("tcp://db:5432")

    assert result["reachable"] is True
    assert "response_time_ms" in result
    assert "error" not in result
    mock_conn.assert_called_once_with(("db", 5432), timeout=5)
    mock_sock.close.assert_called_once()


@patch("app.tools.connectivity.socket.create_connection")
def test_tcp_timeout(mock_conn):
    """TCP timeout returns reachable=False."""
    mock_conn.side_effect = socket.timeout("timed out")

    result = check_endpoint("tcp://db:5432", timeout=2)

    assert result["reachable"] is False
    assert "Timed out" in result["error"]


@patch("app.tools.connectivity.socket.create_connection")
def test_tcp_connection_refused(mock_conn):
    """TCP connection refused returns error."""
    mock_conn.side_effect = OSError("Connection refused")

    result = check_endpoint("tcp://redis:6379")

    assert result["reachable"] is False
    assert "Connection refused" in result["error"]


def test_tcp_missing_port():
    """TCP URL without port returns error."""
    result = check_endpoint("tcp://db-host")

    assert result["reachable"] is False
    assert "must include host and port" in result["error"]


# --- Edge cases ---


def test_unsupported_scheme():
    """Unsupported scheme returns error."""
    result = check_endpoint("ftp://files.example.com")

    assert result["reachable"] is False
    assert "Unsupported scheme" in result["error"]


def test_timeout_clamped():
    """Timeout is clamped between 1 and 30."""
    # We just verify the function doesn't crash with extreme values
    with patch("app.tools.connectivity.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        check_endpoint("http://api:8080", timeout=0)
        mock_get.assert_called_with("http://api:8080", timeout=1, allow_redirects=True, verify=True)

        check_endpoint("http://api:8080", timeout=999)
        mock_get.assert_called_with("http://api:8080", timeout=30, allow_redirects=True, verify=True)


# --- Tool wrapper test ---


def test_tool_wrapper():
    """The LangGraph @tool wrapper returns serialized JSON."""
    from app.agent.tools import check_endpoint as tool_fn

    assert tool_fn.name == "check_endpoint"
    # Docstring should be present for the LLM
    assert "external endpoint" in tool_fn.description.lower()


def test_remote_tool_wrapper():
    """The remote LangGraph @tool wrapper exists and has cluster param."""
    from app.agent.tools import remote_check_endpoint as tool_fn

    assert tool_fn.name == "remote_check_endpoint"
    assert "cluster" in tool_fn.description.lower()


# --- get_tools includes connectivity ---


def test_get_tools_includes_connectivity_standalone(monkeypatch):
    """Standalone mode includes check_endpoint."""
    from app.config import settings
    monkeypatch.setattr(settings, "mode", "standalone")
    monkeypatch.setattr(settings, "mimir_endpoint", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "gitlab_url", "")
    monkeypatch.setattr(settings, "gitlab_token", "")
    monkeypatch.setattr(settings, "gitlab_project", "")

    from app.agent.tools import get_tools
    tools = get_tools()
    tool_names = [t.name for t in tools]
    assert "check_endpoint" in tool_names


def test_get_tools_includes_connectivity_backend(monkeypatch):
    """Backend mode includes remote_check_endpoint."""
    from app.config import settings
    monkeypatch.setattr(settings, "mode", "backend")
    monkeypatch.setattr(settings, "mimir_endpoint", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "gitlab_url", "")
    monkeypatch.setattr(settings, "gitlab_token", "")
    monkeypatch.setattr(settings, "gitlab_project", "")

    from app.agent.tools import get_tools
    tools = get_tools()
    tool_names = [t.name for t in tools]
    assert "remote_check_endpoint" in tool_names


def test_get_compact_tools_includes_connectivity(monkeypatch):
    """Compact mode includes check_endpoint."""
    from app.config import settings
    monkeypatch.setattr(settings, "mode", "standalone")
    monkeypatch.setattr(settings, "database_url", "")

    from app.agent.tools import get_compact_tools
    tools = get_compact_tools()
    tool_names = [t.name for t in tools]
    assert "check_endpoint" in tool_names
