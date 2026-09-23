"""Offline tests for the copied VeSync scale client."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fitness_tracker.apis.vesync import VeSyncClient
from fitness_tracker.apis.vesync.body_composition import calculate
from fitness_tracker.apis.vesync.cache import FileCacheHandler, MemoryCacheHandler
from fitness_tracker.apis.vesync.exceptions import VeSyncAPIError
from fitness_tracker.apis.vesync.models.device import Device
from fitness_tracker.apis.vesync.models.weight import WeightMeasurement
from fitness_tracker.apis.vesync.resources.weight import WeightResource
from fitness_tracker.apis.vesync.session import VeSyncSession


def test_wifi_scale_data_is_normalised() -> None:
    session = MagicMock()
    session.make_request.return_value = {
        "code": 0,
        "result": {
            "data": [{"weigh_kg": 75.3, "weigh_lb": 166.0, "timestamp": 1710000000}],
        },
    }
    scale = Device(cid="scale-1", configModule="WiFiScale_ESFS16B")

    page = WeightResource(session).get_weight_data(scale)

    assert page.measurements[0].weight_kg == pytest.approx(75.3)
    session.make_request.assert_called_once()
    assert session.make_request.call_args.args[0] == "/cloud/v1/deviceManaged/fatScale/getWeighData"
    assert session.make_request.call_args.kwargs["body"]["cid"] == "scale-1"


def test_bluetooth_scale_data_is_normalised() -> None:
    session = MagicMock()
    session.make_request.return_value = {
        "code": 0,
        "result": {
            "weightDatas": [{"weightG": 75300, "timestamp": 1710000000, "subUserID": "profile-1"}]
        },
    }
    scale = Device(configModule="BT_Scale_ESF14_US", deviceRegion="US")

    page = WeightResource(session).get_weight_data_v2(scale)

    assert page.measurements[0].weight_kg == pytest.approx(75.3)
    assert page.measurements[0].sub_user_id == "profile-1"
    assert session.make_request.call_args.args[0] == "/cloud/v2/deviceManaged/getWeighingDataV2"


def test_vesync_error_code_raises() -> None:
    session = MagicMock()
    session.make_request.return_value = {"code": 1001, "msg": "Device unavailable"}

    with pytest.raises(VeSyncAPIError, match="Device unavailable"):
        WeightResource(session).get_weight_data(Device(cid="scale-1"))


def test_find_scale_uses_device_discovery() -> None:
    client = VeSyncClient("person@example.com", "password", cache_handler=MemoryCacheHandler())
    client.device.list_devices = MagicMock(
        return_value=[Device(deviceType="fan"), Device(configModule="WiFiScale_ESFS16B")]
    )

    assert client.find_scale().config_module == "WiFiScale_ESFS16B"


def test_find_scale_recognises_efs_wifi_bluetooth_scale() -> None:
    client = VeSyncClient("person@example.com", "password", cache_handler=MemoryCacheHandler())
    client.device.list_devices = MagicMock(
        return_value=[
            Device(deviceType="fan"),
            Device(deviceType="EFS-A591S-EU", configModule="VS_WB_SCL_EFS-A591S-EU_EU"),
        ]
    )

    assert client.find_scale().device_type == "EFS-A591S-EU"


def test_client_uses_varlock_injected_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VESYNC_EMAIL", "person@example.com")
    monkeypatch.setenv("VESYNC_PASSWORD", "password")

    client = VeSyncClient.from_env()

    assert client.session._email == "person@example.com"


def test_cached_token_can_fetch_without_logging_in() -> None:
    cache = MemoryCacheHandler()
    cache.save_token({"token": "cached", "accountID": "account", "expiresAt": time.time() + 3600})
    session = VeSyncSession("person@example.com", "password", cache_handler=cache)
    response = MagicMock()
    response.status_code.as_int.return_value = 200
    response.json.return_value = {"code": 0, "result": {}}
    session._client = MagicMock()
    session._client.post.return_value = response

    with patch("fitness_tracker.apis.vesync.session.login") as login:
        assert session.make_request("/cloud/test") == {"code": 0, "result": {}}

    login.assert_not_called()
    assert session._client.post.call_args.kwargs["json"]["token"] == "cached"


def test_body_composition_is_available_from_scale_measurement() -> None:
    measurement = WeightMeasurement(
        weight_kg=75.3,
        impedance=520,
        gender="2",
        age=30,
        height_cm=180,
    )

    assert measurement.body_composition.body_fat_pct == pytest.approx(15.5)


def test_athlete_body_fat_matches_app_sample() -> None:
    # Published athlete-mode hardware capture from etekcity_esf551_ble.
    measurement = WeightMeasurement(
        weight_kg=74.55, height_cm=170, age=43, gender="2", impedance=526
    )

    assert calculate(measurement, athlete=True).body_fat_pct == 14.5


def test_cached_token_is_written_privately(tmp_path: Path) -> None:
    path = tmp_path / ".cache-vesync-tokens"
    cache = FileCacheHandler(path)

    cache.save_token({"token": "test-token"})

    assert cache.get_token() == {"token": "test-token"}
    assert path.stat().st_mode & 0o777 == 0o600
