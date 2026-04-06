"""User info models for the Hevy API."""

from __future__ import annotations

from pydantic import BaseModel


class UserInfo(BaseModel):
    """Authenticated user profile from the Hevy API."""

    id: str
    name: str
    url: str


class UserInfoResponse(BaseModel):
    """Wrapper returned by ``GET /v1/user/info``."""

    data: UserInfo
