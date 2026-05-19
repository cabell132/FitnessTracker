"""Command line entry points for fitness-tracker maintenance tasks."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, get_args

import requests
import urllib3
from rapidfuzz import fuzz, process
from sqlalchemy import text
from sqlalchemy.engine import Engine

from fitness_tracker.apis import HevyAppClient, TrueCoachClient
from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.hevy_app.types import (
    PostRoutineFolderRequest,
    PostRoutineFolderRequestBody,
    PostRoutinesRequestBody,
    PutRoutinesRequestBody,
)
from fitness_tracker.apis.hevy_app.types.common import (
    CUSTOM_EXERCISE_TYPES,
    EQUIPMENT_CATEGORIES,
    MUSCLE_GROUPS,
)
from fitness_tracker.apis.true_coach.types import Workout, WorkoutResponse
from fitness_tracker.apis.true_coach.workouts import WorkoutState
from fitness_tracker.config import Config
from fitness_tracker.database import Store
from fitness_tracker.database.config import create_database_engine
from fitness_tracker.database.models import Exercise as TrackerExercise
from fitness_tracker.database.models.hevy_app import HevyAppExercise
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
from fitness_tracker.sync.adapters import (
    HevyRoutineWriterAdapter,
    HevyWorkoutWriterAdapter,
    TrueCoachWorkoutItemWriterAdapter,
)
from fitness_tracker.sync.true_coach_tracker.sync import TrueCoachToFitnessTrackerSyncronizer
from fitness_tracker.sync_review import (
    HevyToTrueCoachResultApplyError,
    HevyToTrueCoachResultApplyResult,
    HevyToTrueCoachResultReviewBundle,
    HevyToTrueCoachResultReviewError,
    HevyToTrueCoachResultReviewService,
    SyncApplyError,
    SyncReviewError,
    TrueCoachToHevyReviewService,
    TrueCoachWorkoutBackfillDiscoveryService,
    TrueCoachWorkoutBackfillReviewService,
    WorkoutBackfillApplyError,
    WorkoutBackfillReviewError,
)
from fitness_tracker.sync_review.true_coach_to_hevy import ApplyResult, _build_hevy_routine_request

TRUECOACH_OPERATIONAL_STATES: tuple[WorkoutState, ...] = ("pending", "completed", "missed")


def main(argv: list[str] | None = None) -> int:  # noqa: C901, PLR0911, PLR0912, PLR0915
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
    if args.command == "hevy" and args.hevy_command == "routines":
        return _hevy_routines(args)
    if args.command == "hevy" and args.hevy_command == "workouts":
        return _hevy_workouts(args)
    if args.command == "hevy" and args.hevy_command == "routine-folders":
        return _hevy_routine_folders(args)
    if args.command == "hevy" and args.hevy_command == "exercise-templates":
        handler = _hevy_exercise_template_command_handler(args.exercise_templates_command)
        if handler is not None:
            return handler(args)
    if args.command == "truecoach" and args.truecoach_command == "due":
        return _truecoach_due(args)
    if args.command == "truecoach" and args.truecoach_command == "import-recent":
        return _truecoach_import_recent(args)
    if args.command == "truecoach" and args.truecoach_command == "workouts":
        return _truecoach_workouts(args)
    if args.command == "exercise-links" and args.exercise_links_command == "set":
        return _set_exercise_link(args)
    if args.command == "sync-review" and args.sync_review_command == "truecoach-to-hevy":
        return _sync_review_truecoach_to_hevy(args)
    if args.command == "sync-review" and args.sync_review_command == "hevy-to-truecoach-results":
        return _sync_review_hevy_to_truecoach_results(args)
    if (
        args.command == "sync-review"
        and args.sync_review_command == "truecoach-workout-backfill-candidates"
    ):
        return _sync_review_truecoach_workout_backfill_candidates(args)
    if args.command == "sync-review" and args.sync_review_command == "truecoach-workout-backfill":
        return _sync_review_truecoach_workout_backfill(args)
    if (
        args.command == "sync-review"
        and args.sync_review_command == "truecoach-workout-backfill-inspect"
    ):
        return _sync_review_truecoach_workout_backfill_inspect(args)
    if (
        args.command == "sync-review"
        and args.sync_review_command == "truecoach-workout-backfill-evidence"
    ):
        return _sync_review_truecoach_workout_backfill_evidence(args)
    if (
        args.command == "sync-review"
        and args.sync_review_command == "truecoach-workout-backfill-diff"
    ):
        return _sync_review_truecoach_workout_backfill_diff(args)
    if args.command == "sync-apply" and args.sync_apply_command == "truecoach-to-hevy":
        return _sync_apply_truecoach_to_hevy(args)
    if args.command == "sync-apply" and args.sync_apply_command == "hevy-to-truecoach-results":
        return _sync_apply_hevy_to_truecoach_results(args)
    if args.command == "sync-apply" and args.sync_apply_command == "truecoach-workout-backfill":
        return _sync_apply_truecoach_workout_backfill(args)
    if (
        args.command == "sync-apply"
        and args.sync_apply_command == "truecoach-workout-backfill-repair"
    ):
        return _sync_apply_truecoach_workout_backfill_repair(args)
    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fitness-tracker")
    subparsers = parser.add_subparsers(dest="command")
    _add_hevy_parser(subparsers)
    _add_truecoach_parser(subparsers)
    _add_exercise_links_parser(subparsers)
    _add_sync_review_parser(subparsers)
    _add_sync_apply_parser(subparsers)
    return parser


def _add_hevy_parser(subparsers: Any) -> None:  # noqa: PLR0915
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

    routines = hevy_subparsers.add_parser("routines")
    routine_subparsers = routines.add_subparsers(dest="routine_command")

    find = routine_subparsers.add_parser("find")
    find.add_argument("--title", required=True)
    _add_json_output_argument(find)

    inspect = routine_subparsers.add_parser("inspect")
    inspect.add_argument("routine_id")
    _add_json_output_argument(inspect)

    delete = routine_subparsers.add_parser("delete")
    delete.add_argument("routine_id")
    delete.add_argument("--yes", action="store_true", required=True)
    _add_json_output_argument(delete)

    create = routine_subparsers.add_parser("create-from-json")
    create.add_argument("request_path")
    create.add_argument("--response-path")
    _add_json_output_argument(create)

    update = routine_subparsers.add_parser("update-from-json")
    update.add_argument("routine_id")
    update.add_argument("request_path")
    update.add_argument("--response-path")
    update.add_argument(
        "--notes-if-empty",
        default="Updated from JSON.",
        help="Routine notes to use when the JSON has an empty notes field.",
    )
    _add_json_output_argument(update)

    diff = routine_subparsers.add_parser("diff-json")
    diff.add_argument("routine_id")
    diff.add_argument("request_path")
    diff.add_argument("--output-path")
    diff.add_argument("--include-low-signal", action="store_true")

    workouts = hevy_subparsers.add_parser("workouts")
    workout_subparsers = workouts.add_subparsers(dest="workout_command")

    workout_inspect = workout_subparsers.add_parser("inspect")
    workout_inspect.add_argument("workout_id")
    _add_json_output_argument(workout_inspect)

    folders = hevy_subparsers.add_parser("routine-folders")
    folder_subparsers = folders.add_subparsers(dest="routine_folder_command")

    ensure = folder_subparsers.add_parser("ensure")
    ensure.add_argument("--title", required=True)
    _add_json_output_argument(ensure)

    _add_hevy_exercise_templates_parser(hevy_subparsers)


def _add_json_output_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a single strict JSON document on stdout.",
    )


def _add_hevy_exercise_templates_parser(subparsers: Any) -> None:  # noqa: PLR0915
    exercise_templates = subparsers.add_parser("exercise-templates")
    exercise_template_subparsers = exercise_templates.add_subparsers(
        dest="exercise_templates_command"
    )

    ensure = exercise_template_subparsers.add_parser("ensure-from-plan")
    ensure.add_argument("plan_path")
    ensure.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    ensure.add_argument("--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL.")
    mode = ensure.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--yes", action="store_true")

    create = exercise_template_subparsers.add_parser("create")
    create.add_argument("--title", required=True)
    create.add_argument(
        "--type", dest="expected_type", required=True, choices=get_args(CUSTOM_EXERCISE_TYPES)
    )
    create.add_argument(
        "--equipment",
        dest="equipment_category",
        required=True,
        choices=get_args(EQUIPMENT_CATEGORIES),
    )
    create.add_argument(
        "--muscle-group",
        required=True,
        choices=get_args(MUSCLE_GROUPS),
    )
    create.add_argument(
        "--other-muscle",
        dest="other_muscles",
        action="append",
        default=[],
        choices=get_args(MUSCLE_GROUPS),
    )
    create.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    create.add_argument("--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL.")
    create_mode = create.add_mutually_exclusive_group(required=True)
    create_mode.add_argument("--dry-run", action="store_true")
    create_mode.add_argument("--yes", action="store_true")

    find = exercise_template_subparsers.add_parser("find")
    find.add_argument("--title", required=True)

    fuzzy_find = exercise_template_subparsers.add_parser("fuzzy-find")
    fuzzy_find.add_argument("--title", required=True)
    fuzzy_find.add_argument("--limit", type=int, default=10)
    fuzzy_find.add_argument("--min-score", type=float, default=55.0)


def _hevy_exercise_template_command_handler(
    command: str | None,
) -> Callable[[argparse.Namespace], int] | None:
    if command is None:
        return None
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "ensure-from-plan": _ensure_hevy_templates_from_plan,
        "create": _create_hevy_template,
        "find": _find_hevy_templates,
        "fuzzy-find": _fuzzy_find_hevy_templates,
    }
    return handlers.get(command)


def _add_truecoach_parser(subparsers: Any) -> None:
    truecoach = subparsers.add_parser("truecoach")
    truecoach_subparsers = truecoach.add_subparsers(dest="truecoach_command")

    _add_truecoach_due_parser(truecoach_subparsers.add_parser("due"))

    _add_truecoach_import_recent_parser(truecoach_subparsers.add_parser("import-recent"))

    workouts = truecoach_subparsers.add_parser("workouts")
    workout_subparsers = workouts.add_subparsers(dest="truecoach_workout_command")

    workout_list = workout_subparsers.add_parser("list")
    workout_list.add_argument(
        "--state",
        dest="states",
        action="append",
        choices=TRUECOACH_OPERATIONAL_STATES,
        default=[],
    )
    workout_list.add_argument("--limit", type=int, default=20)
    workout_list.add_argument("--page", type=int, default=1)
    workout_list.add_argument("--order", choices=("asc", "desc"), default="asc")
    _add_json_output_argument(workout_list)

    workout_inspect = workout_subparsers.add_parser("inspect")
    workout_inspect.add_argument("--workout-id", type=int, required=True)
    workout_inspect.add_argument("--raw", action="store_true")
    _add_json_output_argument(workout_inspect)

    _add_truecoach_due_parser(workout_subparsers.add_parser("due"))

    _add_truecoach_import_recent_parser(workout_subparsers.add_parser("import-recent"))


def _add_truecoach_due_parser(due: argparse.ArgumentParser) -> None:
    due.add_argument("--date", required=True)
    due.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    due.add_argument("--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL.")
    _add_json_output_argument(due)


def _add_truecoach_import_recent_parser(import_recent: argparse.ArgumentParser) -> None:
    import_recent.add_argument("--pages", type=int, default=1)
    import_recent.add_argument("--per-page", type=int, default=20)
    import_recent.add_argument("--order", choices=("asc", "desc"), default="desc")
    import_recent.add_argument(
        "--state",
        dest="states",
        action="append",
        choices=TRUECOACH_OPERATIONAL_STATES,
        help="State to import. May be repeated. Defaults to all operational states.",
    )
    import_recent.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    import_recent.add_argument(
        "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
    )
    _add_json_output_argument(import_recent)


def _add_exercise_links_parser(subparsers: Any) -> None:
    exercise_links = subparsers.add_parser("exercise-links")
    exercise_links_subparsers = exercise_links.add_subparsers(dest="exercise_links_command")

    set_link = exercise_links_subparsers.add_parser("set")
    set_link.add_argument("--truecoach-exercise-id", type=int, required=True)
    set_link.add_argument("--hevy-template-id", required=True)
    set_link.add_argument("--name")
    set_link.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    set_link.add_argument(
        "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
    )


def _add_sync_review_parser(  # noqa: PLR0915
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
    truecoach_to_hevy.add_argument("--summary", action="store_true")

    hevy_to_truecoach_results = sync_review_subparsers.add_parser("hevy-to-truecoach-results")
    hevy_to_truecoach_results.add_argument("--workout-id", required=True)
    hevy_to_truecoach_results.add_argument(
        "--db", help="SQLite database path. Prefer --database-url."
    )
    hevy_to_truecoach_results.add_argument(
        "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
    )
    hevy_to_truecoach_results.add_argument(
        "--output-dir",
        default="reports",
        help="Report root. Defaults to reports.",
    )
    hevy_to_truecoach_results.add_argument(
        "--decisions",
        help="Editable Hevy to True Coach result decisions JSON to validate.",
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

    backfill_review = sync_review_subparsers.add_parser("truecoach-workout-backfill")
    backfill_review.add_argument("--workout-id", type=int, required=True)
    backfill_review.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    backfill_review.add_argument(
        "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
    )
    backfill_review.add_argument(
        "--output-dir",
        default="reports",
        help="Report root. Defaults to reports.",
    )
    backfill_review.add_argument(
        "--decisions",
        help="Editable Workout backfill decisions JSON to validate and apply to the draft request.",
    )

    for command in (
        "truecoach-workout-backfill-inspect",
        "truecoach-workout-backfill-evidence",
        "truecoach-workout-backfill-diff",
    ):
        helper = sync_review_subparsers.add_parser(command)
        helper.add_argument("--workout-id", type=int, required=True)
        helper.add_argument("--db", help="SQLite database path. Prefer --database-url.")
        helper.add_argument(
            "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
        )
        helper.add_argument(
            "--output-dir",
            default="reports",
            help="Report root. Defaults to reports.",
        )
        helper.add_argument(
            "--decisions",
            help="Editable Workout backfill decisions JSON to validate and apply.",
        )


def _add_sync_apply_parser(  # noqa: PLR0915
    subparsers: Any,
) -> None:
    sync_apply = subparsers.add_parser("sync-apply")
    sync_apply_subparsers = sync_apply.add_subparsers(dest="sync_apply_command")

    hevy_to_truecoach_results = sync_apply_subparsers.add_parser("hevy-to-truecoach-results")
    hevy_to_truecoach_results.add_argument("--workout-id", required=True)
    hevy_to_truecoach_results.add_argument(
        "--db", help="SQLite database path. Prefer --database-url."
    )
    hevy_to_truecoach_results.add_argument(
        "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
    )
    hevy_to_truecoach_results.add_argument(
        "--output-dir",
        default="reports",
        help="Report root. Defaults to reports.",
    )
    hevy_to_truecoach_results.add_argument(
        "--decisions",
        help="Editable Hevy to True Coach result decisions JSON to apply to the request.",
    )
    hevy_to_truecoach_results.add_argument("--dry-run", action="store_true")
    hevy_to_truecoach_results.add_argument("--yes", action="store_true")

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
    truecoach_to_hevy.add_argument("--manual-request")
    truecoach_to_hevy.add_argument("--response-path")
    truecoach_to_hevy.add_argument(
        "--down-regulate-duration",
        type=int,
        help="Patch empty Down Regulate items with this duration in seconds.",
    )
    truecoach_to_hevy.add_argument(
        "--folder-id",
        help="Routine folder id to include when creating or writing the Hevy request.",
    )

    workout_backfill = sync_apply_subparsers.add_parser("truecoach-workout-backfill")
    workout_backfill.add_argument("--workout-id", type=int, required=True)
    workout_backfill.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    workout_backfill.add_argument(
        "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
    )
    workout_backfill.add_argument(
        "--output-dir",
        default="reports",
        help="Report root. Defaults to reports.",
    )
    workout_backfill.add_argument(
        "--decisions",
        help="Editable Workout backfill decisions JSON to validate and apply to the request.",
    )
    workout_backfill.add_argument("--dry-run", action="store_true")
    workout_backfill.add_argument("--manual-request")

    workout_backfill_repair = sync_apply_subparsers.add_parser("truecoach-workout-backfill-repair")
    workout_backfill_repair.add_argument("--workout-id", type=int, required=True)
    workout_backfill_repair.add_argument(
        "--db", help="SQLite database path. Prefer --database-url."
    )
    workout_backfill_repair.add_argument(
        "--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL."
    )
    workout_backfill_repair.add_argument(
        "--output-dir",
        default="reports",
        help="Report root. Defaults to reports.",
    )
    workout_backfill_repair.add_argument(
        "--decisions",
        help="Editable Workout backfill decisions JSON to validate and apply to the request.",
    )


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


def _create_hevy_template(args: argparse.Namespace) -> int:
    store = Store(_engine_from_args(args))
    hevy = None if args.dry_run else _hevy_client_from_config()
    service = HevyTemplateEnsureService(
        store=store,
        hevy_exercises=hevy.exercises if hevy is not None else None,
    )
    try:
        result = service.create_template(
            title=args.title,
            expected_type=args.expected_type,
            equipment_category=args.equipment_category,
            muscle_group=args.muscle_group,
            other_muscles=tuple(args.other_muscles),
            dry_run=args.dry_run,
        )
    except TemplateEnsureError as exc:
        _emit(f"Error: {exc}")
        return 2
    _print_template_ensure_result(result)
    return 0


def _find_hevy_templates(args: argparse.Namespace) -> int:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        templates = _find_remote_hevy_templates(args.title)
    except HevyAppAPIError as exc:
        _emit(f"Error: {exc}")
        return 2
    if not templates:
        _emit("No matching Hevy templates.")
        return 0
    for template in templates:
        _emit(
            " | ".join(
                (
                    str(template.get("id")),
                    str(template.get("title")),
                    str(template.get("type")),
                    str(template.get("equipment")),
                    str(template.get("primary_muscle_group")),
                )
            )
        )
    return 0


def _fuzzy_find_hevy_templates(args: argparse.Namespace) -> int:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        templates = _hevy_api_pages("/exercise_templates", "exercise_templates", page_size=100)
    except HevyAppAPIError as exc:
        _emit(f"Error: {exc}")
        return 2
    by_title = {str(template.get("title", "")): template for template in templates}
    matches = process.extract(args.title, by_title.keys(), scorer=fuzz.WRatio, limit=args.limit)
    emitted = False
    for title, score, _ in matches:
        if float(score) < args.min_score:
            continue
        template = by_title[title]
        _emit(
            f"{float(score):.1f} | {template.get('id')} | {title} | "
            f"{template.get('type')} | {template.get('equipment')} | "
            f"{template.get('primary_muscle_group')}"
        )
        emitted = True
    if not emitted:
        _emit("No fuzzy Hevy template matches.")
    return 0


def _set_exercise_link(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    hevy = HevyAppClient(
        api_key=cfg.hevy_api_key.get_secret_value(),
        web_api_key=cfg.hevy_web_api_key.get_secret_value(),
    )
    store = Store(_engine_from_args(args), hevy_client=hevy)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    with store.unit_of_work() as uow:
        template = (
            uow.session.query(HevyAppExercise).filter_by(id=args.hevy_template_id).one_or_none()
        )
        if template is None:
            remote = hevy.exercises.get_template(args.hevy_template_id)
            if remote is None:
                _emit(f"Error: Hevy template not found: {args.hevy_template_id}")
                return 2
            uow.hevy.add_exercise(remote)
            uow.session.flush()
            template = (
                uow.session.query(HevyAppExercise).filter_by(id=args.hevy_template_id).one_or_none()
            )
        tracker = (
            uow.session.query(TrackerExercise)
            .filter_by(true_coach_id=args.truecoach_exercise_id)
            .one_or_none()
        )
        if tracker is None:
            tracker = TrackerExercise(
                name=args.name
                or (template.name if template is not None else args.hevy_template_id),
                true_coach_id=args.truecoach_exercise_id,
            )
            uow.session.add(tracker)
            uow.session.flush()
        tracker.hevy_app_id = args.hevy_template_id
        _emit(
            f"Linked TrueCoach exercise {args.truecoach_exercise_id} "
            f"to Hevy template {args.hevy_template_id}"
        )
    return 0


def _truecoach_due(args: argparse.Namespace) -> int:
    engine = _engine_from_args(args)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, title, due, state, rest_day
                FROM "TrueCoachWorkout"
                WHERE date(due) = :target_date
                ORDER BY due, id
                """
            ),
            {"target_date": args.date},
        ).fetchall()
    if args.json:
        return _emit_json_result(
            {
                "ok": True,
                "date": args.date,
                "workouts": [_truecoach_due_row_payload(row) for row in rows],
                "warnings": [],
            }
        )
    if not rows:
        _emit(f"No True Coach Workouts due on {args.date}.")
        return 0
    _emit("id | title | due | state | rest_day")
    for row in rows:
        _emit(" | ".join(str(value) for value in row))
    return 0


