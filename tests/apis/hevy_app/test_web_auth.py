"""Tests for Hevy web access-token refresh and persistence."""

from __future__ import annotations

import json
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.hevy_app.web_auth import (
    HevyWebAuth,
    HevyWebCredentials,
    HevyWebCredentialStore,
)
from fitness_tracker.apis.hevy_app.web_session import HevyWebSession


def _response(*, status: int = 200, body: dict[str, object] | None = None) -> MagicMock:
    response = MagicMock()
    response.ok = 200 <= status < 300
    response.status_code = status
    response.url = "https://api.hevyapp.com/auth/refresh_token"
    response.text = json.dumps(body or {})
    response.json.return_value = body or {}
    return response


def _credentials(*, expires_at: datetime, suffix: str = "old") -> HevyWebCredentials:
    return HevyWebCredentials(
        access_token=f"access-{suffix}",
        refresh_token=f"refresh-{suffix}",
        expires_at=expires_at,
    )


def test_refreshes_expired_credentials_and_persists_rotated_pair(tmp_path: Path) -> None:
    now = datetime(2026, 8, 10, 17, 0, tzinfo=UTC)
    store = HevyWebCredentialStore(tmp_path / "hevy-auth.json")
    store.save(_credentials(expires_at=now - timedelta(seconds=1)))
    transport = MagicMock(
        return_value=_response(
            body={
                "access_token": "access-new",
                "refresh_token": "refresh-new",
                "expires_at": "2026-08-10T17:15:00.000Z",
            }
        )
    )
    auth = HevyWebAuth(
        store=store,
        legacy_token="legacy",  # noqa: S106
        transport=transport,
        clock=lambda: now,
    )

    token = auth.access_token()

    assert token == "access-new"
    assert store.load() == _credentials(
        expires_at=datetime(2026, 8, 10, 17, 15, tzinfo=UTC), suffix="new"
    )
    request = transport.call_args
    assert request.args == ("POST", "https://api.hevyapp.com/auth/refresh_token")
    assert request.kwargs["json"] == {"refresh_token": "refresh-old"}
    assert request.kwargs["headers"]["Authorization"] == "Bearer access-old"
    assert request.kwargs["headers"]["hevy-platform"] == "web"
    assert request.kwargs["headers"]["x-api-key"] == "shelobs_hevy_web"


def test_reuses_unexpired_credentials_without_refresh(tmp_path: Path) -> None:
    now = datetime(2026, 8, 10, 17, 0, tzinfo=UTC)
    store = HevyWebCredentialStore(tmp_path / "hevy-auth.json")
    store.save(_credentials(expires_at=now + timedelta(minutes=10)))
    transport = MagicMock()
    auth = HevyWebAuth(
        store=store,
        legacy_token="legacy",  # noqa: S106
        transport=transport,
        clock=lambda: now,
    )

    assert auth.access_token() == "access-old"
    transport.assert_not_called()


def test_uses_legacy_token_when_no_refresh_credentials_exist(tmp_path: Path) -> None:
    auth = HevyWebAuth(
        store=HevyWebCredentialStore(tmp_path / "missing.json"),
        legacy_token="legacy",  # noqa: S106
    )

    assert auth.access_token() == "legacy"
    assert auth.has_rotating_credentials is False


def test_web_session_uses_token_supplied_by_auth_manager(tmp_path: Path) -> None:
    now = datetime(2026, 8, 10, 17, 0, tzinfo=UTC)
    store = HevyWebCredentialStore(tmp_path / "hevy-auth.json")
    store.save(_credentials(expires_at=now + timedelta(minutes=10)))
    auth = HevyWebAuth(store=store, legacy_token="legacy", clock=lambda: now)  # noqa: S106
    session = HevyWebSession(auth=auth)

    with patch("fitness_tracker.apis.session.requests.Session") as session_class:
        request = session_class.return_value.__enter__.return_value.request
        request.return_value = _response(body={})
        session.make_request("GET", "/custom_exercise_templates")

    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer access-old"
    assert "auth-token" not in request.call_args.kwargs["headers"]


def test_web_session_refreshes_and_retries_once_after_401(tmp_path: Path) -> None:
    now = datetime(2026, 8, 10, 17, 0, tzinfo=UTC)
    store = HevyWebCredentialStore(tmp_path / "hevy-auth.json")
    store.save(_credentials(expires_at=now + timedelta(minutes=10)))
    refresh_transport = MagicMock(
        return_value=_response(
            body={
                "access_token": "access-new",
                "refresh_token": "refresh-new",
                "expires_at": "2026-08-10T17:15:00.000Z",
            }
        )
    )
    auth = HevyWebAuth(
        store=store,
        legacy_token="",
        transport=refresh_transport,
        clock=lambda: now,
    )
    session = HevyWebSession(auth=auth)

    with patch("fitness_tracker.apis.session.requests.Session") as session_class:
        request = session_class.return_value.__enter__.return_value.request
        request.side_effect = [
            _response(status=401, body={"error": "AccessTokenExpired"}),
            _response(body={}),
        ]
        session.make_request("GET", "/custom_exercise_templates")

    assert request.call_count == 2
    assert request.call_args_list[0].kwargs["headers"]["Authorization"] == "Bearer access-old"
    assert request.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer access-new"
    assert store.load() == _credentials(
        expires_at=datetime(2026, 8, 10, 17, 15, tzinfo=UTC), suffix="new"
    )


def test_refresh_rejection_requests_browser_reauthentication(tmp_path: Path) -> None:
    now = datetime(2026, 8, 10, 17, 0, tzinfo=UTC)
    store = HevyWebCredentialStore(tmp_path / "hevy-auth.json")
    store.save(_credentials(expires_at=now - timedelta(seconds=1)))
    auth = HevyWebAuth(
        store=store,
        legacy_token="",
        transport=MagicMock(return_value=_response(status=401)),
        clock=lambda: now,
    )

    with pytest.raises(HevyAppAPIError, match="Reauthenticate in the Hevy browser"):
        auth.access_token()


def test_credential_store_writes_secrets_with_owner_only_permissions(tmp_path: Path) -> None:
    store = HevyWebCredentialStore(tmp_path / "hevy-auth.json")

    store.save(_credentials(expires_at=datetime(2026, 8, 10, 17, 15, tzinfo=UTC)))

    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_concurrent_expired_token_callers_rotate_refresh_token_once(tmp_path: Path) -> None:
    now = datetime(2026, 8, 10, 17, 0, tzinfo=UTC)
    store = HevyWebCredentialStore(tmp_path / "hevy-auth.json")
    store.save(_credentials(expires_at=now - timedelta(seconds=1)))
    calls: list[str] = []
    calls_lock = threading.Lock()
    start = threading.Barrier(2)

    def transport(*args, **kwargs):
        with calls_lock:
            calls.append(kwargs["json"]["refresh_token"])
        return _response(
            body={
                "access_token": "access-new",
                "refresh_token": "refresh-new",
                "expires_at": "2026-08-10T17:15:00.000Z",
            }
        )

    auth_instances = [
        HevyWebAuth(store=store, legacy_token="", transport=transport, clock=lambda: now)
        for _ in range(2)
    ]

    def access_token(auth: HevyWebAuth) -> str:
        start.wait()
        return auth.access_token()

    with ThreadPoolExecutor(max_workers=2) as executor:
        tokens = list(executor.map(access_token, auth_instances))

    assert tokens == ["access-new", "access-new"]
    assert calls == ["refresh-old"]
