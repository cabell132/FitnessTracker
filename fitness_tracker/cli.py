"""Command line entry points for fitness-tracker maintenance tasks."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import urllib3
from sqlalchemy.engine import Engine

from fitness_tracker.apis import HevyAppClient
from fitness_tracker.database import Store
from fitness_tracker.database.config import create_database_engine
from fitness_tracker.maintenance.hevy_exercise_migration import (
    HevyExerciseTemplateMigrationService,
    MigrationError,
    MigrationPlan,
    MigrationResult,
)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv (list[str] | None): Optional argument list. Defaults to ``sys.argv``.

    Returns:
        int: Process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "hevy" and args.hevy_command == "migrate-exercise-template":
        return _migrate_exercise_template(args)
    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fitness-tracker")
    subparsers = parser.add_subparsers(dest="command")

    hevy = subparsers.add_parser("hevy")
    hevy_subparsers = hevy.add_subparsers(dest="hevy_command")

    migrate = hevy_subparsers.add_parser("migrate-exercise-template")
    migrate.add_argument("--from", dest="source_id", required=True)
    migrate.add_argument("--to", dest="target_id", required=True)
    migrate.add_argument("--db", help="SQLite database path. Prefer --database-url for new usage.")
    migrate.add_argument(
        "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
    )
    migrate.add_argument("--apply", action="store_true")
    migrate.add_argument("--force", action="store_true")
    migrate.add_argument("--limit", type=int)
    migrate.add_argument("--no-backup", action="store_true")
    migrate.add_argument("--report-path")
    return parser


def _migrate_exercise_template(args: argparse.Namespace) -> int:
    engine = _engine_from_args(args)
    store = Store(engine)
    hevy = HevyAppClient() if args.apply else None
    service = HevyExerciseTemplateMigrationService(
        store=store,
        hevy_workouts=hevy.workouts if hevy is not None else None,
    )

    try:
        if args.apply:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            result = service.apply(
                args.source_id,
                args.target_id,
                force=args.force,
                limit=args.limit,
                backup_path=_backup_path_for_engine(engine, no_backup=args.no_backup),
                report_path=_report_path(args.report_path),
            )
            _print_result(result)
        else:
            plan = service.plan(args.source_id, args.target_id, force=args.force)
            _print_plan(plan)
            _emit("\nDry run only. Re-run with --apply to update Hevy and the local DB.")
    except MigrationError as exc:
        _emit(f"Error: {exc}")
        return 2
    return 0


def _engine_from_args(args: argparse.Namespace) -> Engine:
    database_url = args.database_url
    if database_url is None and args.db:
        database_url = f"sqlite:///{args.db}"
    return create_database_engine(database_url)


def _backup_path_for_engine(engine: Engine, *, no_backup: bool) -> Path | None:
    if no_backup or engine.url.get_backend_name() != "sqlite":
        return None
    return _default_backup_path(engine.url.render_as_string(hide_password=False))


def _default_backup_path(database_url: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    db_name = Path(database_url.removeprefix("sqlite:///")).name
    return Path("reports") / "hevy_exercise_migrations" / f"{db_name}.{stamp}.bak"


def _report_path(value: str | None) -> Path | None:
    if value:
        return Path(value)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Path("reports") / "hevy_exercise_migrations" / f"{stamp}.json"


def _print_plan(plan: MigrationPlan) -> None:
    _emit("Hevy exercise template migration plan")
    _emit(f"From: {plan.source.name} ({plan.source.id})")
    _emit(f"To:   {plan.target.name} ({plan.target.id})")
    _emit(f"Type/equipment: {plan.source.type}/{plan.source.equipment}")
    _emit(f"Affected source items: {plan.affected_items}")
    _emit(f"Affected source workouts: {plan.affected_workouts}")
    _emit(
        "Target already has: "
        f"{plan.target_existing_items} items in {plan.target_existing_workouts} workouts"
    )
    _emit(f"Date range: {plan.first_start_time} -> {plan.last_start_time}")
    if plan.conflicts:
        _emit("\nWorkouts already containing both source and target:")
        for conflict in plan.conflicts:
            title = conflict.title.replace("\n", " / ")
            _emit(
                f"- {conflict.start_time} | {conflict.workout_id} | "
                f"source={conflict.source_items} target={conflict.target_items} | {title}"
            )


def _print_result(result: MigrationResult) -> None:
    _print_plan(result.plan)
    _emit("\nApplied migration")
    _emit(f"Hevy workouts updated: {len(result.api_updates)}")
    _emit(f"Local Hevy workout items updated: {result.db_workout_items_updated}")
    _emit(f"Tracker Exercise row updated: {result.tracker_exercise_id}")


def _emit(message: str) -> None:
    print(message)  # noqa: T201


if __name__ == "__main__":
    raise SystemExit(main())