def _truecoach_workouts(args: argparse.Namespace) -> int:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    if args.truecoach_workout_command == "list":
        return _truecoach_workouts_list(args)
    if args.truecoach_workout_command == "inspect":
        return _truecoach_workouts_inspect(args)
    if args.truecoach_workout_command == "due":
        return _truecoach_due(args)
    if args.truecoach_workout_command == "import-recent":
        return _truecoach_import_recent(args)
    return _emit_error(args, "missing truecoach workouts subcommand")


def _truecoach_workouts_list(args: argparse.Namespace) -> int:
    client = _truecoach_client_from_config()
    response = client.workouts.get(
        order=args.order,
        page=args.page,
        per_page=args.limit,
        states=_truecoach_workout_list_states(args.states),
    )
    payload = _truecoach_workout_response_payload(response)
    if args.json:
        return _emit_json_result(payload)
    if response is None:
        return 0
    for workout in response.workouts:
        _emit(
            f"{workout.id} | {workout.due} | {workout.state} | "
            f"{workout.title} | rest_day={workout.rest_day}"
        )
    return 0


def _truecoach_workouts_inspect(args: argparse.Namespace) -> int:
    client = _truecoach_client_from_config()
    if args.raw:
        payload = {
            "ok": True,
            "raw": client.workouts.inspect_raw(args.workout_id),
            "warnings": [],
        }
        return _emit_json_result(payload)
    response = client.workouts.inspect(args.workout_id)
    if response is None:
        return _emit_error(args, f"True Coach Workout not found: {args.workout_id}", exit_code=2)
    payload = _truecoach_workout_inspect_payload(response)
    if args.json:
        return _emit_json_result(payload)
    workout = payload["workout"]
    _emit(
        f"{workout['id']} | {workout['due']} | {workout['state']} | "
        f"{workout['title']} | rest_day={workout['rest_day']}"
    )
    for item in payload["workout_items"]:
        _emit(f"{item['id']} | {item['position']} | {item['state']} | {item['name']}")
    return 0


