"""Tests for Hevy web authentication maintenance commands."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

from fitness_tracker import cli
from fitness_tracker.config import Config


def test_hevy_auth_import_cookie_persists_credentials_without_printing_secrets(
    tmp_path: Path,
    capsys,
) -> None:
    cookie_path = tmp_path / "browser-cookie.json"
    store_path = tmp_path / "hevy-auth.json"
    cookie_path.write_text(
        json.dumps(
            {
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "expires_at": "2099-08-10T17:15:00.000Z",
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "hevy",
            "auth",
            "import-cookie",
            str(cookie_path),
            "--store-path",
            str(store_path),
            "--json",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert json.loads(output) == {
        "ok": True,
        "access_token_valid": True,
        "refresh_token_present": True,
        "expires_at": "2099-08-10T17:15:00+00:00",
        "store_path": str(store_path),
    }
    assert "access-secret" not in output
    assert "refresh-secret" not in output
    assert json.loads(store_path.read_text(encoding="utf-8"))["refresh_token"] == "refresh-secret"


def test_hevy_auth_status_reports_missing_credentials(tmp_path: Path, capsys) -> None:
    store_path = tmp_path / "missing.json"

    exit_code = cli.main(["hevy", "auth", "status", "--store-path", str(store_path), "--json"])

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out) == {
        "ok": False,
        "access_token_valid": False,
        "refresh_token_present": False,
        "store_path": str(store_path),
    }


def test_hevy_auth_import_cookie_accepts_stdin_without_a_secret_file(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    store_path = tmp_path / "hevy-auth.json"
    monkeypatch.setattr(
        sys,
        "stdin",
        StringIO(
            json.dumps(
                {
                    "access_token": "access-secret",
                    "refresh_token": "refresh-secret",
                    "expires_at": "2099-08-10T17:15:00.000Z",
                }
            )
        ),
    )

    exit_code = cli.main(
        [
            "hevy",
            "auth",
            "import-cookie",
            "--stdin",
            "--store-path",
            str(store_path),
            "--json",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "access-secret" not in output
    assert "refresh-secret" not in output
    assert json.loads(output)["refresh_token_present"] is True


def test_hevy_auth_refresh_rotates_stored_credentials(tmp_path: Path, monkeypatch, capsys) -> None:
    store_path = tmp_path / "hevy-auth.json"
    store_path.write_text(
        json.dumps(
            {
                "access_token": "access-old",
                "refresh_token": "refresh-old",
                "expires_at": "2099-08-10T17:15:00.000Z",
            }
        ),
        encoding="utf-8",
    )
    response = MagicMock()
    response.ok = True
    response.status_code = 200
    response.url = "https://api.hevyapp.com/auth/refresh_token"
    response.json.return_value = {
        "access_token": "access-new",
        "refresh_token": "refresh-new",
        "expires_at": "2099-08-10T17:30:00.000Z",
    }
    monkeypatch.setattr(
        "fitness_tracker.apis.hevy_app.web_auth.requests.request", lambda *a, **k: response
    )

    exit_code = cli.main(["hevy", "auth", "refresh", "--store-path", str(store_path), "--json"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "access-new" not in output
    assert "refresh-new" not in output
    assert json.loads(store_path.read_text(encoding="utf-8"))["refresh_token"] == "refresh-new"


def test_config_does_not_require_legacy_hevy_web_token(monkeypatch) -> None:
    monkeypatch.setattr("fitness_tracker.config.load_dotenv", lambda: None)
    monkeypatch.delenv("HEVY_WEB_API_KEY", raising=False)
    for name in Config.required_env_vars():
        monkeypatch.setenv(name, "configured")

    config = Config.from_env()

    assert config.hevy_web_api_key.get_secret_value() == ""


def test_hevy_routine_delete_uses_refreshing_client(monkeypatch, capsys) -> None:
    deleted: list[str] = []

    class FakeRoutines:
        def delete(self, routine_id: str) -> None:
            deleted.append(routine_id)

    class FakeClient:
        routines = FakeRoutines()

    monkeypatch.setattr(cli, "_hevy_client_from_config", lambda: FakeClient())

    exit_code = cli.main(["hevy", "routines", "delete", "routine-1", "--yes", "--json"])

    assert exit_code == 0
    assert deleted == ["routine-1"]
    assert json.loads(capsys.readouterr().out)["action"] == "deleted"
