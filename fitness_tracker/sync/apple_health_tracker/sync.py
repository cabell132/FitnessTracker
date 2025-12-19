import json
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
from dropbox import Dropbox
from dropbox.files import FileMetadata
from fitness_tracker.database import Database


class AppleHealthToFitnessTrackerSyncronizer:
    """Syncronizer class."""

    def __init__(self, database: Database, source: Dropbox) -> None:
        """Initiate the syncronizer with the clients."""
        self._database = database
        self._source = source

    def load_previous_sync_datetimes(self):
        """Load the previous sync datetime from the database."""
        file = Path("apple_health_sync_datetime.json")
        if file.exists():
            with file.open("r") as f:
                sync_datetimes = json.load(f)
                # convert strings back to datetime objects
                return {k: datetime.fromisoformat(v) for k, v in sync_datetimes.items()}
        return {"Workout": datetime(2025, 2, 5, 14, 44), "Metrics": datetime(2025, 2, 10, 13, 59)}

    def save_sync_datetimes(self, sync_datetimes: dict[str, datetime]):
        """Save the sync datetimes to the database."""
        with open("apple_health_sync_datetime.json", "w") as f:
            # convert datetime objects to strings before saving
            json.dump({k: v.isoformat() for k, v in sync_datetimes.items()}, f)

    def get_new_files_since(self, folder_path: str, target_datetime: datetime):
        # List files in the folder (recursive=True lists subfolders too)
        response = self._source.files_list_folder(folder_path, recursive=True)

        new_files = []

        while True:
            # Check each entry in the folder listing
            for entry in response.entries:
                if (
                    isinstance(entry, FileMetadata)
                    and entry.name.endswith(".csv")
                    and entry.server_modified > target_datetime
                ):
                    new_files.append(entry)

            # Check if there's more data to fetch
            if not response.has_more:
                break

            # Continue fetching if needed
            response = self._source.files_list_folder_continue(response.cursor)

        return new_files

    def load_csv_from_dropbox(self, file_metadata: FileMetadata):
        # Download the file
        _, res = self._source.files_download(file_metadata.path_lower)
        # Read content using pandas
        csv_content = res.content.decode("utf-8")  # Decode bytes to string
        df = pd.read_csv(StringIO(csv_content), index_col=False)

        # Convert 'Date' column from UK time to UTC if present

        if "Date" in df.columns:
            # Parse as Europe/London, then convert to UTC
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df["Date"] = (
                df["Date"]
                .dt.tz_localize("Europe/London", ambiguous="NaT", nonexistent="shift_forward")
                .dt.tz_convert("UTC")
            )
            # If you want to remove the tzinfo and keep naive UTC datetimes:
            df["Date"] = df["Date"].dt.tz_localize(None)

        return df

    def sync_metrics(self):
        # Load the previous sync datetime
        sync_datetimes = self.load_previous_sync_datetimes()
        target_datetime = sync_datetimes["Metrics"]

        # Get new files since the target datetime
        new_files = self.get_new_files_since(
            "/apps/health auto export/health auto export/Health App Data", target_datetime
        )

        # Load and process each new file
        for file_metadata in new_files:
            df = self.load_csv_from_dropbox(file_metadata)
            if "Date" not in df.columns:
                continue
            df = df.set_index("Date")
            self._database.apple_health.add_data_records(df)

        # Update the sync datetime
        sync_datetimes["Metrics"] = datetime.now()
        self.save_sync_datetimes(sync_datetimes)
        self.insert_metrics()

    def sync_workouts(self):
        # Load the previous sync datetime
        sync_datetimes = self.load_previous_sync_datetimes()
        target_datetime = sync_datetimes["Workout"]

        # Get new files since the target datetime
        new_files = self.get_new_files_since(
            "/apps/health auto export/health auto export/Apple Workouts", target_datetime
        )

        # Load and process each new file
        for file_metadata in new_files:
            df = self.load_csv_from_dropbox(file_metadata)
            self._database.apple_health.add_workouts(df)

        # Update the sync datetime
        sync_datetimes["Workout"] = datetime.now()
        self.save_sync_datetimes(sync_datetimes)

    def insert_metrics(self):
        """Insert the metrics into the database."""
        with self._database.apple_health.get_session() as session:
            query = Path("fitness_tracker/database/SQL/apple_health/metrics/insert.sql").read_text()
            session.execute(query)
            session.commit()
