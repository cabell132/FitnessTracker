"""CLI commands for bootstrapping and refreshing Hevy web credentials."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.hevy_app.web_auth import (
    HevyWebAuth,
    HevyWebCredentialStore,
    HevyWebCredentials,
    default_hevy_web_credentials_path,
)


def add_hevy_auth_parser(subparsers: Any) -> None:
    """Register ``hevy auth`` maintenance commands.

    Args:
        subparsers (Any): Parent Hevy argparse subparser collection.
    """
    auth = subparsers.add_parser(
        "auth",
        description=(
            "Import the auth2.0-token cookie from an authenticated Hevy browser, "
            "then inspect or rotate the stored credentials."
        ),
    )
    auth_subparsers = auth.add_subparsers(dest="hevy_auth_command")

    import_cookie = auth_subparsers.add_parser(
        "import-cookie",
        description=(
            "After logging into hevy.com, copy the auth2.0-token value from the browser's "
            "Application > Cookies panel. Pipe it with --stdin to avoid a temporary secret file."
        ),
    )
    import_cookie.add_argument("cookie_file", nargs="?")
    import_cookie.add_argument(
        "--stdin",
        action="store_true",
        help="Read the cookie value from stdin so no temporary secret file is needed.",
    )
    _add_common_arguments(import_cookie)

    status = auth_subparsers.add_parser("status")
    _add_common_arguments(status)

    refresh = auth_subparsers.add_parser("refresh")
    _add_common_arguments(refresh)


def run_hevy_auth_command(args: argparse.Namespace) -> int:
    """Execute a parsed ``hevy auth`` command.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.

    Returns:
        int: Process exit code.
    """
    store = HevyWebCredentialStore(Path(args.store_path))
    try:
        if args.hevy_auth_command == "import-cookie":
            raw_payload = _read_cookie_payload(args)
            credentials = store.import_cookie_payload(raw_payload)
            return _emit_status(args, store, credentials)
        if args.hevy_auth_command == "status":
            credentials = store.load()
            if credentials is None:
                return _emit_missing(args, store)
            return _emit_status(args, store, credentials)
        if args.hevy_auth_command == "refresh":
            credentials = HevyWebAuth(store=store, legacy_token="").refresh(force=True)
            return _emit_status(args, store, credentials)
    except (HevyAppAPIError, OSError, TypeError, ValueError) as exc:
        return _emit_error(args, str(exc))
    return _emit_error(args, "Choose import-cookie, status, or refresh")


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store-path",
        default=str(default_hevy_web_credentials_path()),
        help="Rotating Hevy credential file path.",
    )
    parser.add_argument("--json", action="store_true")


def _read_cookie_payload(args: argparse.Namespace) -> str:
    if args.stdin and args.cookie_file:
        message = "Provide either a cookie file or --stdin, not both"
        raise ValueError(message)
    if args.stdin:
        return sys.stdin.read()
    if args.cookie_file:
        return Path(args.cookie_file).read_text(encoding="utf-8")
    message = "Provide a cookie file or pipe the auth2.0-token cookie value with --stdin"
    raise ValueError(message)


def _status_payload(
    store: HevyWebCredentialStore,
    credentials: HevyWebCredentials,
) -> dict[str, object]:
    access_token_expired = credentials.expires_at <= datetime.now(UTC)
    return {
        "ok": True,
        "access_token_valid": not access_token_expired,
        "refresh_token_present": True,
        "expires_at": credentials.expires_at.isoformat(),
        "store_path": str(store.path),
    }


def _emit_status(
    args: argparse.Namespace,
    store: HevyWebCredentialStore,
    credentials: HevyWebCredentials,
) -> int:
    payload = _status_payload(store, credentials)
    if args.json:
        sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    else:
        sys.stdout.write(f"Hevy web authentication expires at {payload['expires_at']}\n")
        sys.stdout.write(f"Access token valid: {payload['access_token_valid']}\n")
        sys.stdout.write(f"Refresh token present: {payload['refresh_token_present']}\n")
        sys.stdout.write(f"Credential store: {payload['store_path']}\n")
    return 0


def _emit_missing(args: argparse.Namespace, store: HevyWebCredentialStore) -> int:
    payload = {
        "ok": False,
        "access_token_valid": False,
        "refresh_token_present": False,
        "store_path": str(store.path),
    }
    if args.json:
        sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    else:
        sys.stdout.write(f"Hevy web credentials not found at {store.path}\n")
    return 1


def _emit_error(args: argparse.Namespace, message: str) -> int:
    if args.json:
        sys.stdout.write(json.dumps({"ok": False, "error": message}, sort_keys=True) + "\n")
    else:
        sys.stderr.write(f"Error: {message}\n")
    return 2
