"""Minimal file metadata protocol for health export entries."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class FileEntry(Protocol):
    """Minimal file metadata -- only the fields the syncer actually reads."""

    @property
    def name(self) -> str:
        """Base filename of the export.

        Returns:
            str: The file name.
        """
        ...

    @property
    def path_lower(self) -> str:
        """Lowercased full path used for download requests.

        Returns:
            str: The lowercased path.
        """
        ...

    @property
    def server_modified(self) -> datetime:
        """Server-side modification timestamp.

        Returns:
            datetime: When the file was last modified on the server.
        """
        ...
