"""Shared review workflow artifact mechanics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def review_bundle_dir(output_root: Path, *parts: object) -> Path:
    """Create and return a sync-review bundle directory.

    Args:
        output_root (Path): Root directory for report artifacts.
        *parts (object): Path components under the sync-review directory.

    Returns:
        Path: Created bundle directory.
    """
    bundle_dir = output_root / "sync-review"
    for part in parts:
        bundle_dir /= str(part)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    return bundle_dir


def write_json_artifact(path: Path, payload: Any) -> None:
    """Write a stable pretty-printed JSON artifact.

    Args:
        path (Path): Destination JSON path.
        payload (Any): JSON-serializable payload or Pydantic model.
    """
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json_artifact(path: Path) -> Any:
    """Read a JSON artifact.

    Args:
        path (Path): JSON artifact path to read.

    Returns:
        Any: Parsed JSON payload.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_object(path: Path) -> dict[str, Any]:
    """Read a JSON artifact that must contain an object.

    Args:
        path (Path): JSON artifact path to read.

    Returns:
        dict[str, Any]: Parsed JSON object.

    Raises:
        TypeError: If the JSON payload is not an object.
    """
    data = read_json_artifact(path)
    if not isinstance(data, dict):
        msg = f"JSON artifact {path} must contain a JSON object"
        raise TypeError(msg)
    return data


def load_decisions_file[ReviewError: Exception](
    decisions_path: Path,
    *,
    error_cls: type[ReviewError],
) -> dict[str, Any]:
    """Load an editable decisions JSON object with workflow-specific errors.

    Args:
        decisions_path (Path): Decisions JSON path to read.
        error_cls (type[ReviewError]): Exception type to raise for workflow errors.

    Returns:
        dict[str, Any]: Parsed decisions object.

    Raises:
        error_cls: If the file cannot be read, parsed, or is not a JSON object.
    """
    try:
        data = read_json_artifact(decisions_path)
    except OSError as exc:
        msg = f"Could not read decisions file {decisions_path}: {exc}"
        raise error_cls(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"Could not parse decisions file {decisions_path}: {exc}"
        raise error_cls(msg) from exc
    if not isinstance(data, dict):
        msg = f"Decisions file {decisions_path} must contain a JSON object"
        raise error_cls(msg)
    return data
