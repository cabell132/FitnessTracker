"""Run the local experimental calculator against an interpreted JSON request."""

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from scripts.load_calculator import Calculation, calculate


def main(argv: list[str] | None = None) -> int:
    """Read a request and emit a review artifact or the input JSON schema.

    Args:
        argv (list[str] | None): Explicit arguments, or process arguments.

    Returns:
        int: Zero on success; argument and validation errors exit with status two.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, nargs="?")
    parser.add_argument("--schema", action="store_true", help="Print the interpreted input schema")
    parser.add_argument("--output", type=Path, help="Write the review artifact to this local file")
    args = parser.parse_args(argv)
    if args.schema:
        output = json.dumps(Calculation.model_json_schema(), indent=2)
    else:
        output = _calculate_file(parser, args.request)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)  # noqa: T201
    return 0


def _calculate_file(parser: argparse.ArgumentParser, path: Path | None) -> str:
    if path is None:
        parser.error("Supply a request JSON file or --schema.")
    try:
        request = Calculation.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        parser.error("Cannot read the request as a UTF-8 file.")
    except ValidationError as error:
        fields = [".".join(map(str, e["loc"])) or "request" for e in error.errors()]
        parser.error("Invalid request fields: " + ", ".join(fields))
    return calculate(request).model_dump_json(indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
