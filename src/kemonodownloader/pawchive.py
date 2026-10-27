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
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from kemonodownloader.domain_config import get_domains
from kemonodownloader.download_policy import (
    IDENTIFIABLE_USER_AGENT,
    is_pawchive_url,
    pace_pawchive_request,
    retry_after_seconds,
)
from kemonodownloader.pawchive_files import size_cap_bytes

# Use the same honest, contactable user agent as the download paths. Impersonating
# a browser is what upstream v5.13.0 removed on purpose (it is also a common cause
# of the 403s Pawchive hands out). Kept as a module constant so callers/tests that
# imported it keep working.
DEFAULT_USER_AGENT = IDENTIFIABLE_USER_AGENT

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
    is_running: Optional[Callable[[], bool]] = None,
    max_attempts: int = 3,
) -> object:
    """GET *url* as JSON, paced and rate-limit aware.

    Every Pawchive metadata call goes through here, so the one-request-per-second
    budget applies to favorites lists, the recent feed and the old-site crawl
    alike. ``429``/``503`` responses are retried after the server's
    ``Retry-After`` (capped in :mod:`download_policy`). Only idempotent GETs are
    retried, which is all this module issues.
    """
    headers = _browser_headers(referer)
    if extra_headers:
        headers.update(extra_headers)

    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        if is_running is not None and not is_running():
            raise requests.RequestException("Cancelled before request")
        if not pace_pawchive_request(url, is_running or (lambda: True)):
            raise requests.RequestException("Cancelled while pacing request")

        response = session.get(url, headers=headers, timeout=timeout)
        if response.status_code in (429, 503) and attempt < attempts:
            delay = retry_after_seconds(getattr(response, "headers", None))
            if delay is None:
                delay = float(attempt)  # mild, capped exponential substitute
            time.sleep(min(delay, 30.0))
            continue

        response.raise_for_status()
        if not response.content.strip():
            return None
        return response.json()
    raise requests.RequestException(f"Exhausted retries for {url}")


def fetch_favorites(
    domain: Optional[str] = None,
    api_key: Optional[str] = None,
    session: Optional[requests.Session] = None,
    fav_type: str = "artist",
    is_running: Optional[Callable[[], bool]] = None,
) -> List[ArtistEntry]:
    """Fetch the authenticated Pawchive favorites list.

    Returns a list of ``(service, id, name)`` entries.  When no credential is
    supplied the request is anonymous and the API answers ``401`` with ``{}``
    (surfaced as an empty list).

    ``fav_type`` selects the API's ``type`` query parameter: ``"artist"`` (the
    default, creator favourites — what this downloader queues) or ``"post"``.
    """
    domain = domain or get_pawchive_domain()
    url = f"https://{domain}/api/v1/account/favorites?type={fav_type}"
    headers = auth_cookie_header(api_key) if api_key else None
    payload = _request_json(
        _resolve_session(session),
        url,
        referer=f"https://{domain}/",
        extra_headers=headers,
        is_running=is_running,
    )
    return parse_artist_entries(payload)


def extract_posts(payload: object) -> List[dict]:
    """Return the post list from an API payload, tolerating both shapes.

    Pawchive answers ``/api/v1/posts`` with a bare array, while ``kemono.cr``
    wraps it as ``{"count": …, "true_count": …, "posts": [...]}``. Some mirrors
    also use ``{"data": [...]}``.
    """
    if isinstance(payload, list):
        return [post for post in payload if isinstance(post, dict)]
    if isinstance(payload, dict):
        for key in ("posts", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [post for post in value if isinstance(post, dict)]
    return []


def fetch_recent_posts_creators(
    domain: Optional[str] = None,
    session: Optional[requests.Session] = None,
    page_size: int = 50,
    is_running: Optional[Callable[[], bool]] = None,
) -> List[ArtistEntry]:
    """Fetch one page of the recent-posts feed and return the unique creators.

    Each returned entry is ``(service, creator_id, title)`` where ``title`` is
    the first post title seen for that creator.
    """
    domain = domain or get_pawchive_domain()
    url = f"https://{domain}/api/v1/posts?o=0"
    payload = _request_json(
        _resolve_session(session),
        url,
        referer=f"https://{domain}/",
        is_running=is_running,
    )
    posts = extract_posts(payload)
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


# ---------------------------------------------------------------------------
# Session cookie helpers
# ---------------------------------------------------------------------------
#
# Pawchive has exactly one auth scheme: the ``session`` cookie that the website
# sets after a form login. There is no API-key endpoint and no
# ``/api/v1/account/login`` route, so asking the user to paste a cookie works but
# is unfriendly; ``login_with_password`` drives the real web form instead.


class PawchiveLoginError(RuntimeError):
    """Raised when a Pawchive/Kemono-family form login does not yield a session."""


def extract_session_cookie(session: object) -> str:
    """Return the ``session`` cookie value from a requests session (or "")."""
    cookies = getattr(session, "cookies", None)
    if cookies is None:
        return ""
    try:
        value = cookies.get("session")
    except Exception:
        return ""
    return str(value or "")


def login_with_password(
    username: str,
    password: str,
    domain: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
    is_running: Optional[Callable[[], bool]] = None,
) -> str:
    """Log in through the site's web form and return the ``session`` cookie.

    The cookie is what the API wants as ``Cookie: session=<value>``. Raises
    :class:`PawchiveLoginError` when the site answers without setting a session
    cookie (bad credentials, captcha, outage).
    """
    username = (username or "").strip()
    password = password or ""
    if not username or not password:
        raise PawchiveLoginError("Username and password are required")

    domain = domain or get_pawchive_domain()
    login_url = f"https://{domain}/account/login"
    requests_session = _resolve_session(session)

    if is_running is not None and not is_running():
        raise PawchiveLoginError("Cancelled before login")
    if not pace_pawchive_request(login_url, is_running or (lambda: True)):
        raise PawchiveLoginError("Cancelled while pacing login")

    headers = _browser_headers(f"https://{domain}/")
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        response = requests_session.post(
            login_url,
            data={"username": username, "password": password},
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException as exc:  # pragma: no cover - network
        raise PawchiveLoginError(f"Login request failed: {exc}") from exc

    token = extract_session_cookie(requests_session)
    if not token:
        raise PawchiveLoginError(
            f"Login did not return a session cookie (HTTP {response.status_code})"
        )
    return token


def verify_session(
    credential: str,
    domain: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> bool:
    """Return whether *credential* is accepted by ``/account/favorites``.

    The endpoint answers ``401`` (with an empty ``{}`` body) for anonymous or
    expired sessions, and a list/object with artists when the cookie is valid.
    """
    credential = (credential or "").strip()
    if not credential:
        return False
    domain = domain or get_pawchive_domain()
    url = f"https://{domain}/api/v1/account/favorites?type=artist"
    try:
        response = _resolve_session(session).get(
            url,
            headers={
                **_browser_headers(f"https://{domain}/"),
                **auth_cookie_header(credential),
            },
            timeout=timeout,
        )
    except requests.RequestException:
        return False
    if getattr(response, "status_code", 0) == 401:
        return False
    if getattr(response, "status_code", 0) >= 400:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    # ``{}`` is what an unauthenticated call returns even when it is not a 401.
    return bool(payload)


def file_size_cap_for_favorites(favorites: object) -> int:
    """Backwards-friendly alias for :func:`pawchive_files.size_cap_bytes`."""
    return size_cap_bytes(favorites)
