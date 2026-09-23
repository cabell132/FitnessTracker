"""Base model for all VeSync API models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class VeSyncModel(BaseModel):
    """Base model for VeSync API responses."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)
