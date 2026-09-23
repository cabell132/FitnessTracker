"""Device-related models."""

from __future__ import annotations

from pydantic import Field, model_validator

from fitness_tracker.apis.vesync.models._base import VeSyncModel


class Device(VeSyncModel):
    """A VeSync-connected device."""

    device_name: str = Field(default="", alias="deviceName")
    cid: str | None = None
    device_type: str = Field(default="", alias="deviceType")
    type: str = Field(default="")
    config_module: str = Field(default="", alias="configModule")
    connection_status: str = Field(default="", alias="connectionStatus")
    connection_type: str = Field(default="", alias="connectionType")
    device_status: str = Field(default="", alias="deviceStatus")
    device_region: str = Field(default="", alias="deviceRegion")
    device_img: str = Field(default="", alias="deviceImg")
    is_owner: bool = Field(default=False, alias="isOwner")
    sub_device_no: int | None = Field(default=None, alias="subDeviceNo")
    sub_device_type: str | None = Field(default=None, alias="subDeviceType")
    product_type: str | None = Field(default=None, alias="productType")
    current_firm_version: str | None = Field(default=None, alias="currentFirmVersion")
    uuid: str | None = None
    mac_id: str | None = Field(default=None, alias="macID")
    mode: str | None = None
    speed: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _fill_cid(cls, values: dict) -> dict:
        """Fall back to uuid or macID when cid is null.

        Args:
            values (dict): Raw input data before validation.

        Returns:
            dict: Input data with cid populated from fallback fields.
        """
        if isinstance(values, dict) and values.get("cid") is None:
            values["cid"] = values.get("uuid") or values.get("macID")
        return values
