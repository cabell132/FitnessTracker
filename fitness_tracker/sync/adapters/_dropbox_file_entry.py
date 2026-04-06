"""Thin wrapper giving Dropbox :class:`FileMetadata` a ``FileEntry``-compatible shape."""

from __future__ import annotations

from datetime import UTC, datetime

from dropbox.files import FileMetadata


class DropboxFileEntry:
    """Adapts Dropbox ``FileMetadata`` to the ``FileEntry`` protocol."""

    def __init__(self, meta: FileMetadata) -> None:
        """Wrap a Dropbox file metadata object.

        Args:
            meta (FileMetadata): Dropbox SDK file metadata.
        """
        self._meta = meta

    @property
    def name(self) -> str:
        """Base filename of the export.

        Returns:
            str: The file name.
        """
        return self._meta.name

    @property
    def path_lower(self) -> str:
        """Lowercased full path used for download requests.

        Returns:
            str: The lowercased path.
        """
        return self._meta.path_lower

    @property
    def server_modified(self) -> datetime:
        """Server-side modification timestamp in UTC.

        Returns:
            datetime: When the file was last modified on the server.
        """
        return self._meta.server_modified.replace(tzinfo=UTC)
