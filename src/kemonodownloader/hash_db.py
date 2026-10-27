"""SQLite-based file hash storage for deduplication.

Replaces the old file_hashes.json approach with a proper SQLite database
for better concurrent access, data integrity, and performance.
"""

import json
import os
import sqlite3
import threading
import time
from typing import Optional, Set, Tuple


class HashDB:
    """Thread-safe SQLite database for storing file hashes.

    Stores URL hashes mapped to file paths and content hashes
    to enable file deduplication across downloads.
    """

    DB_FILENAME = "file_hashes.db"

    def __init__(self, directory: str):
        """Initialise the hash database.

        Parameters
        ----------
        directory:
            Directory where the database file will be stored.
        """
        os.makedirs(directory, exist_ok=True)
        self.db_path = os.path.join(directory, self.DB_FILENAME)
        self._lock = threading.Lock()
        self._init_db()
        self._migrate_json(directory)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Create a new connection (one per call – safe for threads)."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create table if not yet present and run schema migrations."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS file_hashes (
                        url_hash   TEXT PRIMARY KEY,
                        file_path  TEXT NOT NULL,
                        file_hash  TEXT NOT NULL,
                        url        TEXT NOT NULL,
                        file_size  INTEGER NOT NULL DEFAULT 0,
                        content_sha256 TEXT
                    )
                    """
                )
                conn.commit()
                # Post-level processed log for metadata-level deduplication:
                # records which posts were fully downloaded so they are not
                # re-crawled on later runs.
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS processed_posts (
                        key        TEXT PRIMARY KEY,
                        service    TEXT NOT NULL,
                        creator_id TEXT NOT NULL,
                        post_id    TEXT NOT NULL,
                        url        TEXT,
                        timestamp  REAL NOT NULL DEFAULT 0
                    )
                    """
                )
                # Creator-level processed log used by the favorites sync to
                # skip artists that have already been fully downloaded.
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS processed_creators (
                        key        TEXT PRIMARY KEY,
                        service    TEXT NOT NULL,
                        creator_id TEXT NOT NULL,
                        url        TEXT,
                        timestamp  REAL NOT NULL DEFAULT 0
                    )
                    """
                )
                conn.commit()
                # Migrate: add file_size column for databases created before
                # this column existed.  PRAGMA table_info returns one row per
                # column; if file_size is absent we add it.
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(file_hashes)").fetchall()
                }
                if "file_size" not in columns:
                    conn.execute(
                        "ALTER TABLE file_hashes "
                        "ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0"
                    )
                    conn.commit()
                # SHA-256 of the file bytes. Pawchive/Kemono file paths encode
                # this hash, so storing it enables "already downloaded" checks
                # (and integrity verification) without re-reading a library.
                if "content_sha256" not in columns:
                    conn.execute(
                        "ALTER TABLE file_hashes ADD COLUMN content_sha256 TEXT"
                    )
                    conn.commit()
                # Indexes must be created *after* the migrations above, otherwise
                # opening a pre-content_sha256 database fails on the missing
                # column before it can be added.
                #
                # Content-hash index: Pawchive file paths encode the SHA-256 of
                # the file, so we can skip an already-downloaded file without
                # reading it. file_hash is MD5 for legacy rows, hence a lookup
                # simply finds nothing for those.
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_file_hashes_file_hash "
                    "ON file_hashes(file_hash)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_file_hashes_content_sha256 "
                    "ON file_hashes(content_sha256)"
                )
                conn.commit()
            finally:
                conn.close()

    def _migrate_json(self, directory: str) -> None:
        """One-time migration: import data from legacy ``file_hashes.json``."""
        json_path = os.path.join(directory, "file_hashes.json")
        if not os.path.exists(json_path):
            return
        try:
            with open(json_path, "r") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or not data:
                return
            with self._lock:
                conn = self._get_connection()
                try:
                    for url_hash, entry in data.items():
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO file_hashes
                            (url_hash, file_path, file_hash, url, file_size)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                url_hash,
                                entry.get("file_path", ""),
                                entry.get("file_hash", ""),
                                entry.get("url", ""),
                                entry.get("file_size", 0),
                            ),
                        )
                    conn.commit()
                finally:
                    conn.close()
            # Rename the old JSON so it is not re-imported
            backup_path = json_path + ".migrated"
            try:
                os.rename(json_path, backup_path)
            except OSError:
                pass
        except (json.JSONDecodeError, IOError, OSError):
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, url_hash: str) -> Optional[dict]:
        """Return the stored entry for *url_hash*, or ``None``.

        Returns a dict with keys ``file_path``, ``file_hash``, ``url``,
        ``file_size``.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT file_path, file_hash, url, file_size, content_sha256 "
                    "FROM file_hashes WHERE url_hash = ?",
                    (url_hash,),
                ).fetchone()
                if row:
                    return {
                        "file_path": row["file_path"],
                        "file_hash": row["file_hash"],
                        "url": row["url"],
                        "file_size": row["file_size"],
                        "content_sha256": row["content_sha256"],
                    }
                return None
            finally:
                conn.close()

    def store(
        self,
        url_hash: str,
        file_path: str,
        file_hash: str,
        url: str,
        file_size: int = 0,
        content_sha256: Optional[str] = None,
    ) -> None:
        """Insert or replace an entry.

        ``content_sha256`` is optional so every existing caller keeps working;
        when supplied it enables :meth:`has_content_hash` lookups.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO file_hashes
                    (url_hash, file_path, file_hash, url, file_size, content_sha256)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        url_hash,
                        file_path,
                        file_hash,
                        url,
                        file_size,
                        (content_sha256 or "").lower() or None,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def contains(self, url_hash: str) -> bool:
        """Check whether *url_hash* already exists."""
        return self.lookup(url_hash) is not None

    def has_content_hash(self, content_hash: str) -> bool:
        """Return whether a file with *content_hash* was already downloaded.

        Used for Pawchive-style paths whose final segment is the file's SHA-256:
        a match means the exact bytes already exist somewhere in the download
        tree, so the file can be skipped without hashing anything locally.
        """
        content_hash = (content_hash or "").strip().lower()
        if not content_hash:
            return False
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT 1 FROM file_hashes "
                    "WHERE lower(file_hash) = ? OR lower(content_sha256) = ? LIMIT 1",
                    (content_hash, content_hash),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def path_for_content_hash(self, content_hash: str) -> Optional[str]:
        """Return the stored file path for *content_hash*, or ``None``."""
        content_hash = (content_hash or "").strip().lower()
        if not content_hash:
            return None
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT file_path FROM file_hashes "
                    "WHERE lower(file_hash) = ? OR lower(content_sha256) = ? LIMIT 1",
                    (content_hash, content_hash),
                ).fetchone()
                return row["file_path"] if row else None
            finally:
                conn.close()

    def count(self) -> int:
        """Return total number of stored hashes."""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute("SELECT COUNT(*) AS cnt FROM file_hashes").fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    def all_entries(self) -> dict:
        """Return all entries as ``{url_hash: {file_path, file_hash, url, file_size}}``."""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT url_hash, file_path, file_hash, url, file_size "
                    "FROM file_hashes"
                ).fetchall()
                return {
                    row["url_hash"]: {
                        "file_path": row["file_path"],
                        "file_hash": row["file_hash"],
                        "url": row["url"],
                        "file_size": row["file_size"],
                    }
                    for row in rows
                }
            finally:
                conn.close()

    def delete(self, url_hash: str) -> None:
        """Remove a single entry by *url_hash*."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("DELETE FROM file_hashes WHERE url_hash = ?", (url_hash,))
                conn.commit()
            finally:
                conn.close()

    def clear(self) -> None:
        """Remove **all** entries."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("DELETE FROM file_hashes")
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Post / creator processed log (metadata-level deduplication)
    # ------------------------------------------------------------------

    @staticmethod
    def _post_key(service: str, creator_id: str, post_id: str) -> str:
        return f"{service}|{creator_id}|{post_id}"

    @staticmethod
    def _creator_key(service: str, creator_id: str) -> str:
        return f"{service}|{creator_id}"

    def mark_post_processed(
        self, service: str, creator_id: str, post_id: str, url: Optional[str] = None
    ) -> None:
        """Record that *post_id* was fully downloaded."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO processed_posts
                    (key, service, creator_id, post_id, url, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self._post_key(service, creator_id, post_id),
                        service,
                        creator_id,
                        post_id,
                        url,
                        time.time(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def is_post_processed(self, service: str, creator_id: str, post_id: str) -> bool:
        """Return ``True`` when *post_id* has already been processed."""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT 1 FROM processed_posts WHERE key = ?",
                    (self._post_key(service, creator_id, post_id),),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def mark_creator_processed(
        self, service: str, creator_id: str, url: Optional[str] = None
    ) -> None:
        """Record that *creator_id* was fully downloaded."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO processed_creators
                    (key, service, creator_id, url, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self._creator_key(service, creator_id),
                        service,
                        creator_id,
                        url,
                        time.time(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def is_creator_processed(self, service: str, creator_id: str) -> bool:
        """Return ``True`` when *creator_id* has already been processed."""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT 1 FROM processed_creators WHERE key = ?",
                    (self._creator_key(service, creator_id),),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def get_processed_creators(self) -> Set[Tuple[str, str]]:
        """Return the set of ``(service, creator_id)`` pairs already processed."""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT service, creator_id FROM processed_creators"
                ).fetchall()
                return {(row["service"], row["creator_id"]) for row in rows}
            finally:
                conn.close()
