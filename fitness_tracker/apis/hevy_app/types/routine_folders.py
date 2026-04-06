"""Routine folder models for the Hevy API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoutineFolder(BaseModel):
    """Routine folder returned by the routine-folders API."""

    id: int
    index: int
    title: str
    updated_at: str
    created_at: str


class RoutineFolderResponse(BaseModel):
    """Paginated list of routine folders."""

    page: int
    page_count: int
    routine_folders: list[RoutineFolder]


class PostRoutineFolderRequest(BaseModel):
    """Inner folder payload for creating a routine folder."""

    title: str = Field(description="The title of the routine folder.")


class PostRoutineFolderRequestBody(BaseModel):
    """Wrapper object expected by ``POST /v1/routine_folders``."""

    routine_folder: PostRoutineFolderRequest
