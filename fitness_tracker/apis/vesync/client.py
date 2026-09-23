"""VeSync API client."""

from __future__ import annotations

import os
from typing import Self

from fitness_tracker.apis.vesync.cache import CacheHandler
from fitness_tracker.apis.vesync.models.device import Device
from fitness_tracker.apis.vesync.resources.device import DeviceResource
from fitness_tracker.apis.vesync.resources.weight import WeightResource
from fitness_tracker.apis.vesync.session import VeSyncSession


class VeSyncClient:
    """A class that represents a VeSync API client."""

    def __init__(
        self,
        email: str,
        password: str,
        cache_handler: CacheHandler | None = None,
    ) -> None:
        """Initialise a new VeSync API client.

        Args:
            email (str): VeSync account email address.
            password (str): VeSync account password (plaintext).
            cache_handler (CacheHandler | None): Pluggable token cache.
                When ``None``, a file-based cache is created automatically.
        """
        self.session = VeSyncSession(
            email=email,
            password=password,
            cache_handler=cache_handler,
        )
        self.device = DeviceResource(session=self.session)
        self.weight = WeightResource(session=self.session)

    @classmethod
    def from_env(cls) -> Self:
        """Create a client from the environment injected by Varlock.

        Returns:
            Self: VeSync client for the configured account.

        Raises:
            RuntimeError: If a VeSync credential is missing.
        """
        missing = [name for name in ("VESYNC_EMAIL", "VESYNC_PASSWORD") if not os.environ.get(name)]
        if missing:
            msg = f"Missing VeSync environment variable(s): {', '.join(missing)}"
            raise RuntimeError(msg)
        return cls(os.environ["VESYNC_EMAIL"], os.environ["VESYNC_PASSWORD"])

    @property
    def account_id(self) -> str | None:
        """The authenticated VeSync account ID.

        Delegates to the underlying session.

        Returns:
            str | None: The account ID.
        """
        return self.session.account_id

    def find_scale(self) -> Device:
        """Find the first scale connected to this VeSync account.

        Returns:
            Device: The scale device.

        Raises:
            RuntimeError: If the account has no scale.
        """
        for device in self.device.list_devices():
            device_type = device.device_type.lower()
            config_module = device.config_module.lower()
            if (
                "scale" in device_type
                or device_type.startswith(("esf", "efs"))
                or "esf" in config_module
                or "_scl_" in config_module
            ):
                return device
        msg = "No scale device found on VeSync account."
        raise RuntimeError(msg)
