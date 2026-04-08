"""Confluence REST API client for reading BHB (operations handbook) pages.

Supports both Atlassian Cloud and Server/Data Center:
  - Cloud:  basic auth with email + API token, /wiki/rest/api/...
  - Server: bearer token (PAT), /rest/api/...

Set KLARSICHT_CONFLUENCE_URL, KLARSICHT_CONFLUENCE_TOKEN,
and optionally KLARSICHT_CONFLUENCE_USER (email, Cloud only).
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 15


def _is_cloud() -> bool:
    """Detect Atlassian Cloud by URL pattern."""
    return ".atlassian.net" in settings.confluence_url


def _base_url() -> str:
    url = settings.confluence_url.rstrip("/")
    # Cloud uses /wiki prefix, Server doesn't
    if _is_cloud() and not url.endswith("/wiki"):
        url += "/wiki"
    return url


def _auth() -> tuple[str, str] | None:
    """Return (user, token) for basic auth (Cloud) or None for bearer (Server)."""
    if settings.confluence_user:
        return (settings.confluence_user, settings.confluence_token)
    return None


def _headers() -> dict[str, str]:
    """Build request headers. Uses bearer token for Server/DC."""
    h = {"Accept": "application/json"}
    if not settings.confluence_user:
        # Server/DC: PAT as bearer token
        h["Authorization"] = f"Bearer {settings.confluence_token}"
    return h


def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    """Make a GET request to the Confluence REST API."""
    url = f"{_base_url()}/rest/api{path}"
    resp = requests.get(
        url, params=params, headers=_headers(), auth=_auth(), timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _strip_html(html_content: str) -> str:
    """Convert Confluence storage format HTML to plain text."""
    # Remove HTML tags
    text = re.sub(r"<br\s*/?>", "\n", html_content)
    text = re.sub(r"<li[^>]*>", "- ", text)
    text = re.sub(r"<p[^>]*>", "\n", text)
    text = re.sub(r"<h[1-6][^>]*>", "\n## ", text)
    text = re.sub(r"</h[1-6]>", "\n", text)
    text = re.sub(r"<tr[^>]*>", "\n| ", text)
    text = re.sub(r"<td[^>]*>|<th[^>]*>", " | ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    # Clean up whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --- Public API ---


def search_pages(query: str, spaces: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Search for pages by title or content using CQL.

    Args:
        query: Search text.
        spaces: Space keys to search in. Uses configured spaces if None.
        limit: Max results.

    Returns:
        List of {id, title, space, url}.
    """
    space_list = spaces or settings.confluence_space_list
    space_clause = ""
    if space_list:
        quoted = ",".join(f'"{s}"' for s in space_list)
        space_clause = f" AND space IN ({quoted})"

    cql = f'(title ~ "{query}" OR text ~ "{query}"){space_clause} AND type = page'

    data = _get("/content/search", {"cql": cql, "limit": limit})
    results = []
    for page in data.get("results", []):
        results.append({
            "id": page["id"],
            "title": page["title"],
            "space": page.get("space", {}).get("key", ""),
            "url": f"{_base_url()}{page.get('_links', {}).get('webui', '')}",
        })
    return results


def get_page_content(page_id: str, max_chars: int = 8000) -> dict[str, Any]:
    """Get a page's content as plain text.

    Args:
        page_id: Confluence page ID.
        max_chars: Truncate content to this length (LLM context budget).

    Returns:
        {id, title, space, content, url}.
    """
    data = _get(f"/content/{page_id}", {"expand": "body.storage,space"})
    raw_html = data.get("body", {}).get("storage", {}).get("value", "")
    content = _strip_html(raw_html)
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[... truncated]"

    return {
        "id": data["id"],
        "title": data["title"],
        "space": data.get("space", {}).get("key", ""),
        "content": content,
        "url": f"{_base_url()}{data.get('_links', {}).get('webui', '')}",
    }


def get_child_pages(page_id: str) -> list[dict[str, Any]]:
    """List child pages of a parent page.

    Returns:
        List of {id, title, position} sorted by title.
    """
    data = _get(f"/content/{page_id}/child/page", {"limit": 100})
    children = []
    for page in data.get("results", []):
        children.append({
            "id": page["id"],
            "title": page["title"],
        })
    # Sort by title to maintain BHB section order (e.g. "026 - 0 ...", "026 - 1 ...")
    children.sort(key=lambda p: p["title"])
    return children


