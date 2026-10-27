"""Per-host request policies for responsible downloading.

This module is the single throttling/identification point for Pawchive traffic.
It started as upstream v5.13.0's ``download_policy`` and was extended for this
fork (v5.14.0) so that:

* Pawchive hosts are recognised **dynamically** (``pawchive.<suffix>`` plus any
  ``*.pawchive.<suffix>`` host), because the site has already rotated domains
  once (``pawchive.st`` → ``pawchive.pw``) and will rotate again. The upstream
  hardcoded ``pawchive.pw`` check silently disabled pacing for rotated domains.
* Metadata calls (favorites, recent feed, old-site crawl) can be paced by the
  same one-request-per-second budget as file downloads
  (:func:`pace_pawchive_request`).
* ``Retry-After`` responses are honoured (:func:`retry_after_seconds`), so a
  ``429``/``503`` slows us down for exactly as long as the server asks.

Nothing here imports Qt, so it is unit-testable without a display.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Mapping, Optional
from urllib.parse import urlparse

from kemonodownloader import __version__
from kemonodownloader.domain_config import get_domains

# Identifiable user agent with a contact address instead of impersonating a
# browser. The version is interpolated so it never drifts from the package.
IDENTIFIABLE_USER_AGENT = (
    f"KemonoDownloader/{__version__} (+mailto:izeno.contact@gmail.com)"
)
PAWCHIVE_MAX_ACTIVE_DOWNLOADS = 5
PAWCHIVE_REQUEST_INTERVAL = 1.0

# Fallback suffix used when the remote domain list is unavailable.
_FALLBACK_PAWCHIVE_DOMAIN = "pawchive.pw"
# Hard ceiling for a server-provided Retry-After, so a hostile/broken header
# cannot park a worker thread for hours.
MAX_RETRY_AFTER_SECONDS = 300.0


def pawchive_domains() -> list:
    """Return the configured ``pawchive.<suffix>`` domains (never empty)."""
    domains = [
        str(domain).lower().strip()
        for domain in get_domains()
        if str(domain).lower().startswith("pawchive.")
    ]
    return domains or [_FALLBACK_PAWCHIVE_DOMAIN]


def is_pawchive_hostname(hostname: str) -> bool:
    """Return whether *hostname* belongs to pawchive or one of its file hosts."""
    hostname = (hostname or "").lower().strip()
    if not hostname:
        return False
    for domain in pawchive_domains():
        if hostname == domain or hostname.endswith("." + domain):
            return True
    # Forward-compatible: an unknown-but-rotated pawchive suffix
    # (``pawchive.st`` -> ``pawchive.pw`` -> ?) still gets paced/identified
    # instead of silently escaping the policy. Only the real shape counts -
    # ``[host.]pawchive.<tld>`` - so ``pawchive.pw.example.com`` is not ours.
    labels = hostname.split(".")
    if len(labels) < 2 or len(labels) > 4:
        return False
    if "pawchive" not in labels:
        return False
    index = labels.index("pawchive")
    return index <= 1 and (len(labels) - index - 1) in (1, 2)


def is_pawchive_url(url: str) -> bool:
    """Return whether *url* belongs to pawchive or its file servers."""
    return is_pawchive_hostname(urlparse(url or "").hostname or "")


def get_request_headers(headers: dict, url: str) -> dict:
    """Return request headers with an identifiable UA for pawchive."""
    request_headers = dict(headers or {})
    if is_pawchive_url(url):
        request_headers["User-Agent"] = IDENTIFIABLE_USER_AGENT
    return request_headers


def retry_after_seconds(headers: Optional[Mapping[str, str]]) -> Optional[float]:
    """Parse a ``Retry-After`` header into seconds (``None`` when absent).

    Supports both the delta-seconds form (``Retry-After: 30``) and the HTTP-date
    form (``Retry-After: Wed, 21 Oct 2026 07:28:00 GMT``).
    """
    if not headers:
        return None
    raw = None
    for key, value in headers.items():
        if str(key).lower() == "retry-after":
            raw = value
            break
    if raw is None:
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        seconds = _parse_http_date_seconds(raw)
        if seconds is None:
            return None
    return max(0.0, min(seconds, MAX_RETRY_AFTER_SECONDS))


def _parse_http_date_seconds(raw: str) -> Optional[float]:
    from email.utils import parsedate_to_datetime

    try:
        moment = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if moment is None:
        return None
    try:
        target = moment.timestamp()
    except (OverflowError, OSError, ValueError):
        return None
    return max(0.0, target - time.time())


class _PawchiveDownloadLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self._next_request_at = 0.0

    def acquire(self, is_running: Callable[[], bool]) -> bool:
        """Reserve a download slot and wait for the request-rate interval."""
        while is_running():
            with self._lock:
                now = time.monotonic()
                if (
                    self._active < PAWCHIVE_MAX_ACTIVE_DOWNLOADS
                    and now >= self._next_request_at
                ):
                    self._active += 1
                    self._next_request_at = now + PAWCHIVE_REQUEST_INTERVAL
                    return True
                wait_for = max(0.05, self._next_request_at - now)
            time.sleep(min(wait_for, 0.1))
        return False

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)

    # -- introspection / test helpers -------------------------------------
    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    def reset(self) -> None:
        with self._lock:
            self._active = 0
            self._next_request_at = 0.0

    def defer_next_request(self, seconds: float) -> None:
        """Push the next allowed request start at least *seconds* ahead."""
        with self._lock:
            self._next_request_at = max(
                self._next_request_at, time.monotonic() + max(0.0, seconds)
            )


_pawchive_limiter = _PawchiveDownloadLimiter()

# Metadata (favorites / recent feed / old-site crawl) pacing shares the same
# one-request-per-second budget but does not consume a download slot.
_metadata_lock = threading.Lock()
_next_metadata_at = 0.0


def acquire_pawchive_download(url: str, is_running: Callable[[], bool]) -> bool:
    if not is_pawchive_url(url):
        return True
    return _pawchive_limiter.acquire(is_running)


def release_pawchive_download(url: str) -> None:
    if is_pawchive_url(url):
        _pawchive_limiter.release()


def defer_pawchive_requests(seconds: float) -> None:
    """Honour a server ``Retry-After`` for both downloads and metadata calls."""
    global _next_metadata_at
    seconds = max(0.0, float(seconds))
    _pawchive_limiter.defer_next_request(seconds)
    with _metadata_lock:
        _next_metadata_at = max(_next_metadata_at, time.monotonic() + seconds)


def pace_pawchive_request(
    url: str,
    is_running: Callable[[], bool] = lambda: True,
    interval: float = PAWCHIVE_REQUEST_INTERVAL,
) -> bool:
    """Block until the next allowed Pawchive *metadata* request slot.

    Returns ``False`` when *is_running* turns false while waiting, so worker
    threads can abort cleanly.
    """
    global _next_metadata_at
    if not is_pawchive_url(url):
        return True
    while is_running():
        with _metadata_lock:
            now = time.monotonic()
            if now >= _next_metadata_at:
                _next_metadata_at = now + interval
                return True
            wait_for = _next_metadata_at - now
        time.sleep(min(max(wait_for, 0.05), 0.1))
    return False


def reset_pawchive_limiter() -> None:
    """Reset both pacers (used by tests and by a full download reset)."""
    global _next_metadata_at
    _pawchive_limiter.reset()
    with _metadata_lock:
        _next_metadata_at = 0.0
