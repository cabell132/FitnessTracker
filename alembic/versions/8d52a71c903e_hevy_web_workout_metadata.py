# ruff: noqa: INP001
"""Persist Hevy web workout identities, timing and response snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "8d52a71c903e"
down_revision = "e3b50fba4d21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable web metadata without changing existing identities."""
    op.add_column("HevyAppWorkout", sa.Column("web_payload", sa.JSON(), nullable=True))
    op.add_column(
        "HevyAppWorkout", sa.Column("web_fetched_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("HevyAppWorkoutItem", sa.Column("source_exercise_id", sa.String(), nullable=True))
    op.add_column("HevyAppWorkoutItem", sa.Column("rest_seconds", sa.Integer(), nullable=True))
    op.add_column("HevyAppSets", sa.Column("source_set_id", sa.String(), nullable=True))
    op.add_column(
        "HevyAppSets", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Remove web metadata while retaining the original workout records."""
    for table, columns in (
        ("HevyAppSets", ("completed_at", "source_set_id")),
        ("HevyAppWorkoutItem", ("rest_seconds", "source_exercise_id")),
        ("HevyAppWorkout", ("web_fetched_at", "web_payload")),
    ):
        for column in columns:
            op.drop_column(table, column)
