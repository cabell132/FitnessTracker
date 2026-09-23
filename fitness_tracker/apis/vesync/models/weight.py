"""Weight measurement models."""

from __future__ import annotations

import time as _time
from typing import TYPE_CHECKING

from pydantic import Field, model_validator

from fitness_tracker.apis.vesync.models._base import VeSyncModel

if TYPE_CHECKING:
    from fitness_tracker.apis.vesync.models.body_composition import BodyComposition

_FIELD_REMAP: dict[str, str] = {
    "weigh_kg": "weight_kg",
    "weigh_lb": "weight_lbs",
    "impedence": "impedance",
    "heightCm": "height_cm",
    "ID": "record_id",
    "userId": "user_id",
    "subUserID": "sub_user_id",
    "macID": "mac_id",
    "uploadTimestamp": "upload_timestamp",
    "isManualInput": "is_manual_input",
}


def _remap_fields(values: dict) -> dict:
    """Rename API field names to model field names.

    Args:
        values (dict): Raw API response data (mutated in-place).

    Returns:
        dict: Data with renamed keys.
    """
    for api_key, model_key in _FIELD_REMAP.items():
        if api_key in values:
            values.setdefault(model_key, values.pop(api_key))
    return values


def _convert_weight_grams(values: dict) -> dict:
    """Convert V2 ``weightG`` (grams) to kg and lbs.

    Args:
        values (dict): Raw API response data (mutated in-place).

    Returns:
        dict: Data with ``weight_kg`` and ``weight_lbs`` populated.
    """
    if "weightG" in values:
        grams = values.pop("weightG") or 0.0
        values.setdefault("weight_kg", grams / 1000.0)
        values.setdefault("weight_lbs", grams / 453.592)
    return values


class WeightMeasurement(VeSyncModel):
    """A single weight measurement from the scale.

    Normalises both V1 (``weigh_kg``, ``weigh_lb``) and V2
    (``weightG``) API response formats into consistent fields.
    """

    weight_kg: float = 0.0
    weight_lbs: float = 0.0
    impedance: float = 0.0
    timestamp: int = 0
    unit: str = ""
    gender: str = ""
    age: int = 0
    height_cm: float = 0.0
    record_id: int | None = None
    user_id: str | None = None
    sub_user_id: str | None = None
    mac_id: str | None = None
    upload_timestamp: str = ""
    is_manual_input: bool = False

    @property
    def body_composition(self) -> BodyComposition | None:
        """Compute body composition from this measurement's profile data.

        Returns ``None`` when impedance, height, or age are missing/zero.

        Returns:
            BodyComposition | None: Computed body composition, or ``None``.
        """
        from fitness_tracker.apis.vesync.body_composition import calculate  # noqa: PLC0415

        return calculate(self)

    @model_validator(mode="before")
    @classmethod
    def _normalise_fields(cls, values: dict) -> dict:
        """Map V1 and V2 API field names to model fields.

        Args:
            values (dict): Raw API response data.

        Returns:
            dict: Normalised data with consistent field names.
        """
        if not isinstance(values, dict):
            return values
        _convert_weight_grams(values)
        _remap_fields(values)
        return values


class WeightDataPage(VeSyncModel):
    """A paginated page of weight measurement data.

    Handles both V1 (``data`` key, cursor pagination) and V2
    (``weightDatas`` key, page pagination) response formats.
    """

    measurements: list[WeightMeasurement] = Field(default_factory=list)
    page_size: int = Field(default=0, alias="pageSize")
    index: int = 0

    @model_validator(mode="before")
    @classmethod
    def _normalise_list_key(cls, values: dict) -> dict:
        """Extract measurements from V1 ``data`` or V2 ``weightDatas``.

        Args:
            values (dict): Raw API result dict.

        Returns:
            dict: Data with ``measurements`` key populated.
        """
        if not isinstance(values, dict):
            return values

        items = values.pop("data", None) or values.pop("weightDatas", None) or []
        values.setdefault("measurements", items)
        return values


def default_end_time() -> int:
    """Return the current epoch time as a default end-time bound.

    Returns:
        int: Current Unix timestamp.
    """
    return int(_time.time())
