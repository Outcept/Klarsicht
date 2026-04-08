"""Connectivity check tool for the RCA agent.

Verifies whether external endpoints (HTTP/HTTPS/TCP) are reachable.
Read-only, no request payloads, short timeouts.
"""

from __future__ import annotations

import logging
import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_MAX_TIMEOUT = 30


def check_endpoint(url: str, timeout: int = 5) -> dict[str, Any]:
    """Check if an endpoint is reachable.

    Supports:
    - http:// and https:// — makes a GET request, returns status code +
      TLS certificate info for HTTPS.
    - tcp://host:port — opens a socket connection, returns if port is open.

    Args:
        url: Endpoint URL (e.g. 'https://payment-api:8443/healthz', 'tcp://db:5432').
        timeout: Connection timeout in seconds (max 30).

    Returns:
        dict with keys: reachable, response_time_ms, status_code (HTTP),
        tls (HTTPS), error (on failure).
    """
    timeout = max(1, min(timeout, _MAX_TIMEOUT))
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()

    if scheme in ("http", "https"):
        return _check_http(url, parsed, timeout)
    elif scheme == "tcp":
        host = parsed.hostname or ""
        port = parsed.port
        if not host or not port:
            return {"reachable": False, "error": "TCP URL must include host and port (tcp://host:port)"}
        return _check_tcp(host, port, timeout)
    else:
        return {"reachable": False, "error": f"Unsupported scheme '{scheme}'. Use http, https, or tcp."}


def _check_http(url: str, parsed: Any, timeout: int) -> dict[str, Any]:
    """Check an HTTP/HTTPS endpoint."""
    result: dict[str, Any] = {"url": url, "reachable": False}

    try:
        start = time.monotonic()
        resp = requests.get(url, timeout=timeout, allow_redirects=True, verify=True)
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)

        result["reachable"] = True
        result["status_code"] = resp.status_code
        result["response_time_ms"] = elapsed_ms

        # TLS cert info for HTTPS
        if parsed.scheme == "https":
            result["tls"] = _get_tls_info(parsed.hostname, parsed.port or 443, timeout)

    except requests.exceptions.SSLError as e:
        result["error"] = f"TLS/SSL error: {e}"
        # Still try to get cert info even on SSL errors
        if parsed.scheme == "https":
            result["tls"] = _get_tls_info(parsed.hostname, parsed.port or 443, timeout)
    except requests.exceptions.ConnectionError as e:
        result["error"] = f"Connection refused or unreachable: {e}"
    except requests.exceptions.Timeout:
        result["error"] = f"Timed out after {timeout}s"
    except requests.exceptions.RequestException as e:
        result["error"] = f"Request failed: {e}"

    return result


def _check_tcp(host: str, port: int, timeout: int) -> dict[str, Any]:
    """Check a TCP endpoint by opening a socket connection."""
    result: dict[str, Any] = {"url": f"tcp://{host}:{port}", "reachable": False}

    try:
        start = time.monotonic()
        sock = socket.create_connection((host, port), timeout=timeout)
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        sock.close()

        result["reachable"] = True
        result["response_time_ms"] = elapsed_ms

    except socket.timeout:
        result["error"] = f"Timed out after {timeout}s"
    except OSError as e:
        result["error"] = f"Connection failed: {e}"

    return result


def _get_tls_info(hostname: str | None, port: int, timeout: int) -> dict[str, Any]:
    """Extract TLS certificate information from an HTTPS endpoint."""
    if not hostname:
        return {"error": "No hostname for TLS check"}

    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return {"error": "No certificate returned"}

                # Parse expiry
                not_after = cert.get("notAfter", "")
                not_before = cert.get("notBefore", "")

                # ssl date format: 'Mar 19 10:00:00 2025 GMT'
                expiry_dt = None
                if not_after:
                    try:
                        expiry_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass

                # Issuer
                issuer_parts = []
                for rdn in cert.get("issuer", ()):
                    for attr_name, attr_value in rdn:
                        if attr_name in ("organizationName", "commonName"):
                            issuer_parts.append(attr_value)
                issuer = ", ".join(issuer_parts) if issuer_parts else "unknown"

                # Subject
                subject_parts = []
                for rdn in cert.get("subject", ()):
                    for attr_name, attr_value in rdn:
                        if attr_name == "commonName":
                            subject_parts.append(attr_value)
                subject_cn = subject_parts[0] if subject_parts else "unknown"

                valid = expiry_dt > datetime.now(timezone.utc) if expiry_dt else None

                return {
                    "subject": subject_cn,
                    "issuer": issuer,
                    "not_before": not_before,
                    "not_after": not_after,
                    "valid": valid,
                    "days_until_expiry": (expiry_dt - datetime.now(timezone.utc)).days if expiry_dt else None,
                }

    except ssl.SSLCertVerificationError as e:
        return {"error": f"Certificate verification failed: {e}", "valid": False}
    except Exception as e:
        return {"error": f"TLS check failed: {e}"}