def _truecoach_import_recent(args: argparse.Namespace) -> int:  # noqa: PLR0915
    client = _truecoach_client_from_config()
    store = Store(_engine_from_args(args))
    syncer = TrueCoachToFitnessTrackerSyncronizer(store=store, source=client)
    states = cast(list[WorkoutState], args.states or list(TRUECOACH_OPERATIONAL_STATES))
    imported_workouts = 0
    imported_items = 0
    imported_pages = 0
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    for page in range(1, args.pages + 1):
        response = client.workouts.get(
            order=args.order,
            page=page,
            per_page=args.per_page,
            states=states,
        )
        if response is None:
            if not args.json:
                _emit(f"page {page}: empty response")
            break
        syncer.sync_workouts(response)
        imported_pages += 1
        imported_workouts += len(response.workouts)
        imported_items += len(response.workout_items)
        if not args.json:
            _emit(
                f"page {page}/{response.meta.total_pages}: "
                f"workouts={len(response.workouts)} items={len(response.workout_items)}"
            )
        if page >= response.meta.total_pages:
            break
    if args.json:
        return _emit_json_result(
            {
                "ok": True,
                "imported_pages": imported_pages,
                "imported_workouts": imported_workouts,
                "imported_items": imported_items,
                "warnings": [],
            }
        )
    _emit(
        f"imported_pages={imported_pages} "
        f"imported_workouts={imported_workouts} imported_items={imported_items}"
    )
    return 0


