"""Pawchive/Kemono-family file resolution (the "what do I actually download" layer).

The Kemono-family API has grown three coexisting file models. As observed on the
live Pawchive API (2026-10-28):

1. **Classic** — ``{"name", "path"}`` (optionally ``"node": 2``). The file lives at
   ``https://file.<domain>/data{path}?f={name}``.
2. **Preview-only** — ``{"name", "path", "preview_only": true, "temp_url", "temp_expires"}``.
   The full-resolution file is *not* served from the classic host; the only
   working link is the signed ``temp_url`` (host ``t1.<domain>``, expires after
   roughly two weeks), otherwise the thumbnail.
3. **Deferred** — ``{"name", "deferred": true}`` with **no** ``path``: not imported
   yet, nothing to download.

On top of that, ``has_full: false`` on the post (ours since v5.13.0) still means
"no full-resolution media at all".

This module turns any of those shapes into a single decision plus a reason, so
the two downloaders, the thumbnail tab and the favorites flows all agree. It has
no Qt dependency and no network access, which makes it fully unit-testable.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from kemonodownloader.domain_config import clean_file_url, to_thumbnail_url

# Kinds of resolved sources.
FULL = "full"
TEMP = "temp"
THUMBNAIL = "thumbnail"
UNAVAILABLE = "unavailable"

# Reasons, mainly used for log messages / tests.
REASON_CLASSIC = "classic"
REASON_SIGNED = "signed_temp_url"
REASON_PREVIEW_ONLY = "preview_only"
REASON_HAS_FULL_FALSE = "has_full_false"
REASON_DEFERRED = "deferred"
REASON_NOT_IMPORTED = "not_imported"
REASON_MISSING = "missing"

# Pawchive caps per-post file size by how many favourites the creator has; files
# above the cap are never imported, so retrying them is pointless.
_PAID_TIERS = (
    (250, 100 * 1024 * 1024),  # < 250 favourites  → 100 MB
    (5000, 1024 * 1024 * 1024),  # 250–5000        → 1 GB
)
_TOP_TIER_BYTES = 5 * 1024 * 1024 * 1024  # > 5000 favourites → 5 GB

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class FileSource:
    """Result of resolving one API file object."""

    url: Optional[str]
    kind: str
    reason: str
    #: ``True`` when *url* is a signed, time-limited link (``temp_url``).
    signed: bool = False
    #: ``True`` when the caller should append ``?f=<name>`` for a nicer filename.
    append_filename: bool = False

    @property
    def available(self) -> bool:
        return self.url is not None and self.kind != UNAVAILABLE

    @property
    def degraded(self) -> bool:
        """True when the bytes we can fetch are not full-resolution media."""
        return self.kind == THUMBNAIL or self.kind == UNAVAILABLE


def _parse_expiry(value: object) -> Optional[datetime]:
    """Parse ``temp_expires`` (ISO-8601, usually with ``+00:00``)."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def temp_url_is_usable(file_obj: object, now: Optional[datetime] = None) -> bool:
    """Return whether *file_obj* carries a ``temp_url`` that has not expired."""
    if not isinstance(file_obj, dict):
        return False
    url = file_obj.get("temp_url")
    if not url or not isinstance(url, str):
        return False
    expires = _parse_expiry(file_obj.get("temp_expires"))
    if expires is None:
        # No expiry advertised: assume the server will reject it if stale.
        return True
    now = now or datetime.now(timezone.utc)
    return expires > now


def is_deferred(file_obj: object) -> bool:
    """Return whether the API marked this file as not-yet-imported."""
    return isinstance(file_obj, dict) and file_obj.get("deferred") is True


def is_preview_only(file_obj: object) -> bool:
    """Return whether only a preview exists for this file."""
    return isinstance(file_obj, dict) and file_obj.get("preview_only") is True


