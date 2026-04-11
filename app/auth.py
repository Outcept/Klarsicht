"""OIDC authentication and team-based access control.

Validates JWT bearer tokens from the OIDC provider, extracts claims,
maps them to alert labels, and filters incidents accordingly.

Config:
  KLARSICHT_AUTH_ENABLED=true
  KLARSICHT_OIDC_ISSUER_URL=https://login.microsoftonline.com/{tenant}/v2.0
  KLARSICHT_OIDC_CLIENT_ID=abc123
  KLARSICHT_AUTH_CLAIM_MAPPING={"department": "team"}
  KLARSICHT_AUTH_TEAM_MAPPINGS={"XY-Z": ["XY-Z1", "XY-Z2"]}
  KLARSICHT_AUTH_ADMIN_TEAMS=sre,admin
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

SESSION_COOKIE = "klarsicht_session"
SESSION_TTL = 8 * 3600  # 8 hours

# --- JWKS / OIDC discovery cache ---

_jwks_cache: dict[str, Any] = {}
_jwks_fetched_at: float = 0
_oidc_config: dict[str, Any] = {}
_oidc_config_fetched_at: float = 0
_JWKS_TTL = 3600  # 1 hour


def get_oidc_config() -> dict[str, Any]:
    """Fetch and cache the OIDC discovery document."""
    global _oidc_config, _oidc_config_fetched_at
    now = time.time()
    if _oidc_config and (now - _oidc_config_fetched_at) < _JWKS_TTL:
        return _oidc_config
    issuer = settings.oidc_issuer_url.rstrip("/")
    url = f"{issuer}/.well-known/openid-configuration"
    _oidc_config = requests.get(url, timeout=10).json()
    _oidc_config_fetched_at = now
    return _oidc_config


# --- Session cookie (signed JWT) ---


def _session_secret() -> str:
    """Server-side secret for signing session cookies."""
    return settings.oidc_client_secret or settings.join_token or "dev-secret-change-me"


def sign_session(claims: dict[str, Any]) -> str:
    """Sign a session JWT with the OIDC claims we care about."""
    payload = {
        "claims": claims,
        "exp": int(time.time()) + SESSION_TTL,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, _session_secret(), algorithm="HS256")


def verify_session(token: str) -> dict[str, Any] | None:
    """Verify and decode a session JWT. Returns claims dict or None."""
    try:
        payload = jwt.decode(token, _session_secret(), algorithms=["HS256"])
        return payload.get("claims", {})
    except JWTError:
        return None


def _get_claim_mapping() -> dict[str, str]:
    if not settings.auth_claim_mapping:
        return {}
    return json.loads(settings.auth_claim_mapping)


def _get_team_mappings() -> dict[str, list[str]]:
    if not settings.auth_team_mappings:
        return {}
    return json.loads(settings.auth_team_mappings)


def _get_admin_teams() -> list[str]:
    if not settings.auth_admin_teams:
        return []
    return [t.strip() for t in settings.auth_admin_teams.split(",") if t.strip()]


# --- OIDC token validation ---


def _fetch_jwks() -> dict[str, Any]:
    """Fetch and cache JWKS from the OIDC provider's discovery endpoint."""
    global _jwks_cache, _jwks_fetched_at
    now = time.time()
    if _jwks_cache and (now - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_cache

    issuer = settings.oidc_issuer_url.rstrip("/")
    config_url = f"{issuer}/.well-known/openid-configuration"
    config = requests.get(config_url, timeout=10).json()
    jwks_uri = config["jwks_uri"]
    _jwks_cache = requests.get(jwks_uri, timeout=10).json()
    _jwks_fetched_at = now
    logger.info("JWKS refreshed from %s", jwks_uri)
    return _jwks_cache


def decode_token(token: str) -> dict[str, Any]:
    """Validate and decode a JWT token using the OIDC provider's JWKS."""
    jwks = _fetch_jwks()
    unverified_header = jwt.get_unverified_header(token)

    rsa_key = {}
    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            rsa_key = key
            break

    if not rsa_key:
        raise HTTPException(status_code=401, detail="Unable to find signing key")

    payload = jwt.decode(
        token,
        rsa_key,
        algorithms=["RS256"],
        audience=settings.oidc_client_id,
        issuer=settings.oidc_issuer_url,
    )
    return payload


# --- User model ---


@dataclass
class AuthUser:
    sub: str
    claims: dict[str, Any]
    is_admin: bool = False
    # {alert_label: [allowed_values]} — e.g. {"team": ["XY-Z1", "XY-Z2"]}
    allowed_label_values: dict[str, list[str]] = field(default_factory=dict)


def resolve_user(claims: dict[str, Any]) -> AuthUser:
    """Build an AuthUser from OIDC claims using the configured mappings."""
    claim_mapping = _get_claim_mapping()
    team_mappings = _get_team_mappings()
    admin_teams = _get_admin_teams()

    allowed: dict[str, list[str]] = {}
    is_admin = False

    for oidc_claim, alert_label in claim_mapping.items():
        value = claims.get(oidc_claim)
        if value is None:
            continue

        # Check if this team is admin
        if value in admin_teams:
            is_admin = True
            break

        # Expand via team mappings or use exact value
        if value in team_mappings:
            allowed[alert_label] = team_mappings[value]
        else:
            allowed[alert_label] = [value]

    return AuthUser(
        sub=claims.get("sub", ""),
        claims=claims,
        is_admin=is_admin,
        allowed_label_values=allowed,
    )


# --- FastAPI dependency ---


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthUser | None:
    """FastAPI dependency: validate session cookie OR bearer token.

    Returns None when auth is disabled (all data visible).
    """
    if not settings.auth_enabled:
        return None

    # 1. Session cookie (BFF flow — set by /auth/callback)
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        claims = verify_session(session_token)
        if claims is not None:
            return resolve_user(claims)

    # 2. Bearer token (SPA PKCE flow or API clients)
    if credentials is not None:
        try:
            payload = decode_token(credentials.credentials)
            return resolve_user(payload)
        except JWTError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    raise HTTPException(status_code=401, detail="Not authenticated")


# --- Incident filtering ---


def filter_incidents(
    incidents: dict[str, Any],
    user: AuthUser | None,
) -> dict[str, Any]:
    """Filter incident dict based on user's allowed label values."""
    if user is None or user.is_admin:
        return incidents  # Auth disabled or admin — see everything

    if not user.allowed_label_values:
        return {}  # No mapped claims — see nothing

    return {
        iid: data for iid, data in incidents.items()
        if _incident_matches(data, user.allowed_label_values)
    }


def can_view_incident(incident_data: dict, user: AuthUser | None) -> bool:
    """Check if a user can view a specific incident."""
    if user is None or user.is_admin:
        return True
    if not user.allowed_label_values:
        return False
    return _incident_matches(incident_data, user.allowed_label_values)


def _incident_matches(incident_data: dict, allowed: dict[str, list[str]]) -> bool:
    """Check if an incident's labels match any of the user's allowed values."""
    labels = incident_data.get("labels", {})
    if not labels:
        return False
    for label_key, allowed_values in allowed.items():
        if labels.get(label_key, "") in allowed_values:
            return True
    return False
