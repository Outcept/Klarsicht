"""Apply outbound TLS settings (custom CA, insecure mode) globally.

CA bundles are picked up by `requests`/`httpx` via REQUESTS_CA_BUNDLE / SSL_CERT_FILE
env vars set by the Helm chart — no code needed here. Insecure mode (KLARSICHT_TLS_VERIFY=false)
patches the `requests` Session default to skip verification, which the LangChain HTTP path
and our internal callers all use.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

_applied = False


def apply_tls_settings() -> None:
    global _applied
    if _applied or settings.tls_verify:
        return
    _applied = True

    logger.warning("KLARSICHT_TLS_VERIFY=false — outbound HTTPS cert verification disabled")

    import requests
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    original = requests.Session.merge_environment_settings

    def _merge(self, url, proxies, stream, verify, cert):
        result = original(self, url, proxies, stream, verify, cert)
        result["verify"] = False
        return result

    requests.Session.merge_environment_settings = _merge
