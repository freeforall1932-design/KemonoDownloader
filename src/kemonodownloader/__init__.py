"""Kemono Downloader package.

``__version__`` is the single source of truth for the application version. It is
used by ``app.CURRENT_VERSION`` (window title, about text, update checker) and by
``download_policy.IDENTIFIABLE_USER_AGENT`` (the User-Agent we send to Pawchive),
so a version bump only has to happen here and in ``pyproject.toml``.
"""

__version__ = "5.14.0"
