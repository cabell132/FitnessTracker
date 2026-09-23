"""One-time local conversion of VeSync values to prompt-free Varlock inputs.

Run only in your own terminal:
``uv run --locked python -m scripts.make_vesync_env_plaintext``
The script asks for both values once without echoing them. It does not print them.
"""

from __future__ import annotations

import os
import re
import tempfile
from getpass import getpass
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".env.local"
VESYNC_LINE = re.compile(r"^(VESYNC_EMAIL|VESYNC_PASSWORD)=")


def replace_vesync_values(source: str, values: dict[str, str]) -> str:
    """Replace only VeSync assignments, preserving other lines verbatim.

    Args:
        source (str): Existing local file content.
        values (dict[str, str]): New VeSync values entered by the user.

    Returns:
        str: Updated local file content.
    """
    output: list[str] = []
    seen: set[str] = set()
    for line in source.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        match = VESYNC_LINE.match(content)
        if match is None:
            output.append(line)
            continue
        name = match.group(1)
        seen.add(name)
        output.append(f"{name}={_literal(values[name])}{line[len(content) :]}")

    result = "".join(output)
    for name in ("VESYNC_EMAIL", "VESYNC_PASSWORD"):
        if name not in seen:
            if result and not result.endswith(("\n", "\r")):
                result += "\n"
            result += f"{name}={_literal(values[name])}\n"
    return result


def _literal(value: str) -> str:
    if "\n" in value or "\r" in value or value.endswith("\\"):
        msg = "VeSync value cannot be represented safely in .env.local"
        raise ValueError(msg)
    return "'" + value.replace("'", "\\'") + "'"


def main() -> None:
    """Write the two local values to the ignored file with owner-only access.

    Raises:
        RuntimeError: If the local file is missing or is a symlink.
    """
    if ENV_PATH.is_symlink() or not ENV_PATH.is_file():
        msg = ".env.local must be an existing regular file"
        raise RuntimeError(msg)

    values = _local_values()
    updated = replace_vesync_values(ENV_PATH.read_text(encoding="utf-8"), values)
    _write_private(ENV_PATH, updated)


def _local_values() -> dict[str, str]:
    names = ("VESYNC_EMAIL", "VESYNC_PASSWORD")
    values = {name: os.environ.get(name, "") for name in names}
    if not any(values.values()):
        values = {name: getpass(f"{name}: ") for name in names}
    if not all(values.values()):
        msg = "Both VeSync values are required"
        raise RuntimeError(msg)
    return values


def _write_private(path: Path, content: str) -> None:
    """Atomically replace the local file and restrict it to its owner.

    Args:
        path (Path): Local file to replace.
        content (str): New content to write.
    """
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".env.local.", delete=False
        ) as temp:
            temp_path = Path(temp.name)
            os.fchmod(temp.fileno(), 0o600)
            temp.write(content)
            temp.flush()
            os.fsync(temp.fileno())
        temp_path.replace(path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
