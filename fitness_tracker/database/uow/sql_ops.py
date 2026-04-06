"""Cross-schema SQL operations for UnitOfWork."""

from __future__ import annotations

from typing import Any

from fitness_tracker.database.uow.base import CrudMixin


class SqlOpsMixin(CrudMixin):
    """Named SQL file wrappers mixed into UnitOfWork."""

    def link_hevy_tracker_workout_items(self, true_coach_id: int) -> None:
        """Run SQL to link Hevy and tracker workout items.

        Args:
            true_coach_id (int): True Coach workout id scope.
        """
        self.execute_sql_file(
            "hevy/tracker/workout_items/update.sql",
            {"true_coach_id": true_coach_id},
        )

    def update_hevy_tracker_exercises(self, true_coach_id: int) -> None:
        """Bulk-update exercise associations for a workout.

        Args:
            true_coach_id (int): True Coach workout id scope.
        """
        self.execute_sql_file(
            "hevy/tracker/exercises/update.sql",
            {"true_coach_id": true_coach_id},
        )

    def update_hevy_tracker_sets(self, true_coach_id: int) -> None:
        """Run SQL to refresh set rows for a workout.

        Args:
            true_coach_id (int): True Coach workout id scope.
        """
        self.execute_sql_file(
            "hevy/tracker/sets/update.sql",
            {"true_coach_id": true_coach_id},
        )

    def insert_hevy_tracker_sets(self, true_coach_id: int) -> None:
        """Insert missing set rows from Hevy data.

        Args:
            true_coach_id (int): True Coach workout id scope.
        """
        self.execute_sql_file(
            "hevy/tracker/sets/insert.sql",
            {"true_coach_id": true_coach_id},
        )

    def insert_tc_tracker_workout_items(self) -> None:
        """Insert tracker workout items from True Coach data."""
        self.execute_sql_file("true_coach/tracker/workout_items/insert.sql")

    def insert_apple_health_metrics(self) -> None:
        """Materialize Apple Health metrics from staged data."""
        self.execute_sql_file("apple_health/metrics/insert.sql")

    def insert_hevy_calories_burned_metrics(self) -> None:
        """Insert calorie metrics derived from Hevy sync."""
        self.execute_sql_file("hevy/tracker/metric/calories_burned/insert.sql")

    def select_tracker_tc_assessments(self) -> list[Any]:
        """Run SQL to select tracker assessments for True Coach sync.

        Returns:
            list[Any]: Rows of assessment data as mappings.
        """
        result = self.execute_sql_file(
            "tracker/true_coach/assessments/select.sql",
        )
        return result.mappings().all()
