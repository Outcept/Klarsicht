"""Apply outbound TLS settings (custom CA, insecure mode) to both `requests` and `httpx`.

`requests` reads REQUESTS_CA_BUNDLE natively, but `httpx` (used by the Anthropic, OpenAI,
watsonx and Ollama SDKs) defaults to certifi and ignores the env vars. So we patch the
default constructor for httpx.Client / httpx.AsyncClient to inject an SSL context that
trusts certifi + our extra CA bundle (or skips verification entirely in insecure mode).
"""

from __future__ import annotations

import logging
import os
import ssl

from app.config import settings

logger = logging.getLogger(__name__)

_applied = False


def _build_ssl_context(ca_path: str | None, insecure: bool) -> ssl.SSLContext:
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()

    if ca_path:
        try:
            ctx.load_verify_locations(cafile=ca_path)
        except OSError as e:
            logger.warning("Failed to load extra CA bundle from %s: %s", ca_path, e)

    return ctx


def _patch_requests_insecure() -> None:
    import requests
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    original = requests.Session.merge_environment_settings

    def _merge(self, url, proxies, stream, verify, cert):
        result = original(self, url, proxies, stream, verify, cert)
        result["verify"] = False
        return result

    requests.Session.merge_environment_settings = _merge


def _patch_httpx(ctx: ssl.SSLContext) -> None:
    try:
        import httpx
    except ImportError:
        return

    def _wrap(cls):
        original = cls.__init__

        def patched(self, *args, **kwargs):
            if kwargs.get("verify", True) is True:
                kwargs["verify"] = ctx
            original(self, *args, **kwargs)

        cls.__init__ = patched

    _wrap(httpx.Client)
    _wrap(httpx.AsyncClient)


def apply_tls_settings() -> None:
    global _applied
    if _applied:
        return

    ca_path = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    insecure = not settings.tls_verify

    if not ca_path and not insecure:
        return

    _applied = True

    if insecure:
        logger.warning("KLARSICHT_TLS_VERIFY=false — outbound HTTPS cert verification disabled")
        _patch_requests_insecure()
    elif ca_path:
        logger.info("Trusting extra CA bundle: %s (applied to httpx; requests reads it via env var)", ca_path)

    ctx = _build_ssl_context(ca_path, insecure)
    _patch_httpx(ctx)