def _truecoach_client_from_config() -> TrueCoachClient:
    cfg = Config.from_env()
    return TrueCoachClient(
        email=cfg.email,
        password=cfg.truecoach_password.get_secret_value(),
    )


def _truecoach_workout_list_states(states: list[WorkoutState]) -> WorkoutState | list[WorkoutState]:
    if len(states) == 1:
        return states[0]
    if states:
        return states
    return "pending"


def _truecoach_workout_response_payload(response: WorkoutResponse | None) -> dict[str, Any]:
    if response is None:
        return {
            "ok": True,
            "workouts": [],
            "workout_items": [],
            "comments": [],
            "meta": None,
            "warnings": [],
        }
    return {
        "ok": True,
        "workouts": [_truecoach_workout_payload(workout) for workout in response.workouts],
        **_truecoach_related_workout_payload(response),
        "warnings": [],
    }


def _truecoach_due_row_payload(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "title": row[1],
        "due": str(row[2]),
        "state": row[3],
        "rest_day": row[4],
    }


def _truecoach_workout_inspect_payload(response: WorkoutResponse) -> dict[str, Any]:
    workout = response.workouts[0] if response.workouts else None
    return {
        "ok": True,
        "workout": _truecoach_workout_payload(workout) if workout else None,
        **_truecoach_related_workout_payload(response),
        "warnings": [],
    }


def _truecoach_related_workout_payload(response: WorkoutResponse) -> dict[str, Any]:
    return {
        "workout_items": [item.model_dump() for item in response.workout_items],
        "comments": [comment.model_dump() for comment in response.comments],
        "meta": response.meta.model_dump(),
    }


def _truecoach_workout_payload(workout: Workout) -> dict[str, Any]:
    return {
        "id": workout.id,
        "due": workout.due,
        "title": workout.title,
        "state": workout.state,
        "rest_day": workout.rest_day,
        "program_name": workout.program_name,
        "workout_item_ids": workout.workout_item_ids,
    }


def _hevy_routines(args: argparse.Namespace) -> int:  # noqa: PLR0911
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        if args.routine_command == "find":
            return _find_hevy_routines(args)
        if args.routine_command == "inspect":
            return _inspect_hevy_routine(args)
        if args.routine_command == "delete":
            return _delete_hevy_routine(args)
        if args.routine_command == "create-from-json":
            return _create_hevy_routine_from_json(args)
        if args.routine_command == "update-from-json":
            return _update_hevy_routine_from_json(args)
        if args.routine_command == "diff-json":
            return _diff_hevy_routine_from_json(args)
    except HevyAppAPIError as exc:
        return _emit_error(args, str(exc))
    return _emit_error(args, "missing hevy routines subcommand")


def _hevy_workouts(args: argparse.Namespace) -> int:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        if args.workout_command == "inspect":
            return _inspect_hevy_workout(args)
    except HevyAppAPIError as exc:
        return _emit_error(args, str(exc))
    return _emit_error(args, "missing hevy workouts subcommand")


def _hevy_routine_folders(args: argparse.Namespace) -> int:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        if args.routine_folder_command == "ensure":
            return _ensure_hevy_routine_folder(args)
    except HevyAppAPIError as exc:
        return _emit_error(args, str(exc))
    return _emit_error(args, "missing hevy routine-folders subcommand")


def _find_hevy_routines(args: argparse.Namespace) -> int:
    routines = _find_remote_hevy_routines(args.title)
    if args.json:
        return _emit_json_result({"ok": True, "routines": routines, "warnings": []})
    if not routines:
        _emit("No matching Hevy routines.")
        return 0
    for routine in routines:
        _emit(f"{routine.get('id')} | {routine.get('title')}")
    return 0


def _inspect_hevy_routine(args: argparse.Namespace) -> int:
    routine = _hevy_api_json("GET", f"/routines/{args.routine_id}")
    routine_data = _unwrap_routine(routine)
    exercises = routine_data.get("exercises", [])
    empty_set_blocks = _empty_set_block_positions(exercises)
    if args.json:
        warnings = _empty_set_block_warnings("Routine", empty_set_blocks)
        return _emit_json_result(
            {
                "ok": True,
                "routine": _routine_inspect_payload(routine_data),
                "warnings": warnings,
            },
            warnings=warnings,
        )
    _emit(f"id: {routine_data.get('id')}")
    _emit(f"title: {routine_data.get('title')}")
    _emit(f"exercises: {len(exercises)}")
    _emit(f"superset_ids: {[exercise.get('superset_id') for exercise in exercises]}")
    _emit(f"empty_set_blocks: {empty_set_blocks}")
    for index, exercise in enumerate(exercises, start=1):
        _emit(
            f"{index}. superset={exercise.get('superset_id')} "
            f"template={exercise.get('exercise_template_id')} "
            f"notes={exercise.get('notes')!r} sets={len(exercise.get('sets') or [])}"
        )
    return 0


def _routine_inspect_payload(routine_data: dict[str, Any]) -> dict[str, Any]:
    exercises = routine_data.get("exercises", [])
    return {
        "id": routine_data.get("id"),
        "title": routine_data.get("title"),
        "exercise_count": len(exercises),
        "superset_ids": [exercise.get("superset_id") for exercise in exercises],
        "empty_set_blocks": _empty_set_block_positions(exercises),
        "exercises": [
            {
                "position": index,
                "superset_id": exercise.get("superset_id"),
                "exercise_template_id": exercise.get("exercise_template_id"),
                "notes": exercise.get("notes"),
                "set_count": len(exercise.get("sets") or []),
            }
            for index, exercise in enumerate(exercises, start=1)
        ],
    }


def _inspect_hevy_workout(args: argparse.Namespace) -> int:
    workout = _hevy_api_json("GET", f"/workouts/{args.workout_id}")
    workout_data = _unwrap_workout(workout)
    exercises = workout_data.get("exercises", [])
    empty_set_blocks = _empty_set_block_positions(exercises)
    if args.json:
        warnings = _empty_set_block_warnings("Workout", empty_set_blocks)
        return _emit_json_result(
            {
                "ok": True,
                "workout": _workout_inspect_payload(workout_data),
                "warnings": warnings,
            },
            warnings=warnings,
        )
    _emit(f"id: {workout_data.get('id')}")
    _emit(f"title: {workout_data.get('title')}")
    _emit(f"start_time: {workout_data.get('start_time')}")
    _emit(f"end_time: {workout_data.get('end_time')}")
    _emit(f"exercises: {len(exercises)}")
    _emit(f"superset_ids: {[exercise.get('superset_id') for exercise in exercises]}")
    _emit(f"empty_set_blocks: {empty_set_blocks}")
    for index, exercise in enumerate(exercises, start=1):
        name = exercise.get("title") or exercise.get("name")
        _emit(
            f"{index}. superset={exercise.get('superset_id')} "
            f"template={exercise.get('exercise_template_id')} "
            f"name={name!r} notes={exercise.get('notes')!r} "
            f"sets={len(exercise.get('sets') or [])}"
        )
    return 0


