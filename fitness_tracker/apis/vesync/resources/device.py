"""Device resource."""

from __future__ import annotations

from fitness_tracker.apis.vesync.models.device import Device
from fitness_tracker.apis.vesync.resources._base import Base


class DeviceResource(Base):
    """Resource for device-related endpoints."""

    def list_devices(self, page_no: int = 1, page_size: int = 100) -> list[Device]:
        """List all devices on the VeSync account.

        Args:
            page_no (int): Page number.
            page_size (int): Number of results per page.

        Returns:
            list[Device]: List of connected devices.
        """
        result, _ = self._post(
            "/cloud/v1/deviceManaged/devices",
            body={"method": "devices", "pageNo": page_no, "pageSize": page_size},
        )
        if isinstance(result, dict):
            items = result.get("list", [])
        elif isinstance(result, list):
            items = result
        else:
            items = []
        return [Device(**d) for d in items]
