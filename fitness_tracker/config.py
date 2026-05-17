"""Application configuration loaded once at the composition root."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv
from pydantic import SecretStr


@dataclass(frozen=True)
class Config:
    """Immutable bundle of every configurable value in the application."""

    hevy_api_key: SecretStr
    hevy_web_api_key: SecretStr
    openai_api_key: SecretStr
    truecoach_password: SecretStr
    dropbox_access_token: SecretStr
    email: str
    database_url: str = "sqlite:///fitness_tracker.db"
    llm_model: str = "gpt-4o-mini-2024-07-18"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 150

    @classmethod
    def required_env_vars(cls) -> tuple[str, ...]:
        """Return the required environment variable names.

        Returns:
            tuple[str, ...]: Required names in stable display order.
        """
        return (
            "DROPBOX_ACCESS_TOKEN",
            "EMAIL",
            "HEVY_API_KEY",
            "HEVY_WEB_API_KEY",
            "OPENAI_API_KEY",
            "TRUECOACH_PASSWORD",
        )

    @classmethod
    def from_env(cls) -> Config:
        """Load ``.env`` once, validate required settings, and return config.

        Returns:
            Config: Fully populated application configuration.
        """
        load_dotenv()
        missing = [name for name in cls.required_env_vars() if not os.environ.get(name)]
        if missing:
            sys.exit(
                "Missing required environment variables:\n"
                + "\n".join(f"  - {name}" for name in missing)
            )
        return cls(
            hevy_api_key=SecretStr(os.environ["HEVY_API_KEY"]),
            hevy_web_api_key=SecretStr(os.environ["HEVY_WEB_API_KEY"]),
            openai_api_key=SecretStr(os.environ["OPENAI_API_KEY"]),
            truecoach_password=SecretStr(os.environ["TRUECOACH_PASSWORD"]),
            dropbox_access_token=SecretStr(os.environ["DROPBOX_ACCESS_TOKEN"]),
            email=os.environ["EMAIL"],
            database_url=os.environ.get("DATABASE_URL", cls.database_url),
        )
