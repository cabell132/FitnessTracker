"""Weight data resource."""

from __future__ import annotations

from datetime import datetime

from fitness_tracker.apis.vesync.models.device import Device
from fitness_tracker.apis.vesync.models.weight import WeightDataPage, default_end_time
from fitness_tracker.apis.vesync.resources._base import Base


class WeightResource(Base):
    """Resource for weight data endpoints."""

    def get_weight_data(  # noqa: PLR0913 - public query options from Caloric
        self,
        device: Device,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page_size: int = 100,
        order: str = "desc",
    ) -> WeightDataPage:
        """Get weight measurements using the V1 endpoint.

        Suitable for WiFi-connected scales (e.g. ESF00+, ESF16B).

        Args:
            device (Device): The scale device.
            start_time (datetime | None): Start of time range. Defaults to epoch 0.
            end_time (datetime | None): End of time range. Defaults to now.
            page_size (int): Number of results per page.
            order (str): Sort order (``"desc"`` or ``"asc"``).

        Returns:
            WeightDataPage: Paginated weight measurement data.
        """
        start_ts = int(start_time.timestamp()) if start_time is not None else 0
        end_ts = int(end_time.timestamp()) if end_time is not None else default_end_time()
        result, _ = self._post(
            "/cloud/v1/deviceManaged/fatScale/getWeighData",
            body={
                "method": "getWeighData",
                "configModule": device.config_module,
                "cid": device.cid,
                "startTime": start_ts,
                "endTime": end_ts,
                "pageSize": page_size,
                "order": order,
                "index": 0,
                "flag": 1,
            },
        )
        if isinstance(result, dict):
            return WeightDataPage(**result)
        return WeightDataPage()

    def get_weight_data_v2(  # noqa: PLR0913 - public query options from Caloric
        self,
        device: Device,
        all_data: bool = True,
        page: int = 1,
        page_size: int = 100,
    ) -> WeightDataPage:
        """Get weight measurements using the V2 endpoint.

        Suitable for Bluetooth and Wi-Fi/Bluetooth scales (e.g. ESF14, EFS-A591S).

        Args:
            device (Device): The scale device.
            all_data (bool): Whether to return all data.
            page (int): Page number.
            page_size (int): Number of results per page.

        Returns:
            WeightDataPage: Paginated weight measurement data.
        """
        result, _ = self._post(
            "/cloud/v2/deviceManaged/getWeighingDataV2",
            body={
                "method": "getWeighingDataV2",
                "configModule": device.config_module,
                "allData": all_data,
                "debugMode": False,
                "deviceRegion": device.device_region,
                "page": page,
                "pageSize": page_size,
            },
        )
        if isinstance(result, dict):
            return WeightDataPage(**result)
        return WeightDataPage()
