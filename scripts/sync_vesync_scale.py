# ruff: noqa: T201 - command-line status output contains counts only
"""Create the scale table if needed and reconcile VeSync history.

Run through Varlock so credentials stay in the child process environment:
``npm run env:run -- uv run --locked python -m scripts.sync_vesync_scale``.
"""

from __future__ import annotations

import os

from sqlalchemy import inspect

from fitness_tracker.apis.vesync import VeSyncClient
from fitness_tracker.database import Store
from fitness_tracker.database.config import create_database_engine
from fitness_tracker.database.models.vesync import VeSyncWeighIn
from fitness_tracker.sync.vesync import sync_vesync_weigh_ins


def main() -> None:
    """Add only the VeSync table, then import the primary profile's history.

    Raises:
        RuntimeError: If an existing table does not match the importer model.
    """
    engine = create_database_engine()
    table = VeSyncWeighIn.__table__
    inspector = inspect(engine)
    if inspector.has_table(table.name):
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        expected = {column.name for column in table.columns}
        if actual != expected:
            msg = "Existing VeSync table columns do not match the importer model"
            raise RuntimeError(msg)
    else:
        table.create(engine, checkfirst=True)

    athlete_mode = os.environ.get("VESYNC_ATHLETE_MODE", "false").lower() in {"true", "1"}
    result = sync_vesync_weigh_ins(
        Store(engine), VeSyncClient.from_env(), athlete_mode=athlete_mode
    )
    print(f"Scanned: {result.scanned}")
    print(f"Imported: {result.inserted}")
    print(f"Updated: {result.updated}")
    print(f"Other profiles excluded: {result.excluded}")
    print(f"Invalid readings skipped: {result.invalid}")


if __name__ == "__main__":
    main()
