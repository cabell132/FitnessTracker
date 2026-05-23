#!/usr/bin/env python3
"""Find True Coach-to-Hevy Routine artifacts that can seed Routine feedback reviews.

This script is intentionally read-only. It scans existing review artifacts and prints
candidate Routine IDs plus the commands an Agent can run to diff current remote Hevy
state against the original generated request.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _created_routine_ids(response: dict[str, Any]) -> list[str]:
    ids = response.get("created_routine_ids")
    if isinstance(ids, list):
        return [str(value) for value in ids if value]

    # Be permissive for manually captured Hevy responses.
    routine = response.get("routine")
    if isinstance(routine, dict) and routine.get("id"):
        return [str(routine["id"])]
    if isinstance(routine, list):
        return [str(row["id"]) for row in routine if isinstance(row, dict) and row.get("id")]
    return []


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("reports")
    source_root = root / "sync-review" / "truecoach-to-hevy"
    if not source_root.exists():
        print(f"No True Coach-to-Hevy review directory found: {source_root}")
        return 1

    candidates = []
    for workout_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
        request_path = workout_dir / "hevy-request.json"
        response_path = workout_dir / "hevy-response.json"
        plan_path = workout_dir / "plan.json"
        report_path = workout_dir / "report.md"
        if not request_path.exists():
            continue
        response = _read_json(response_path) if response_path.exists() else {}
        routine_ids = _created_routine_ids(response)
        candidates.append(
            {
                "workout_id": workout_dir.name,
                "routine_ids": routine_ids,
                "request_path": request_path,
                "response_path": response_path if response_path.exists() else None,
                "plan_path": plan_path if plan_path.exists() else None,
                "report_path": report_path if report_path.exists() else None,
                "missing": [
                    name
                    for name, path in (
                        ("plan.json", plan_path),
                        ("report.md", report_path),
                        ("hevy-response.json", response_path),
                    )
                    if not path.exists()
                ],
            }
        )

    if not candidates:
        print(f"No candidates with hevy-request.json found under {source_root}")
        return 1

    print(f"Found {len(candidates)} Routine feedback candidate(s).")
    for candidate in candidates:
        print("\n---")
        print(f"workout_id: {candidate['workout_id']}")
        print(f"request: {_relative(candidate['request_path'])}")
        if candidate["response_path"]:
            print(f"response: {_relative(candidate['response_path'])}")
        if candidate["plan_path"]:
            print(f"plan: {_relative(candidate['plan_path'])}")
        if candidate["report_path"]:
            print(f"report: {_relative(candidate['report_path'])}")
        if candidate["missing"]:
            print(f"missing: {', '.join(candidate['missing'])}")
        routine_ids = candidate["routine_ids"]
        if not routine_ids:
            print("routine_ids: unknown; inspect hevy-response.json or provide ROUTINE_ID manually")
            continue
        print(f"routine_ids: {', '.join(routine_ids)}")
        for routine_id in routine_ids:
            out_dir = Path("reports") / "sync-review" / "routine-feedback" / routine_id
            print("suggested_diff:")
            print(
                "  uv run fitness-tracker hevy routines diff-json "
                f"{routine_id} {_relative(candidate['request_path'])} "
                f"--output-path {_relative(out_dir / 'hevy-routine-diff.md')}"
            )
            print("suggested_low_signal_diff:")
            print(
                "  uv run fitness-tracker hevy routines diff-json "
                f"{routine_id} {_relative(candidate['request_path'])} "
                "--include-low-signal "
                f"--output-path {_relative(out_dir / 'hevy-routine-diff.low-signal.md')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
