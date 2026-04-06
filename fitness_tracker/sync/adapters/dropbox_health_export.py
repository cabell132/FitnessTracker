"""Adapter wrapping Dropbox SDK behind :class:`HealthExportStore`."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

import pandas as pd
from dropbox import Dropbox
from dropbox.files import FileMetadata

from fitness_tracker.sync.adapters._dropbox_file_entry import DropboxFileEntry
from fitness_tracker.sync.ports.file_entry import FileEntry


class DropboxHealthExportAdapter:
    """Lists and downloads health export CSVs from Dropbox."""

    def __init__(self, client: Dropbox) -> None:
        """Wrap a Dropbox client for health export access.

        Args:
            client (Dropbox): Dropbox SDK client.
        """
        self._client = client

    def list_csv_files_since(self, folder_path: str, since: datetime) -> list[FileEntry]:
        """Return CSV file entries modified after ``since``.

        Args:
            folder_path (str): Dropbox folder path.
            since (datetime): Inclusive lower bound on modification time.

        Returns:
            list[FileEntry]: New or updated CSV file entries.
        """
        response = self._client.files_list_folder(folder_path, recursive=True)
        entries: list[FileEntry] = []

        while True:
            entries.extend(
                DropboxFileEntry(entry)
                for entry in response.entries
                if isinstance(entry, FileMetadata)
                and entry.name.endswith(".csv")
                and entry.server_modified.replace(tzinfo=UTC) > since
            )
            if not response.has_more:
                break
            response = self._client.files_list_folder_continue(response.cursor)

        return entries

    def download_csv(self, path: str) -> pd.DataFrame:
        """Download and parse a remote CSV into a DataFrame.

        Args:
            path (str): Remote file path.

        Returns:
            pd.DataFrame: Parsed CSV with ``Date`` normalised to naive UTC if present.
        """
        _, res = self._client.files_download(path)
        csv_content = res.content.decode("utf-8")
        df = pd.read_csv(StringIO(csv_content), index_col=False)

        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df["Date"] = (
                df["Date"]
                .dt.tz_localize("Europe/London", ambiguous="NaT", nonexistent="shift_forward")
                .dt.tz_convert("UTC")
            )
            df["Date"] = df["Date"].dt.tz_localize(None)

        return df
