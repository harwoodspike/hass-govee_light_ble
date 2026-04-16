from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)

from .const import DOMAIN
from .api import GoveeAPI

import logging
_LOGGER = logging.getLogger(__name__)

@dataclass
class GoveeApiData:
    """Class to hold api data."""

    state: bool | None = None
    brightness: int | None = None
    color: tuple[int, ...] | None = None

class GoveeCoordinator(DataUpdateCoordinator):
    """My coordinator."""

    data: GoveeApiData

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize coordinator."""

        # Set variables from values entered in config flow setup
        self.device_name = config_entry.data[CONF_NAME]
        self.device_address = config_entry.data[CONF_ADDRESS]
        self.device_segmented = config_entry.data["segmented"]

        #get connection to bluetooth device
        ble_device = bluetooth.async_ble_device_from_address(
            hass,
            self.device_address,
            connectable=False
        )
        assert ble_device
        self._api = GoveeAPI(ble_device, self._async_push_data, self.device_segmented)

        config_entry.async_on_unload(
            bluetooth.async_register_callback(
                hass,
                self._async_ble_device_update,
                BluetoothCallbackMatcher(address=self.device_address),
                BluetoothScanningMode.PASSIVE,
            )
        )

        # Initialise DataUpdateCoordinator
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            # Set update method to get devices on first load.
            update_method=self._async_update_data,
            # Do not set a polling interval as data will be pushed.
            # You can remove this line but left here for explanatory purposes.
            update_interval=timedelta(seconds=15)
        )

    def _async_ble_device_update(self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange) -> None:
        self._api.update_ble_device(service_info.device)

    def _get_data(self):
        return GoveeApiData(
            state=self._api.state,
            brightness=self._api.brightness,
            color=self._api.color
        )

    async def _async_push_data(self):
        self.async_set_updated_data(self._get_data())

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        await self._api.requestStateBuffered()
        await self._api.requestBrightnessBuffered()
        await self._api.requestColorBuffered()
        await self._api.sendPacketBuffer()
        return self._get_data()

    async def setStateBuffered(self, state: bool):
        await self._api.setStateBuffered(state)

    async def setBrightnessBuffered(self, brightness: int):
        await self._api.setBrightnessBuffered(brightness)

    async def setColorBuffered(self, red: int, green: int, blue: int):
        await self._api.setColorBuffered(red, green, blue)

    async def sendPacketBuffer(self):
        await self._api.sendPacketBuffer()