def list_bhb_pages(spaces: list[str] | None = None) -> list[dict[str, Any]]:
    """Discover all BHB root pages across configured spaces.

    Looks for pages matching the pattern "NNN - Service Name" that have
    child pages (indicating a BHB structure with sections).

    Returns:
        List of {id, title, space, bhb_number, service_name, sections}.
    """
    space_list = spaces or settings.confluence_space_list
    if not space_list:
        logger.warning("No Confluence spaces configured")
        return []

    bhbs = []
    for space_key in space_list:
        # Get all pages in the space — using CQL to filter by pattern
        # BHB root pages typically match "NNN - Name"
        cql = f'space = "{space_key}" AND type = page'
        start = 0
        while True:
            data = _get("/content/search", {"cql": cql, "limit": 50, "start": start})
            results = data.get("results", [])
            if not results:
                break

            for page in results:
                title = page["title"]
                # Match BHB pattern: "026 - RabbitMQ" or "026 - 0 RACI RabbitMQ" (subsection)
                match = re.match(r"^(\d{2,4})\s*-\s*(.+)$", title)
                if not match:
                    continue

                bhb_number = match.group(1)
                rest = match.group(2).strip()

                # Skip subsections (they start with a digit: "0 RACI", "1 Beschreibung")
                if rest and rest[0].isdigit():
                    continue

                # This looks like a BHB root page
                bhbs.append({
                    "id": page["id"],
                    "title": title,
                    "space": space_key,
                    "bhb_number": bhb_number,
                    "service_name": rest,
                })

            # Pagination
            total = data.get("totalSize", data.get("size", 0))
            start += len(results)
            if start >= total:
                break

    # Fetch child sections for each BHB
    for bhb in bhbs:
        children = get_child_pages(bhb["id"])
        bhb["sections"] = _parse_bhb_sections(children, bhb["bhb_number"])

    logger.info("Discovered %d BHBs across spaces %s", len(bhbs), space_list)
    return bhbs


# Standard BHB section numbering
BHB_SECTION_MAP = {
    "0": "raci",
    "1": "description",
    "2": "architecture",
    "3": "installation",
    "4": "operations",
    "5": "monitoring",
    "6": "procedures",
    "7": "contacts",
    "8": "security",
    "99": "internal",
    "100": "recovery",
}


def _parse_bhb_sections(children: list[dict], bhb_number: str) -> dict[str, str]:
    """Parse child pages into a section_name → page_id map.

    Example child title: "026 - 4 Betriebsaufgaben" → {"operations": "page_id"}
    """
    sections: dict[str, str] = {}
    prefix = f"{bhb_number} -"

    for child in children:
        title = child["title"]
        if not title.startswith(prefix):
            continue
        rest = title[len(prefix):].strip()
        # Extract section number: "4 Betriebsaufgaben" → "4"
        section_match = re.match(r"^(\d+)\s", rest)
        if section_match:
            section_num = section_match.group(1)
            section_name = BHB_SECTION_MAP.get(section_num, f"section_{section_num}")
            sections[section_name] = child["id"]

    return sections


def get_bhb_section(bhb_page_id: str, section: str, max_chars: int = 6000) -> dict[str, Any] | None:
    """Fetch a specific BHB section by name.

    Args:
        bhb_page_id: Page ID of the BHB root page.
        section: Section name (e.g. 'operations', 'monitoring', 'recovery').
        max_chars: Max content length.

    Returns:
        Page content dict, or None if section not found.
    """
    children = get_child_pages(bhb_page_id)
    bhb_number = ""
    # Detect BHB number from first child
    for child in children:
        match = re.match(r"^(\d{2,4})\s*-", child["title"])
        if match:
            bhb_number = match.group(1)
            break

    if not bhb_number:
        return None

    sections = _parse_bhb_sections(children, bhb_number)
    page_id = sections.get(section)
    if not page_id:
        return None

    return get_page_content(page_id, max_chars)
