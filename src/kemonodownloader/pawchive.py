"""Pawchive / Kemono-family favorites helpers.

Pure-Python helpers for:

* fetching an authenticated Pawchive favorites list (``GET /account/favorites``),
* optionally pulling the recent-posts feed (``GET /posts``),
* crawling a previous Kemono-family site's favorites list
  (``GET /api/v1/account/favorites?type=artist``, paginated with ``?o=``),
* parsing a Kemono-family favorites JSON export into ``(service, id, name)``.

This module deliberately has **no** Qt dependency so the parsing/normalisation
logic can be unit-tested without a display.  Network calls accept an optional
``requests.Session`` so the caller can reuse the application's proxy-aware
session.
"""

from __future__ import annotations

import json
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from kemonodownloader.domain_config import get_domains

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Artist entry: (service, id, name)
ArtistEntry = Tuple[str, str, str]


def get_pawchive_domain() -> str:
    """Return the active pawchive domain (first ``pawchive.<suffix>`` entry)."""
    for domain in get_domains():
        if domain.startswith("pawchive."):
            return domain
    return "pawchive.pw"


def build_creator_url(
    service: str, creator_id: str, domain: Optional[str] = None
) -> str:
    """Build a creator page URL for the given service/id, e.g.
    ``https://pawchive.pw/fanbox/user/12345``."""
    base = (domain or get_pawchive_domain()).rstrip("/")
    return f"https://{base}/{service}/user/{creator_id}"


def auth_cookie_header(credential: str) -> Dict[str, str]:
    """Build the authentication cookie header for a Pawchive/Kemono session key.

    Pawchive sends API keys as ``Cookie: session=<key>``.  A value that already
    looks like a cookie (contains ``=``) is forwarded verbatim so a full
    ``connect.sid=…`` style cookie also works.
    """
    credential = (credential or "").strip()
    if "=" in credential:
        return {"Cookie": credential}
    return {"Cookie": f"session={credential}"}


def _browser_headers(referer: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _resolve_session(session: Optional[requests.Session]) -> requests.Session:
    return session if session is not None else requests.Session()


def extract_artist(entry: object) -> Optional[ArtistEntry]:
    """Normalise a single favorites entry into ``(service, id, name)``.

    Handles minor shape variations: ``id`` may also appear as ``user``,
    ``creator_id`` or ``artist_id``.
    """
    if not isinstance(entry, dict):
        return None
    service = str(entry.get("service") or "").strip().lower()
    if not service:
        return None
    artist_id = entry.get("id")
    if artist_id is None:
        artist_id = (
            entry.get("user")
            if entry.get("user") is not None
            else entry.get("creator_id", entry.get("artist_id"))
        )
    if artist_id is None or str(artist_id).strip() == "":
        return None
    name = str(entry.get("name") or entry.get("title") or "").strip()
    return (service, str(artist_id), name)


def parse_artist_entries(payload: object) -> List[ArtistEntry]:
    """Extract artist entries from a favorites API payload.

    Accepts a list, ``{"artists": [...]}``, ``{"creators": [...]}``,
    ``{"data": [...]}``, ``{"results": [...]}`` or an empty object.
    """
    items: Iterable[object]
    if isinstance(payload, dict):
        for key in ("artists", "creators", "data", "results"):
            if key in payload and isinstance(payload[key], list):
                items = payload[key]
                break
        else:
            items = []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    entries: List[ArtistEntry] = []
    for item in items:
        artist = extract_artist(item)
        if artist is not None and artist not in entries:
            entries.append(artist)
    return entries


def parse_favorites_json_text(text: str) -> List[ArtistEntry]:
    """Parse a Kemono-family favorites JSON export.

    Expected shape is ``[{"id": "...", "service": "...", "name": "..."}]``
    (optionally wrapped in ``{"artists": [...]}``), but minor variations are
    tolerated gracefully.
    """
    data = json.loads(text)
    return parse_artist_entries(data)


def _request_json(
    session: requests.Session,
    url: str,
    referer: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> object:
    headers = _browser_headers(referer)
    if extra_headers:
        headers.update(extra_headers)
    response = session.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    if not response.content.strip():
        return None
    return response.json()


def fetch_favorites(
    domain: Optional[str] = None,
    api_key: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> List[ArtistEntry]:
    """Fetch the authenticated Pawchive favorites list.

    Returns a list of ``(service, id, name)`` entries.  When no API key is
    supplied the request is anonymous (returns an empty list).
    """
    domain = domain or get_pawchive_domain()
    url = f"https://{domain}/api/v1/account/favorites"
    headers = auth_cookie_header(api_key) if api_key else None
    payload = _request_json(
        _resolve_session(session),
        url,
        referer=f"https://{domain}/",
        extra_headers=headers,
    )
    return parse_artist_entries(payload)


def fetch_recent_posts_creators(
    domain: Optional[str] = None,
    session: Optional[requests.Session] = None,
    page_size: int = 50,
) -> List[ArtistEntry]:
    """Fetch one page of the recent-posts feed and return the unique creators.

    Each returned entry is ``(service, creator_id, title)`` where ``title`` is
    the first post title seen for that creator.
    """
    domain = domain or get_pawchive_domain()
    url = f"https://{domain}/api/v1/posts?o=0"
    payload = _request_json(
        _resolve_session(session), url, referer=f"https://{domain}/"
    )
    posts = payload if isinstance(payload, list) else []
    seen = set()
    entries: List[ArtistEntry] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        service = str(post.get("service") or "").strip().lower()
        creator_id = post.get("user")
        if not service or creator_id is None:
            continue
        key = (service, str(creator_id))
        if key in seen:
            continue
        seen.add(key)
        entries.append((service, str(creator_id), str(post.get("title") or "")))
    return entries[:page_size]


def fetch_old_site_favorites(
    domain: str,
    credential: str,
    session: Optional[requests.Session] = None,
    page_size: int = 50,
    max_pages: int = 1000,
) -> List[ArtistEntry]:
    """Crawl a previous Kemono-family site's favorites list.

    Uses ``GET /api/v1/account/favorites?type=artist`` with ``?o=`` offset
    pagination (matching Pawchive/Kemono), authenticated with the provided
    session cookie or API key.
    """
    domain = (domain or "").strip().rstrip("/")
    if not domain:
        return []

    entries: List[ArtistEntry] = []
    seen = set()
    offset = 0
    for _ in range(max_pages):
        url = f"https://{domain}/api/v1/account/favorites?type=artist&o={offset}"
        payload = _request_json(
            _resolve_session(session),
            url,
            referer=f"https://{domain}/",
            extra_headers=auth_cookie_header(credential),
        )
        page = parse_artist_entries(payload)
        new_in_page = 0
        for artist in page:
            key = (artist[0], artist[1])
            if key not in seen:
                seen.add(key)
                entries.append(artist)
                new_in_page += 1
        if not page or new_in_page == 0:
            break
        if len(page) < page_size:
            break
        offset += page_size
        time.sleep(0.1)

    return entries


def parse_json_file(path: str) -> List[ArtistEntry]:
    """Read and parse a favorites JSON export file."""
    with open(path, "r", encoding="utf-8") as fh:
        return parse_favorites_json_text(fh.read())
