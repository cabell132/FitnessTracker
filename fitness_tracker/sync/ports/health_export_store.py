"""Port for listing and downloading health export CSV files from remote storage."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

import pandas as pd

from fitness_tracker.sync.ports.file_entry import FileEntry


@runtime_checkable
class HealthExportStore(Protocol):
    """List and download health export CSV files from a remote store."""

    def list_csv_files_since(self, folder_path: str, since: datetime) -> list[FileEntry]:
        """Return CSV file entries modified after ``since``.

        Args:
            folder_path (str): Remote folder to scan.
            since (datetime): Inclusive lower bound on modification time.

        Returns:
            list[FileEntry]: File entries for new or updated CSVs.
        """
        ...

    def download_csv(self, path: str) -> pd.DataFrame:
        """Download and parse a remote CSV into a DataFrame.

        Args:
            path (str): Remote file path (typically ``FileEntry.path_lower``).

        Returns:
            pd.DataFrame: Parsed CSV contents.
        """
        ...
