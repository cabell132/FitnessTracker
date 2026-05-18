"""Command line entry points for fitness-tracker maintenance tasks."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import urllib3
from sqlalchemy.engine import Engine

from fitness_tracker.apis import HevyAppClient
from fitness_tracker.config import Config
from fitness_tracker.database import Store
from fitness_tracker.database.config import create_database_engine
from fitness_tracker.maintenance.hevy_exercise_migration import (
    HevyExerciseTemplateMigrationService,
    MigrationError,
    MigrationPlan,
    MigrationResult,
)
from fitness_tracker.maintenance.hevy_template_ensure import (
    HevyTemplateEnsureService,
    TemplateEnsureError,
    TemplateEnsureResult,
)
from fitness_tracker.sync.adapters import HevyRoutineWriterAdapter
from fitness_tracker.sync_review import (
    SyncApplyError,
    SyncReviewError,
    TrueCoachToHevyReviewService,
    TrueCoachWorkoutBackfillDiscoveryService,
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
    if args.command == "hevy-templates" and args.hevy_templates_command == "ensure-from-plan":
        return _ensure_hevy_templates_from_plan(args)
    if args.command == "sync-review" and args.sync_review_command == "truecoach-to-hevy":
        return _sync_review_truecoach_to_hevy(args)
    if (
        args.command == "sync-review"
        and args.sync_review_command == "truecoach-workout-backfill-candidates"
    ):
        return _sync_review_truecoach_workout_backfill_candidates(args)
    if args.command == "sync-apply" and args.sync_apply_command == "truecoach-to-hevy":
        return _sync_apply_truecoach_to_hevy(args)
    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fitness-tracker")
    subparsers = parser.add_subparsers(dest="command")
    _add_hevy_parser(subparsers)
    _add_hevy_templates_parser(subparsers)
    _add_sync_review_parser(subparsers)
    _add_sync_apply_parser(subparsers)
    return parser


def _add_hevy_parser(subparsers: Any) -> None:
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


def _add_hevy_templates_parser(subparsers: Any) -> None:
    hevy_templates = subparsers.add_parser("hevy-templates")
    hevy_template_subparsers = hevy_templates.add_subparsers(dest="hevy_templates_command")

    ensure = hevy_template_subparsers.add_parser("ensure-from-plan")
    ensure.add_argument("plan_path")
    ensure.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    ensure.add_argument("--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL.")
    mode = ensure.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--yes", action="store_true")


def _add_sync_review_parser(
    subparsers: Any,
) -> None:
    sync_review = subparsers.add_parser("sync-review")
    sync_review_subparsers = sync_review.add_subparsers(dest="sync_review_command")

    truecoach_to_hevy = sync_review_subparsers.add_parser("truecoach-to-hevy")
    truecoach_to_hevy.add_argument("--workout-id", type=int, required=True)
    truecoach_to_hevy.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    truecoach_to_hevy.add_argument(
        "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
    )
    truecoach_to_hevy.add_argument(
        "--output-dir",
        default="reports",
        help="Report root. Defaults to reports.",
    )

    backfill_candidates = sync_review_subparsers.add_parser("truecoach-workout-backfill-candidates")
    backfill_candidates.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    backfill_candidates.add_argument(
        "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
    )
    backfill_candidates.add_argument(
        "--output-dir",
        default="reports",
        help="Report root. Defaults to reports.",
    )


def _add_sync_apply_parser(
    subparsers: Any,
) -> None:
    sync_apply = subparsers.add_parser("sync-apply")
    sync_apply_subparsers = sync_apply.add_subparsers(dest="sync_apply_command")

    truecoach_to_hevy = sync_apply_subparsers.add_parser("truecoach-to-hevy")
    truecoach_to_hevy.add_argument("--workout-id", type=int, required=True)
    truecoach_to_hevy.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    truecoach_to_hevy.add_argument(
        "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
    )
    truecoach_to_hevy.add_argument(
        "--output-dir",
        default="reports",
        help="Report root. Defaults to reports.",
    )
    truecoach_to_hevy.add_argument("--dry-run", action="store_true")


def _migrate_exercise_template(args: argparse.Namespace) -> int:
    engine = _engine_from_args(args)
    store = Store(engine)
    hevy = _hevy_client_from_config() if args.apply else None
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


def _ensure_hevy_templates_from_plan(args: argparse.Namespace) -> int:
    store = Store(_engine_from_args(args))
    hevy = None if args.dry_run else _hevy_client_from_config()
    service = HevyTemplateEnsureService(
        store=store,
        hevy_exercises=hevy.exercises if hevy is not None else None,
    )
    try:
        result = service.ensure_from_plan(Path(args.plan_path), dry_run=args.dry_run)
    except TemplateEnsureError as exc:
        _emit(f"Error: {exc}")
        return 2
    _print_template_ensure_result(result)
    return 0


def _engine_from_args(args: argparse.Namespace) -> Engine:
    database_url = args.database_url
    if database_url is None and args.db:
        database_url = f"sqlite:///{args.db}"
    return create_database_engine(database_url)


def _hevy_client_from_config() -> HevyAppClient:
    cfg = Config.from_env()
    return HevyAppClient(
        api_key=cfg.hevy_api_key.get_secret_value(),
        web_api_key=cfg.hevy_web_api_key.get_secret_value(),
    )


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


def _sync_review_truecoach_to_hevy(args: argparse.Namespace) -> int:
    store = Store(_engine_from_args(args))
    service = TrueCoachToHevyReviewService(store=store, output_root=Path(args.output_dir))
    try:
        bundle = service.write_review(args.workout_id)
    except SyncReviewError as exc:
        _emit(f"Error: {exc}")
        return 2
    _emit(f"Wrote sync review: {bundle.directory}")
    return 0


def _sync_review_truecoach_workout_backfill_candidates(args: argparse.Namespace) -> int:
    store = Store(_engine_from_args(args))
    service = TrueCoachWorkoutBackfillDiscoveryService(
        store=store,
        output_root=Path(args.output_dir),
    )
    bundle = service.write_report()
    _emit(f"Wrote backfill candidate report: {bundle.report_path}")
    return 0


def _sync_apply_truecoach_to_hevy(args: argparse.Namespace) -> int:
    store = Store(_engine_from_args(args))
    service = TrueCoachToHevyReviewService(store=store, output_root=Path(args.output_dir))
    try:
        if args.dry_run:
            result = service.write_apply_request(args.workout_id)
        else:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            result = service.apply(
                args.workout_id,
                routine_writer=HevyRoutineWriterAdapter(_hevy_client_from_config()),
            )
    except (SyncApplyError, SyncReviewError) as exc:
        _emit(f"Error: {exc}")
        return 2
    if args.dry_run:
        _emit(f"Wrote Hevy request dry-run: {result.request_path}")
    else:
        _emit(f"Created Hevy Routine from request: {result.request_path}")
    return 0


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


def _print_template_ensure_result(result: TemplateEnsureResult) -> None:
    for template in result.existing:
        _emit(f"Already exists: {template.title}")
    for template in result.would_create:
        _emit(f"Would create Hevy template: {template.title}")
    for template in result.created:
        _emit(f"Created Hevy template: {template.title}")
    if not (result.existing or result.would_create or result.created):
        _emit("No Hevy templates to create.")


def _emit(message: str) -> None:
    print(message)  # noqa: T201


if __name__ == "__main__":
    raise SystemExit(main())