def _workout_inspect_payload(workout_data: dict[str, Any]) -> dict[str, Any]:
    exercises = workout_data.get("exercises", [])
    return {
        "id": workout_data.get("id"),
        "title": workout_data.get("title"),
        "start_time": workout_data.get("start_time"),
        "end_time": workout_data.get("end_time"),
        "exercise_count": len(exercises),
        "superset_ids": [exercise.get("superset_id") for exercise in exercises],
        "empty_set_blocks": _empty_set_block_positions(exercises),
        "exercises": [
            {
                "position": index,
                "superset_id": exercise.get("superset_id"),
                "exercise_template_id": exercise.get("exercise_template_id"),
                "name": exercise.get("title") or exercise.get("name"),
                "notes": exercise.get("notes"),
                "set_count": len(exercise.get("sets") or []),
            }
            for index, exercise in enumerate(exercises, start=1)
        ],
    }


def _empty_set_block_positions(exercises: list[dict[str, Any]]) -> list[int]:
    return [index for index, exercise in enumerate(exercises, start=1) if not exercise.get("sets")]


def _empty_set_block_warnings(label: str, empty_set_blocks: list[int]) -> list[str]:
    if not empty_set_blocks:
        return []
    return [f"{label} has empty set blocks: {empty_set_blocks}"]


def _delete_hevy_routine(args: argparse.Namespace) -> int:
    _hevy_web_json("DELETE", f"/routine/{args.routine_id}")
    if args.json:
        return _emit_json_result(
            {
                "ok": True,
                "action": "deleted",
                "routine_id": args.routine_id,
                "warnings": [],
            },
        )
    _emit(f"Deleted Hevy routine: {args.routine_id}")
    return 0


def _create_hevy_routine_from_json(args: argparse.Namespace) -> int:
    request_path = Path(getattr(args, "request_path", None) or args.manual_request)
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    PostRoutinesRequestBody(**payload)
    response = _hevy_api_json("POST", "/routines", json_body=payload)
    response_path = _write_response_artifact(args.response_path, response)
    routine = _unwrap_routine(response)
    if getattr(args, "json", False):
        return _emit_json_result(
            {
                "ok": True,
                "action": "created",
                "routine_id": routine.get("id"),
                "response_path": _json_response_path(response_path),
                "response": response,
                "warnings": [],
            },
        )
    _emit(f"Created Hevy routine: {routine.get('id')}")
    if response_path is not None:
        _emit(f"Wrote Hevy response: {response_path}")
    return 0


def _update_hevy_routine_from_json(args: argparse.Namespace) -> int:
    request_path = Path(args.request_path)
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    routine_payload = payload.setdefault("routine", {})
    routine_payload.pop("folder_id", None)
    if not routine_payload.get("notes"):
        routine_payload["notes"] = args.notes_if_empty
    body = PutRoutinesRequestBody(**payload)
    response = _hevy_api_json(
        "PUT",
        f"/routines/{args.routine_id}",
        json_body=body.model_dump(exclude_none=True),
    )
    response_path = _write_response_artifact(args.response_path, response)
    routine = _unwrap_routine(response)
    if getattr(args, "json", False):
        return _emit_json_result(
            {
                "ok": True,
                "action": "updated",
                "routine_id": routine.get("id", args.routine_id),
                "response_path": _json_response_path(response_path),
                "response": response,
                "warnings": [],
            },
        )
    _emit(f"Updated Hevy routine: {routine.get('id', args.routine_id)}")
    if response_path is not None:
        _emit(f"Wrote Hevy response: {response_path}")
    return 0


def _json_response_path(response_path: Path | None) -> str | None:
    if response_path is None:
        return None
    return str(response_path)


def _diff_hevy_routine_from_json(args: argparse.Namespace) -> int:
    request_path = Path(args.request_path)
    expected = json.loads(request_path.read_text(encoding="utf-8")).get("routine", {})
    response = _hevy_api_json("GET", f"/routines/{args.routine_id}")
    actual = _unwrap_routine(response)
    report = _format_routine_diff_report(
        routine_id=args.routine_id,
        expected=expected,
        actual=actual,
        include_low_signal=args.include_low_signal,
    )
    if args.output_path:
        output_path = Path(args.output_path)
        output_path.write_text(report + "\n", encoding="utf-8")
        _emit(f"Wrote Hevy routine diff: {output_path}")
    else:
        _emit(report)
    return 1 if "## " in report else 0


def _ensure_hevy_routine_folder(args: argparse.Namespace) -> int:
    existing = _find_remote_hevy_routine_folder(args.title)
    if existing is not None:
        if args.json:
            return _emit_json_result(
                {
                    "ok": True,
                    "action": "existing",
                    "routine_folder": existing,
                    "warnings": [],
                },
            )
        _emit(f"{existing.get('id')} | {existing.get('title')}")
        return 0
    payload = PostRoutineFolderRequestBody(
        routine_folder=PostRoutineFolderRequest(title=args.title)
    ).model_dump()
    response = _hevy_api_json("POST", "/routine_folders", json_body=payload)
    folder = _unwrap_routine_folder(response)
    if args.json:
        return _emit_json_result(
            {
                "ok": True,
                "action": "created",
                "routine_folder": folder,
                "response": response,
                "warnings": [],
            },
        )
    _emit(f"{folder.get('id')} | {folder.get('title')}")
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
    if args.summary:
        _print_sync_review_summary(bundle.plan_path)
    return 0


def _sync_review_hevy_to_truecoach_results(args: argparse.Namespace) -> int:
    store = Store(_engine_from_args(args))
    service = HevyToTrueCoachResultReviewService(store=store, output_root=Path(args.output_dir))
    try:
        bundle = service.write_review(
            args.workout_id,
            decisions_path=_decisions_path_from_args(args),
        )
    except HevyToTrueCoachResultReviewError as exc:
        _emit(f"Error: {exc}")
        return 2
    _print_hevy_to_truecoach_result_review_summary(bundle)
    return 0


def _sync_apply_hevy_to_truecoach_results(args: argparse.Namespace) -> int:
    if not args.dry_run and not args.yes:
        _emit("Error: real apply requires --yes")
        return 2
    store = Store(_engine_from_args(args))
    service = HevyToTrueCoachResultReviewService(store=store, output_root=Path(args.output_dir))
    decisions_path = _decisions_path_from_args(args)
    try:
        if args.dry_run:
            result = service.write_apply_request(
                args.workout_id,
                decisions_path=decisions_path,
            )
        else:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            result = service.apply(
                args.workout_id,
                workout_item_writer=_truecoach_workout_item_writer_from_config(),
                decisions_path=decisions_path,
            )
    except (HevyToTrueCoachResultReviewError, HevyToTrueCoachResultApplyError) as exc:
        _emit(f"Error: {exc}")
        return 2
    _print_hevy_to_truecoach_result_apply_summary(result)
    return 0


def _print_hevy_to_truecoach_result_review_summary(
    bundle: HevyToTrueCoachResultReviewBundle,
) -> None:
    validation = _read_json(bundle.decision_validation_path)
    _emit(f"review_dir: {bundle.directory}")
    _emit(f"report: {bundle.report_path}")
    _emit(f"plan: {bundle.plan_path}")
    _emit(f"decisions: {bundle.decisions_path}")
    _emit(f"decision_validation: {bundle.decision_validation_path}")
    _emit(f"blockers: {len(validation.get('blockers', []))}")
    _emit(f"warnings: {len(validation.get('warnings', []))}")


