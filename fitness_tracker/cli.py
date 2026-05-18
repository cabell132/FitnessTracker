"""Command line entry points for fitness-tracker maintenance tasks."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

import requests
import urllib3
from sqlalchemy import text
from sqlalchemy.engine import Engine

from fitness_tracker.apis import HevyAppClient
from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.hevy_app.types import PostRoutinesRequestBody
from fitness_tracker.apis.hevy_app.types.common import (
    CUSTOM_EXERCISE_TYPES,
    EQUIPMENT_CATEGORIES,
    MUSCLE_GROUPS,
)
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
from fitness_tracker.sync.adapters import HevyRoutineWriterAdapter, HevyWorkoutWriterAdapter
from fitness_tracker.sync_review import (
    SyncApplyError,
    SyncReviewError,
    TrueCoachToHevyReviewService,
    TrueCoachWorkoutBackfillDiscoveryService,
    TrueCoachWorkoutBackfillReviewService,
    WorkoutBackfillApplyError,
    WorkoutBackfillReviewError,
)


def main(argv: list[str] | None = None) -> int:  # noqa: C901, PLR0911
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
    if args.command == "hevy-templates" and args.hevy_templates_command == "ensure-from-plan":
        return _ensure_hevy_templates_from_plan(args)
    if args.command == "hevy-templates" and args.hevy_templates_command == "create":
        return _create_hevy_template(args)
    if args.command == "hevy-templates" and args.hevy_templates_command == "find":
        return _find_hevy_templates(args)
    if args.command == "truecoach" and args.truecoach_command == "due":
        return _truecoach_due(args)
    if args.command == "sync-review" and args.sync_review_command == "truecoach-to-hevy":
        return _sync_review_truecoach_to_hevy(args)
    if (
        args.command == "sync-review"
        and args.sync_review_command == "truecoach-workout-backfill-candidates"
    ):
        return _sync_review_truecoach_workout_backfill_candidates(args)
    if args.command == "sync-review" and args.sync_review_command == "truecoach-workout-backfill":
        return _sync_review_truecoach_workout_backfill(args)
    if args.command == "sync-apply" and args.sync_apply_command == "truecoach-to-hevy":
        return _sync_apply_truecoach_to_hevy(args)
    if args.command == "sync-apply" and args.sync_apply_command == "truecoach-workout-backfill":
        return _sync_apply_truecoach_workout_backfill(args)
    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fitness-tracker")
    subparsers = parser.add_subparsers(dest="command")
    _add_hevy_parser(subparsers)
    _add_hevy_templates_parser(subparsers)
    _add_truecoach_parser(subparsers)
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

    inspect = routine_subparsers.add_parser("inspect")
    inspect.add_argument("routine_id")

    delete = routine_subparsers.add_parser("delete")
    delete.add_argument("routine_id")
    delete.add_argument("--yes", action="store_true", required=True)

    create = routine_subparsers.add_parser("create-from-json")
    create.add_argument("request_path")
    create.add_argument("--response-path")


def _add_hevy_templates_parser(subparsers: Any) -> None:  # noqa: PLR0915
    hevy_templates = subparsers.add_parser("hevy-templates")
    hevy_template_subparsers = hevy_templates.add_subparsers(dest="hevy_templates_command")

    ensure = hevy_template_subparsers.add_parser("ensure-from-plan")
    ensure.add_argument("plan_path")
    ensure.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    ensure.add_argument("--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL.")
    mode = ensure.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--yes", action="store_true")

    create = hevy_template_subparsers.add_parser("create")
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

    find = hevy_template_subparsers.add_parser("find")
    find.add_argument("--title", required=True)


def _add_truecoach_parser(subparsers: Any) -> None:
    truecoach = subparsers.add_parser("truecoach")
    truecoach_subparsers = truecoach.add_subparsers(dest="truecoach_command")

    due = truecoach_subparsers.add_parser("due")
    due.add_argument("--date", required=True)
    due.add_argument("--db", help="SQLite database path. Prefer --database-url.")
    due.add_argument("--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL.")


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
    truecoach_to_hevy.add_argument("--summary", action="store_true")

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
    truecoach_to_hevy.add_argument("--manual-request")
    truecoach_to_hevy.add_argument("--response-path")

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
    if not rows:
        _emit(f"No True Coach Workouts due on {args.date}.")
        return 0
    _emit("id | title | due | state | rest_day")
    for row in rows:
        _emit(" | ".join(str(value) for value in row))
    return 0


def _hevy_routines(args: argparse.Namespace) -> int:
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
    except HevyAppAPIError as exc:
        _emit(f"Error: {exc}")
        return 2
    _emit("Error: missing hevy routines subcommand")
    return 2


def _find_hevy_routines(args: argparse.Namespace) -> int:
    routines = _find_remote_hevy_routines(args.title)
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
    empty_set_blocks = [
        index for index, exercise in enumerate(exercises, start=1) if not exercise.get("sets")
    ]
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


def _delete_hevy_routine(args: argparse.Namespace) -> int:
    _hevy_web_json("DELETE", f"/routine/{args.routine_id}")
    _emit(f"Deleted Hevy routine: {args.routine_id}")
    return 0


def _create_hevy_routine_from_json(args: argparse.Namespace) -> int:
    request_path = Path(getattr(args, "request_path", None) or args.manual_request)
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    PostRoutinesRequestBody(**payload)
    response = _hevy_api_json("POST", "/routines", json_body=payload)
    response_path = _routine_response_path(args.response_path, request_path)
    response_path.write_text(
        json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    routine = _unwrap_routine(response)
    _emit(f"Created Hevy routine: {routine.get('id')}")
    _emit(f"Wrote Hevy response: {response_path}")
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


def _sync_apply_truecoach_workout_backfill(args: argparse.Namespace) -> int:
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
    else:
        _emit(f"Created Hevy Workout from request: {result.request_path}")
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


def _hevy_api_pages(endpoint: str, collection_key: str, *, page_size: int) -> list[dict[str, Any]]:
    page = 1
    results: list[dict[str, Any]] = []
    while True:
        data = _hevy_api_json(
            endpoint=endpoint, method="GET", params={"page": page, "pageSize": page_size}
        )
        results.extend(data.get(collection_key, []))
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


def _routine_response_path(response_path: str | None, request_path: Path) -> Path:
    if response_path:
        return Path(response_path)
    return request_path.with_name(f"{request_path.stem}.response.json")


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


def _emit(message: str) -> None:
    print(message)  # noqa: T201


if __name__ == "__main__":
    raise SystemExit(main())
