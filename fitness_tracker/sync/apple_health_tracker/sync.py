"""Apple Health CSV import from Dropbox into the fitness tracker database."""

import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pandas as pd
from dropbox import Dropbox
from dropbox.files import FileMetadata
from sqlalchemy import text

from fitness_tracker.database import Database


class AppleHealthToFitnessTrackerSyncronizer:
    """Imports Apple Health exports via Dropbox into tracker tables."""

    def __init__(self, database: Database, source: Dropbox) -> None:
        """Initiate the syncronizer with the clients.

        Args:
            database (Database): Persistence layer for Apple Health aggregates.
            source (Dropbox): Dropbox client for listing and downloading exports.
        """
        self._database = database
        self._source = source

    def load_previous_sync_datetimes(self) -> dict[str, datetime]:
        """Load the previous sync datetime from the database.

        Returns:
            dict[str, datetime]: Last successful sync times per stream key.
        """
        file = Path("apple_health_sync_datetime.json")
        if file.exists():
            with file.open("r", encoding="utf-8") as f:
                sync_datetimes = json.load(f)
                return {k: datetime.fromisoformat(v) for k, v in sync_datetimes.items()}
        return {
            "Workout": datetime(2025, 2, 5, 14, 44, tzinfo=UTC),
            "Metrics": datetime(2025, 2, 10, 13, 59, tzinfo=UTC),
        }

    def save_sync_datetimes(self, sync_datetimes: dict[str, datetime]) -> None:
        """Save the sync datetimes to the database.

        Args:
            sync_datetimes (dict[str, datetime]): Per-stream checkpoints to persist.
        """
        path = Path("apple_health_sync_datetime.json")
        with path.open("w", encoding="utf-8") as f:
            json.dump({k: v.isoformat() for k, v in sync_datetimes.items()}, f)

    def get_new_files_since(self, folder_path: str, target_datetime: datetime) -> list[FileMetadata]:
        """List Dropbox CSV files modified after the given time.

        Args:
            folder_path (str): Dropbox folder path.
            target_datetime (datetime): Inclusive lower bound on ``server_modified``.

        Returns:
            list[FileMetadata]: New or updated CSV file metadata.
        """
        response = self._source.files_list_folder(folder_path, recursive=True)

        new_files: list[FileMetadata] = []

        while True:
            new_files.extend(
                entry
                for entry in response.entries
                if isinstance(entry, FileMetadata)
                and entry.name.endswith(".csv")
                and entry.server_modified > target_datetime
            )

            if not response.has_more:
                break

            response = self._source.files_list_folder_continue(response.cursor)

        return new_files

    def load_csv_from_dropbox(self, file_metadata: FileMetadata) -> pd.DataFrame:
        """Download a CSV from Dropbox and load it into a DataFrame.

        Args:
            file_metadata (FileMetadata): Dropbox file entry to download.

        Returns:
            pd.DataFrame: Parsed CSV; ``Date`` column normalized to naive UTC if present.
        """
        _, res = self._source.files_download(file_metadata.path_lower)
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

    def sync_metrics(self) -> None:
        """Pull new metric CSVs from Dropbox and load them into the database."""
        sync_datetimes = self.load_previous_sync_datetimes()
        target_datetime = sync_datetimes["Metrics"]

        new_files = self.get_new_files_since(
            "/apps/health auto export/health auto export/Health App Data", target_datetime
        )

        for file_metadata in new_files:
            df = self.load_csv_from_dropbox(file_metadata)
            if "Date" not in df.columns:
                continue
            df = df.set_index("Date")
            self._database.apple_health.add_data_records(df)

        sync_datetimes["Metrics"] = datetime.now(UTC)
        self.save_sync_datetimes(sync_datetimes)
        self.insert_metrics()

    def sync_workouts(self) -> None:
        """Pull new workout CSVs from Dropbox and load them into the database."""
        sync_datetimes = self.load_previous_sync_datetimes()
        target_datetime = sync_datetimes["Workout"]

        new_files = self.get_new_files_since(
            "/apps/health auto export/health auto export/Apple Workouts", target_datetime
        )

        for file_metadata in new_files:
            df = self.load_csv_from_dropbox(file_metadata)
            self._database.apple_health.add_workouts(df)

        sync_datetimes["Workout"] = datetime.now(UTC)
        self.save_sync_datetimes(sync_datetimes)

    def insert_metrics(self) -> None:
        """Run SQL to materialize Apple Health metrics from staged data."""
        sql_path = Path("fitness_tracker/database/SQL/apple_health/metrics/insert.sql")
        with self._database.apple_health.get_session() as session:
            session.execute(text(sql_path.read_text(encoding="utf-8")))
            session.commit()