def _print_hevy_to_truecoach_result_apply_summary(
    result: HevyToTrueCoachResultApplyResult,
) -> None:
    _print_hevy_to_truecoach_result_review_summary(result.review_bundle)
    _emit(f"request: {result.request_path}")
    _emit(f"action: {result.action}")
    _emit(f"updated_true_coach_workout_item_ids: {result.updated_true_coach_workout_item_ids}")
    _emit(f"omitted_hevy_workout_item_ids: {result.omitted_hevy_workout_item_ids}")
    _emit(f"unresolved_hevy_workout_item_ids: {result.unresolved_hevy_workout_item_ids}")
    _emit(f"completion_status: {result.completion_status}")


def _decisions_path_from_args(args: argparse.Namespace) -> Path | None:
    if not args.decisions:
        return None
    return Path(args.decisions)


def _truecoach_workout_item_writer_from_config() -> TrueCoachWorkoutItemWriterAdapter:
    cfg = Config.from_env()
    return TrueCoachWorkoutItemWriterAdapter(
        TrueCoachClient(
            email=cfg.email,
            password=cfg.truecoach_password.get_secret_value(),
        )
    )


def _sync_review_truecoach_workout_backfill_candidates(args: argparse.Namespace) -> int:
    store = Store(_engine_from_args(args))
    service = TrueCoachWorkoutBackfillDiscoveryService(
        store=store,
        output_root=Path(args.output_dir),
    )
    bundle = service.write_report()
    _emit(f"Wrote backfill candidate report: {bundle.report_path}")
    return 0


def _sync_review_truecoach_workout_backfill(args: argparse.Namespace) -> int:
    store = Store(_engine_from_args(args))
    service = TrueCoachWorkoutBackfillReviewService(
        store=store,
        output_root=Path(args.output_dir),
    )
    try:
        bundle = service.write_review(
            args.workout_id,
            decisions_path=Path(args.decisions) if args.decisions else None,
        )
    except WorkoutBackfillReviewError as exc:
        _emit(f"Error: {exc}")
        return 2
    _emit(f"Wrote Workout backfill review: {bundle.directory}")
    return 0


def _sync_review_truecoach_workout_backfill_inspect(args: argparse.Namespace) -> int:
    try:
        bundle = _write_workout_backfill_review(args)
    except WorkoutBackfillReviewError as exc:
        _emit(f"Error: {exc}")
        return 2
    plan = _read_json(bundle.plan_path)
    request = _read_json(bundle.request_path)
    workout = plan.get("workout", {})
    _emit(f"review_dir: {bundle.directory}")
    _emit(
        "workout: "
        f"{workout.get('id')} | {workout.get('title')} | due={workout.get('due')} | "
        f"tracker={workout.get('tracker_workout_id')} | hevy={workout.get('tracker_hevy_app_id')}"
    )
    _emit(f"blockers: {plan.get('blockers', [])}")
    _emit(f"warnings: {plan.get('warnings', [])}")
    _emit("plan_items:")
    for item in plan.get("items", []):
        template = item.get("selected_hevy_template") or {}
        _emit(
            f"{item.get('position')}. tc_item={item.get('source_id')} "
            f"tracker_item={item.get('tracker_workout_item_id')} "
            f"superset={item.get('superset_id')} template={template.get('id')} "
            f"sets={len(item.get('sets') or [])} notes={bool(item.get('notes'))} "
            f"name={item.get('name')!r}"
        )
        for warning in item.get("warnings", []):
            _emit(f"  warning: {warning}")
        for blocker in item.get("blockers", []):
            _emit(f"  blocker: {blocker}")
    _emit("request_exercises:")
    for index, exercise in enumerate(request.get("workout", {}).get("exercises", []), start=1):
        _emit(
            f"{index}. superset={exercise.get('superset_id')} "
            f"template={exercise.get('exercise_template_id')} "
            f"sets={len(exercise.get('sets') or [])} notes={bool(exercise.get('notes'))}"
        )
    return 0


def _sync_review_truecoach_workout_backfill_evidence(args: argparse.Namespace) -> int:
    try:
        bundle = _write_workout_backfill_review(args)
    except WorkoutBackfillReviewError as exc:
        _emit(f"Error: {exc}")
        return 2
    evidence = _read_json(bundle.apple_health_evidence_path)
    _emit(f"evidence: {bundle.apple_health_evidence_path}")
    _emit(
        "search_window: "
        f"{evidence.get('search_window', {}).get('start')} -> "
        f"{evidence.get('search_window', {}).get('end')}"
    )
    _emit("candidate_windows:")
    for candidate in evidence.get("candidate_windows", []):
        _emit(
            f"- {candidate.get('confidence')} {candidate.get('source')}: "
            f"{candidate.get('start')} -> {candidate.get('end')} | {candidate.get('reason')}"
        )
    _emit("workout_intervals:")
    for interval in evidence.get("workout_intervals", []):
        _emit(
            f"- {interval.get('type')}: {interval.get('start')} -> {interval.get('end')} "
            f"({interval.get('duration_minutes')} min)"
        )
    _emit("heart_rate_summaries:")
    for summary in evidence.get("heart_rate_summaries", []):
        _emit(
            f"- {summary.get('window_start')} -> {summary.get('window_end')} "
            f"samples={summary.get('sample_count')} avg={summary.get('average_bpm')} "
            f"max={summary.get('max_bpm')}"
        )
    return 0


def _sync_review_truecoach_workout_backfill_diff(args: argparse.Namespace) -> int:
    try:
        bundle = _write_workout_backfill_review(args)
    except WorkoutBackfillReviewError as exc:
        _emit(f"Error: {exc}")
        return 2
    request = _read_json(bundle.request_path)
    local = _linked_hevy_workout_snapshot(_engine_from_args(args), args.workout_id)
    if local is None:
        _emit(f"No linked local Hevy Workout for True Coach Workout {args.workout_id}.")
        return 2
    differences = _workout_request_local_differences(request, local)
    _emit(f"request: {bundle.request_path}")
    _emit(f"local_hevy_workout: {local.get('id')}")
    if not differences:
        _emit("No differences between request and linked local Hevy Workout cache.")
        return 0
    _emit("differences:")
    for difference in differences:
        _emit(f"- {difference}")
    return 1


def _sync_apply_truecoach_to_hevy(args: argparse.Namespace) -> int:  # noqa: PLR0915
    if args.manual_request:
        if args.dry_run:
            _emit("Error: --manual-request cannot be combined with --dry-run")
            return 2
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            return _create_hevy_routine_from_json(args)
        except (HevyAppAPIError, ValueError) as exc:
            _emit(f"Error: {exc}")
            return 2
    store = Store(_engine_from_args(args))
    service = TrueCoachToHevyReviewService(store=store, output_root=Path(args.output_dir))
    try:
        if args.down_regulate_duration is not None or args.folder_id is not None:
            result = _write_patched_truecoach_to_hevy_request(args, service)
            if not args.dry_run:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                HevyRoutineWriterAdapter(_hevy_client_from_config()).create_routine(
                    result.request_body
                )
        elif args.dry_run:
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


