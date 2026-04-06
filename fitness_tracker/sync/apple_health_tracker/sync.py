"""Apple Health CSV import from remote storage into the fitness tracker database."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fitness_tracker.sync.ports.health_export_store import HealthExportStore
from fitness_tracker.sync.ports.store_like import StoreLike


class AppleHealthToFitnessTrackerSyncronizer:
    """Imports Apple Health exports via a remote store into tracker tables."""

    def __init__(self, store: StoreLike, health_export: HealthExportStore) -> None:
        """Initiate the syncronizer with port-typed dependencies.

        Args:
            store (StoreLike): Persistence layer for Apple Health aggregates.
            health_export (HealthExportStore): Port for listing and downloading exports.
        """
        self._store = store
        self._health_export = health_export

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

    def sync_metrics(self) -> None:
        """Pull new metric CSVs from remote storage and load them into the database."""
        sync_datetimes = self.load_previous_sync_datetimes()
        target_datetime = sync_datetimes["Metrics"]

        new_files = self._health_export.list_csv_files_since(
            "/apps/health auto export/health auto export/Health App Data",
            target_datetime,
        )

        with self._store.unit_of_work() as uow:
            for file_entry in new_files:
                df = self._health_export.download_csv(file_entry.path_lower)
                if "Date" not in df.columns:
                    continue
                df = df.set_index("Date")
                uow.ah_add_data_records(df)

        sync_datetimes["Metrics"] = datetime.now(UTC)
        self.save_sync_datetimes(sync_datetimes)

        with self._store.unit_of_work() as uow:
            uow.insert_apple_health_metrics()

    def sync_workouts(self) -> None:
        """Pull new workout CSVs from remote storage and load them into the database."""
        sync_datetimes = self.load_previous_sync_datetimes()
        target_datetime = sync_datetimes["Workout"]

        new_files = self._health_export.list_csv_files_since(
            "/apps/health auto export/health auto export/Apple Workouts",
            target_datetime,
        )

        with self._store.unit_of_work() as uow:
            for file_entry in new_files:
                df = self._health_export.download_csv(file_entry.path_lower)
                uow.ah_add_workouts(df)

        sync_datetimes["Workout"] = datetime.now(UTC)
        self.save_sync_datetimes(sync_datetimes)
