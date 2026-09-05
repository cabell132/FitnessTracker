"""The additive migration retains existing rows and starts metadata as unknown."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect, text


def test_migration_preserves_rows_and_round_trips():
    path = Path("alembic/versions/8d52a71c903e_hevy_web_workout_metadata.py")
    spec = importlib.util.spec_from_file_location("hevy_web_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for table in ("HevyAppWorkout", "HevyAppWorkoutItem", "HevyAppSets"):
            model = Table(table, MetaData(), Column("id", Integer, primary_key=True))
            model.create(connection)
            connection.execute(model.insert().values(id=1))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.execute(
            text('SELECT completed_at, source_set_id FROM "HevyAppSets"')
        ).one() == (None, None)
        assert "web_payload" in {
            c["name"] for c in inspect(connection).get_columns("HevyAppWorkout")
        }
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert connection.execute(text('SELECT id FROM "HevyAppSets"')).scalar() == 1
        assert len(inspect(connection).get_columns("HevyAppSets")) == 1