def _write_patched_truecoach_to_hevy_request(
    args: argparse.Namespace,
    service: TrueCoachToHevyReviewService,
) -> ApplyResult:
    bundle = service.write_review(args.workout_id)
    plan = _read_json(bundle.plan_path)
    if args.down_regulate_duration is not None:
        _patch_down_regulate_sets(plan, duration_seconds=args.down_regulate_duration)
    request_body = _build_hevy_routine_request(plan)
    if args.folder_id is not None:
        request_body.routine.folder_id = args.folder_id
    request_path = bundle.directory / "hevy-request.json"
    request_path.write_text(
        json.dumps(request_body.model_dump(exclude_none=True), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return ApplyResult(
        review_bundle=bundle,
        request_path=request_path,
        request_body=request_body,
    )


def _patch_down_regulate_sets(plan: dict[str, Any], *, duration_seconds: int) -> None:
    for item in plan.get("items", []):
        if str(item.get("name", "")).casefold().strip() != "down regulate":
            continue
        if item.get("planned_blocks") or item.get("proposed_sets"):
            continue
        item["proposed_sets"] = [{"type": "normal", "duration_seconds": duration_seconds}]


def _sync_apply_truecoach_workout_backfill(args: argparse.Namespace) -> int:  # noqa: PLR0915
    decisions_path = Path(args.decisions) if args.decisions else None
    try:
        if args.manual_request:
            if args.dry_run:
                _emit("Error: --manual-request cannot be combined with --dry-run")
                return 2
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            result = _workout_backfill_manual_service(args).apply_manual_request(
                Path(args.manual_request),
                workout_id=args.workout_id,
                workout_writer=HevyWorkoutWriterAdapter(_hevy_client_from_config()),
            )
        elif args.dry_run:
            result = _workout_backfill_review_service(args).write_apply_request(
                args.workout_id,
                decisions_path=decisions_path,
            )
        else:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            result = _workout_backfill_review_service(args).apply(
                args.workout_id,
                workout_writer=HevyWorkoutWriterAdapter(_hevy_client_from_config()),
                decisions_path=decisions_path,
            )
    except (WorkoutBackfillApplyError, WorkoutBackfillReviewError, HevyAppAPIError) as exc:
        _emit(f"Error: {exc}")
        return 2
    if args.dry_run:
        _emit(f"Wrote Hevy Workout request dry-run: {result.request_path}")
    elif result.action == "already_linked":
        _emit(f"Hevy Workout already linked locally: {result.request_path}")
    elif result.action == "repaired_existing_remote":
        _emit(f"Linked existing remote Hevy Workout from request: {result.request_path}")
    else:
        _emit(f"Created Hevy Workout from request: {result.request_path}")
    return 0


def _sync_apply_truecoach_workout_backfill_repair(args: argparse.Namespace) -> int:
    decisions_path = Path(args.decisions) if args.decisions else None
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        result = _workout_backfill_review_service(args).repair_local_links(
            args.workout_id,
            workout_writer=HevyWorkoutWriterAdapter(_hevy_client_from_config()),
            decisions_path=decisions_path,
        )
    except (WorkoutBackfillApplyError, WorkoutBackfillReviewError, HevyAppAPIError) as exc:
        _emit(f"Error: {exc}")
        return 2
    _emit(f"Linked existing remote Hevy Workout from request: {result.request_path}")
    return 0


def _workout_backfill_review_service(
    args: argparse.Namespace,
) -> TrueCoachWorkoutBackfillReviewService:
    return TrueCoachWorkoutBackfillReviewService(
        store=Store(_engine_from_args(args)),
        output_root=Path(args.output_dir),
    )


def _workout_backfill_manual_service(
    args: argparse.Namespace,
) -> TrueCoachWorkoutBackfillReviewService:
    return TrueCoachWorkoutBackfillReviewService(
        store=Store(create_database_engine("sqlite:///:memory:")),
        output_root=Path(args.output_dir),
    )


def _write_workout_backfill_review(args: argparse.Namespace) -> Any:
    return _workout_backfill_review_service(args).write_review(
        args.workout_id,
        decisions_path=Path(args.decisions) if args.decisions else None,
    )


def _find_remote_hevy_routines(title: str) -> list[dict[str, Any]]:
    normalized_title = title.casefold().strip()
    return [
        routine
        for routine in _hevy_api_pages("/routines", "routines", page_size=10)
        if str(routine.get("title", "")).casefold().strip() == normalized_title
    ]


def _find_remote_hevy_templates(title: str) -> list[dict[str, Any]]:
    normalized_title = title.casefold().strip()
    return [
        template
        for template in _hevy_api_pages("/exercise_templates", "exercise_templates", page_size=100)
        if str(template.get("title", "")).casefold().strip() == normalized_title
    ]


def _find_remote_hevy_routine_folder(title: str) -> dict[str, Any] | None:
    normalized_title = title.casefold().strip()
    for folder in _hevy_api_pages("/routine_folders", "routine_folders", page_size=10):
        if str(folder.get("title", "")).casefold().strip() == normalized_title:
            return folder
    return None


def _hevy_api_pages(endpoint: str, collection_key: str, *, page_size: int) -> list[dict[str, Any]]:
    page = 1
    results: list[dict[str, Any]] = []
    while True:
        data = _hevy_api_json(
            endpoint=endpoint, method="GET", params={"page": page, "pageSize": page_size}
        )
        results.extend(data.get(collection_key, data.get("routines", [])))
        if page >= int(data.get("page_count", page)):
            return results
        page += 1


def _hevy_api_json(  # noqa: PLR0913
    method: str,
    endpoint: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = Config.from_env()
    return _request_json(
        method=method,
        url=f"https://api.hevyapp.com/v1{endpoint}",
        headers={"api-key": cfg.hevy_api_key.get_secret_value()},
        json_body=json_body,
        params=params,
    )


def _hevy_web_json(method: str, endpoint: str) -> dict[str, Any] | None:
    cfg = Config.from_env()
    return _request_json(
        method=method,
        url=f"https://api.hevyapp.com{endpoint}",
        headers={
            "auth-token": cfg.hevy_web_api_key.get_secret_value(),
            "x-api-key": "shelobs_hevy_web",
        },
    )


def _request_json(  # noqa: PLR0913
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = requests.request(
        method,
        url,
        headers=headers,
        json=json_body,
        params=params,
        timeout=10,
        verify=False,
    )
    if not response.ok:
        msg = f"Error {response.status_code} for {response.url!r}"
        if response.text:
            msg = f"{msg} body={response.text!r}"
        raise HevyAppAPIError(msg, status_code=response.status_code, url=response.url)
    if response.status_code == 204 or not response.text:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def _unwrap_routine(response: dict[str, Any]) -> dict[str, Any]:
    routine = response.get("routine", response)
    if isinstance(routine, list):
        return routine[0] if routine else {}
    if isinstance(routine, dict):
        return routine
    return {}


def _unwrap_workout(response: dict[str, Any]) -> dict[str, Any]:
    workout = response.get("workout", response)
    if isinstance(workout, list):
        return workout[0] if workout else {}
    if isinstance(workout, dict):
        return workout
    return {}


def _unwrap_routine_folder(response: dict[str, Any]) -> dict[str, Any]:
    folder = response.get("routine_folder", response)
    if isinstance(folder, list):
        return folder[0] if folder else {}
    if isinstance(folder, dict):
        return folder
    return {}


def _write_response_artifact(response_path: str | None, response: dict[str, Any]) -> Path | None:
    if not response_path:
        return None
    path = Path(response_path)
    path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _linked_hevy_workout_snapshot(
    engine: Engine, true_coach_workout_id: int
) -> dict[str, Any] | None:
    with engine.connect() as conn:
        workout = (
            conn.execute(
                text(
                    """
                    SELECT h.id, h.title, h.start_time, h.end_time
                    FROM "Workout" AS tw
                    JOIN "HevyAppWorkout" AS h ON h.id = tw.hevy_app_id
                    WHERE tw.true_coach_id = :true_coach_workout_id
                    """
                ),
                {"true_coach_workout_id": true_coach_workout_id},
            )
            .mappings()
            .first()
        )
        if workout is None:
            return None
        exercises = (
            conn.execute(
                text(
                    """
                    SELECT id, "index", name, notes, superset_id, exercise_id
                    FROM "HevyAppWorkoutItem"
                    WHERE workout_id = :workout_id
                    ORDER BY "index"
                    """
                ),
                {"workout_id": workout["id"]},
            )
            .mappings()
            .all()
        )
        sets = (
            conn.execute(
                text(
                    """
                    SELECT workout_item_id, "index", type, weight_kg, reps,
                           distance_meters, duration_seconds, rpe
                    FROM "HevyAppSets"
                    WHERE workout_item_id IN (
                        SELECT id FROM "HevyAppWorkoutItem" WHERE workout_id = :workout_id
                    )
                    ORDER BY workout_item_id, "index"
                    """
                ),
                {"workout_id": workout["id"]},
            )
            .mappings()
            .all()
        )
    sets_by_item: dict[int, list[dict[str, Any]]] = {}
    for row in sets:
        sets_by_item.setdefault(int(row["workout_item_id"]), []).append(dict(row))
    return {
        "id": workout["id"],
        "title": workout["title"],
        "start_time": workout["start_time"],
        "end_time": workout["end_time"],
        "exercises": [
            {
                "id": row["id"],
                "index": row["index"],
                "name": row["name"],
                "notes": row["notes"],
                "superset_id": row["superset_id"],
                "exercise_template_id": row["exercise_id"],
                "sets": sets_by_item.get(int(row["id"]), []),
            }
            for row in exercises
        ],
    }


def _workout_request_local_differences(
    request: dict[str, Any],
    local: dict[str, Any],
) -> list[str]:
    request_exercises = request.get("workout", {}).get("exercises", [])
    local_exercises = local.get("exercises", [])
    differences = []
    if len(request_exercises) != len(local_exercises):
        differences.append(
            f"exercise count request={len(request_exercises)} local={len(local_exercises)}"
        )
    for index, request_exercise in enumerate(request_exercises):
        if index >= len(local_exercises):
            differences.append(f"exercise {index + 1} missing locally")
            continue
        local_exercise = local_exercises[index]
        comparisons = (
            (
                "template",
                request_exercise.get("exercise_template_id"),
                local_exercise.get("exercise_template_id"),
            ),
            ("superset", request_exercise.get("superset_id"), local_exercise.get("superset_id")),
            ("notes", request_exercise.get("notes") or "", local_exercise.get("notes") or ""),
        )
        for label, request_value, local_value in comparisons:
            if request_value != local_value:
                differences.append(
                    f"exercise {index + 1} {label} request={request_value!r} local={local_value!r}"
                )
        request_sets = request_exercise.get("sets") or []
        local_sets = local_exercise.get("sets") or []
        if len(request_sets) != len(local_sets):
            differences.append(
                f"exercise {index + 1} set count request={len(request_sets)} local={len(local_sets)}"
            )
    return differences


def _format_routine_diff_report(  # noqa: PLR0913
    *,
    routine_id: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
    include_low_signal: bool = False,
) -> str:
    expected_exercises = [
        _normalized_routine_exercise(row) for row in expected.get("exercises", [])
    ]
    actual_exercises = [_normalized_routine_exercise(row) for row in actual.get("exercises", [])]
    lines = [
        f"# Hevy Routine Diff: {routine_id}",
        "",
        f"Expected title: {expected.get('title')!r}",
        f"Actual title: {actual.get('title')!r}",
        f"Exercise count expected={len(expected_exercises)} actual={len(actual_exercises)}",
        "",
    ]
    differences = _routine_exercise_differences(
        expected_exercises,
        actual_exercises,
        include_low_signal=include_low_signal,
    )
    if not differences:
        lines.append("No normalized differences found.")
        return "\n".join(lines)
    lines.append("Differences:")
    for index, labels, expected_row, actual_row in differences:
        row = actual_row or expected_row or {}
        name = row.get("title") or row.get("template_id") or "unknown"
        lines.extend(
            [
                "",
                f"## {index}. {name} ({', '.join(labels)})",
                "",
                "Expected:",
                "```json",
                json.dumps(expected_row, indent=2, sort_keys=True),
                "```",
                "",
                "Actual:",
                "```json",
                json.dumps(actual_row, indent=2, sort_keys=True),
                "```",
            ]
        )
    return "\n".join(lines)


def _routine_exercise_differences(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    *,
    include_low_signal: bool,
) -> list[tuple[int, list[str], dict[str, Any] | None, dict[str, Any] | None]]:
    differences = []
    for index in range(max(len(expected), len(actual))):
        if index >= len(expected):
            differences.append((index + 1, ["added_remote_exercise"], None, actual[index]))
            continue
        if index >= len(actual):
            differences.append((index + 1, ["missing_remote_exercise"], expected[index], None))
            continue
        expected_row = expected[index]
        actual_row = actual[index]
        labels = _routine_exercise_difference_labels(expected_row, actual_row)
        if labels == ["low_signal_sets"] and not include_low_signal:
            continue
        if labels:
            differences.append((index + 1, labels, expected_row, actual_row))
    return differences


def _routine_exercise_difference_labels(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> list[str]:
    labels = [
        key
        for key in ("template_id", "superset_id", "notes", "rest_seconds")
        if expected.get(key) != actual.get(key)
    ]
    if expected.get("sets") != actual.get("sets"):
        labels.append(_set_difference_label(expected.get("sets") or [], actual.get("sets") or []))
    return labels


def _set_difference_label(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> str:
    if len(expected) != len(actual):
        return "sets"
    expected_types = [set_row.get("type") for set_row in expected]
    actual_types = [set_row.get("type") for set_row in actual]
    if expected_types != actual_types:
        return "sets"
    if _only_low_signal_set_values_changed(expected, actual):
        return "low_signal_sets"
    return "sets"


def _only_low_signal_set_values_changed(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
) -> bool:
    low_signal_keys = {"weight_kg", "reps", "duration_seconds"}
    for expected_set, actual_set in zip(expected, actual, strict=True):
        changed_keys = {
            key
            for key in set(expected_set) | set(actual_set)
            if expected_set.get(key) != actual_set.get(key)
        }
        if not changed_keys:
            continue
        if not changed_keys <= low_signal_keys:
            return False
        if "duration_seconds" in changed_keys and expected_set.get("distance_meters") is None:
            return False
    return True


def _normalized_routine_exercise(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_id": row.get("exercise_template_id"),
        "title": row.get("title"),
        "superset_id": row.get("superset_id"),
        "notes": row.get("notes") or "",
        "rest_seconds": row.get("rest_seconds") or 0,
        "sets": [_normalized_routine_set(set_row) for set_row in row.get("sets") or []],
    }


def _normalized_routine_set(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("type", "weight_kg", "reps", "distance_meters", "duration_seconds", "custom_metric")
    return {key: row[key] for key in keys if row.get(key) is not None or key == "type"}


def _print_sync_review_summary(plan_path: Path) -> None:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    items = plan.get("items", [])
    blockers = [blocker for item in items for blocker in item.get("blockers", [])]
    warnings = [warning for item in items for warning in item.get("warnings", [])]
    required_templates = [
        template for item in items for template in item.get("required_hevy_templates", [])
    ]
    superset_ids = [
        block.get("superset_id")
        for item in items
        for block in (item.get("planned_blocks") or [item])
    ]
    empty_set_items = [
        item.get("name")
        for item in items
        if not item.get("planned_blocks") and not item.get("proposed_sets")
    ]
    empty_set_items.extend(
        block.get("source_text")
        for item in items
        for block in item.get("planned_blocks", [])
        if not block.get("proposed_sets")
    )
    _emit(f"blockers: {blockers}")
    _emit(f"warnings: {warnings}")
    _emit(f"required_templates: {required_templates}")
    _emit(f"superset_ids: {superset_ids}")
    _emit(f"empty_set_items: {empty_set_items}")


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


def _emit_json_result(
    payload: dict[str, Any],
    *,
    warnings: list[str] | None = None,
    exit_code: int = 0,
) -> int:
    for warning in warnings or []:
        _emit(f"Warning: {warning}", stderr=True)
    _emit(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return exit_code


def _emit_error(args: argparse.Namespace, message: str, *, exit_code: int = 2) -> int:
    if getattr(args, "json", False):
        return _emit_json_result({"ok": False, "error": message}, exit_code=exit_code)
    _emit(f"Error: {message}", stderr=True)
    return exit_code


def _emit(message: str, *, stderr: bool = False) -> None:
    print(message, file=sys.stderr if stderr else sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