def resolve_file(
    file_obj: object,
    domain_config: dict,
    post: Optional[object] = None,
    now: Optional[datetime] = None,
) -> FileSource:
    """Resolve one API file object into something we can download.

    Resolution order (first match wins):

    1. deferred / no path at all      → UNAVAILABLE (not imported yet)
    2. usable ``temp_url``            → TEMP (signed link)
    3. ``preview_only``               → THUMBNAIL
    4. ``post["has_full"] is False``  → THUMBNAIL
    5. ``path``                       → FULL (classic ``file.<domain>/data{path}``)

    Args:
        file_obj: the ``file`` object or one element of ``attachments``.
        domain_config: the domain config dict for the site being downloaded.
        post: optional parent post, used for the post-level ``has_full`` flag.
        now: injectable clock (tests only).
    """
    if not isinstance(file_obj, dict) or not file_obj:
        return FileSource(None, UNAVAILABLE, REASON_MISSING)

    name = str(file_obj.get("name") or "")
    path = file_obj.get("path")

    if is_deferred(file_obj):
        return FileSource(None, UNAVAILABLE, REASON_DEFERRED)
    if not path:
        # A named object with neither path nor temp_url has not been imported.
        if temp_url_is_usable(file_obj, now=now):
            return FileSource(
                str(file_obj["temp_url"]), TEMP, REASON_SIGNED, signed=True
            )
        return FileSource(None, UNAVAILABLE, REASON_NOT_IMPORTED)

    if temp_url_is_usable(file_obj, now=now):
        return FileSource(str(file_obj["temp_url"]), TEMP, REASON_SIGNED, signed=True)

    if is_preview_only(file_obj):
        return FileSource(
            to_thumbnail_url(str(path), domain_config),
            THUMBNAIL,
            REASON_PREVIEW_ONLY,
        )

    if isinstance(post, dict) and post.get("has_full") is False:
        return FileSource(
            to_thumbnail_url(str(path), domain_config),
            THUMBNAIL,
            REASON_HAS_FULL_FALSE,
        )

    url = clean_file_url(str(path), domain_config)
    return FileSource(
        url, FULL, REASON_CLASSIC, append_filename=bool(name) and "f=" not in url
    )


def resolve_thumbnail(file_obj: object, domain_config: dict) -> Optional[str]:
    """Return the thumbnail URL for a file object, or ``None``."""
    if not isinstance(file_obj, dict):
        return None
    path = file_obj.get("path")
    if not path:
        return None
    return to_thumbnail_url(str(path), domain_config)


def sha256_from_path(raw_path: object) -> Optional[str]:
    """Return the content SHA-256 encoded in a Pawchive/Kemono file path.

    File paths look like ``/ab/cd/<64 hex chars>.<ext>``; the final path segment
    *is* the SHA-256 of the file's bytes, which lets us verify or skip a download
    without reading the local file.
    """
    if not raw_path:
        return None
    text = str(raw_path)
    # Drop any query string (``?f=name``) and trailing slashes.
    text = text.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    stem = os.path.splitext(os.path.basename(text))[0].lower()
    return stem if _SHA256_RE.match(stem) else None


def size_cap_bytes(favorites: object) -> int:
    """Per-post file size cap (bytes) for a creator with *favorites* favourites.

    Pawchive states: <250 favourites → 100 MB, 250–5000 → 1 GB, >5000 → 5 GB.
    Unknown/invalid input gets the most generous cap so we never skip a file we
    could have downloaded.
    """
    try:
        count = int(favorites)
    except (TypeError, ValueError):
        return _TOP_TIER_BYTES
    if count < 0:
        return _TOP_TIER_BYTES
    for threshold, cap in _PAID_TIERS:
        if count < threshold:
            return cap
    return _TOP_TIER_BYTES


def human_size(num_bytes: int) -> str:
    """Format a byte count compactly (``100 MB``, ``1 GB``)."""
    try:
        value = float(num_bytes)
    except (TypeError, ValueError):
        return str(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.0f} {unit}" if value >= 10 else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.0f} TB"


def is_pending_post(post: object) -> bool:
    """Return whether the API says this post's files are still being imported."""
    return (
        isinstance(post, dict)
        and str(post.get("preview_state") or "").lower() == "pending"
    )


def is_scraped_post(post: object) -> bool:
    """Return whether the API says this post's files have been imported."""
    return (
        isinstance(post, dict)
        and str(post.get("preview_state") or "").lower() == "scraped"
    )


def compute_digests(path: str, chunk_size: int = 1024 * 256) -> tuple:
    """Return ``(md5_hex, sha256_hex)`` for a local file in a single read pass.

    The downloaders historically hashed the whole file with MD5; Pawchive file
    paths carry SHA-256 instead. Reading once and computing both avoids doubling
    disk I/O on large videos.
    """
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def expected_sha256_for_url(url: object) -> Optional[str]:
    """Return the SHA-256 a Pawchive URL claims for its content, if any.

    Works for classic (``/data/ab/cd/<sha>.<ext>``), thumbnail
    (``/thumbnail/data/...``) and signed (``t1.<domain>/f/<id>/<name>``) URLs —
    for the signed form the *name* is the real filename, so the hash is only
    available from classic/thumbnail paths, which is exactly what we want.
    """
    if not url:
        return None
    return sha256_from_path(url)


def verify_content_sha256(path: str, expected: Optional[str]) -> Optional[bool]:
    """Return whether *path* matches *expected*, or ``None`` when unverifiable."""
    expected = (expected or "").strip().lower()
    if not expected or not _SHA256_RE.match(expected):
        return None
    try:
        _, actual = compute_digests(path, chunk_size=1024 * 1024)
    except OSError:
        return None
    return actual == expected
