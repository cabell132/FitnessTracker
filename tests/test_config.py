"""Tests for application configuration."""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine

from fitness_tracker.config import Config
from fitness_tracker.sync._deps import SyncDeps


def test_from_env_reports_all_missing_required_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing required settings are reported together at startup."""
    for name in Config.required_env_vars():
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(SystemExit) as exc_info:
        Config.from_env()

    message = str(exc_info.value)
    assert "Missing required environment variables:" in message
    for name in Config.required_env_vars():
        assert f"  - {name}" in message


def test_sync_deps_from_config_wires_configured_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production dependency wiring consumes credentials from Config."""
    captured: dict[str, object] = {}

    class FakeHevy:
        def __init__(self, *, api_key: str, web_api_key: str) -> None:
            captured["hevy_api_key"] = api_key
            captured["hevy_web_api_key"] = web_api_key

    class FakeTrueCoach:
        def __init__(self, *, email: str, password: str) -> None:
            captured["email"] = email
            captured["truecoach_password"] = password

    class FakeLLM:
        def __init__(  # noqa: PLR0913
            self,
            model_name: str,
            *,
            api_key: str,
            temperature: float,
            max_completion_tokens: int,
        ) -> None:
            captured["llm_model"] = model_name
            captured["openai_api_key"] = api_key
            captured["llm_temperature"] = temperature
            captured["llm_max_tokens"] = max_completion_tokens

    class FakeDropbox:
        def __init__(self, access_token: str) -> None:
            captured["dropbox_access_token"] = access_token

    monkeypatch.setattr("fitness_tracker.sync._deps.HevyAppClient", FakeHevy)
    monkeypatch.setattr("fitness_tracker.sync._deps.TrueCoachClient", FakeTrueCoach)
    monkeypatch.setattr("fitness_tracker.sync._deps.FitnessLLM", FakeLLM)
    monkeypatch.setattr("fitness_tracker.sync._deps.dropbox.Dropbox", FakeDropbox)

    cfg = Config(
        hevy_api_key=SecretStr("hevy"),
        hevy_web_api_key=SecretStr("web"),
        openai_api_key=SecretStr("openai"),
        truecoach_password=SecretStr("tc-pass"),
        dropbox_access_token=SecretStr("dbx"),
        email="coach@example.com",
        llm_model="model",
        llm_temperature=0.25,
        llm_max_tokens=300,
    )

    SyncDeps.from_config(create_engine("sqlite:///:memory:"), cfg)

    assert captured == {
        "hevy_api_key": "hevy",
        "hevy_web_api_key": "web",
        "email": "coach@example.com",
        "truecoach_password": "tc-pass",
        "llm_model": "model",
        "openai_api_key": "openai",
        "llm_temperature": 0.25,
        "llm_max_tokens": 300,
        "dropbox_access_token": "dbx",
    }
