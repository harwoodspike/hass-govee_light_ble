from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.components.light import (ColorMode, LightEntity, ATTR_BRIGHTNESS, ATTR_RGB_COLOR)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .api import GoveeAPI
from .const import DOMAIN
from .coordinator import GoveeCoordinator

import logging
_LOGGER = logging.getLogger(__name__)

def num_to_range(num, inMin, inMax, outMin, outMax):
    return outMin + (float(num - inMin) / float(inMax - inMin) * (outMax - outMin))

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up a Lights."""
    # This gets the data update coordinator from hass.data as specified in your __init__.py
    coordinator: GoveeCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ].coordinator

    async_add_entities([
        GoveeBluetoothLight(coordinator)
    ], True)


class GoveeBluetoothLight(CoordinatorEntity, LightEntity, RestoreEntity):

    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB

    def __init__(self, coordinator: GoveeCoordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_name = coordinator.device_name
        self._attr_unique_id = f"{coordinator.device_address}"
        self._attr_device_info = DeviceInfo(
            #only generate device once!
            manufacturer="GOVEE",
            model=coordinator.device_name,
            serial_number=coordinator.device_address,
            identifiers={(DOMAIN, coordinator.device_address)}
        )

    async def async_added_to_hass(self) -> None:
        """Start from the last known colour when the device doesn't report one."""
        await super().async_added_to_hass()
        #e.g. the H613C answers colour requests with zeros, so its colour only exists in HA
        if self.coordinator.data.color is None and (last_state := await self.async_get_last_state()):
            rgb = last_state.attributes.get(ATTR_RGB_COLOR)
            if rgb:
                await self.coordinator.restoreColor(tuple(rgb))

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def brightness(self):
        """Return the current brightness. 1-255"""
        return self.coordinator.data.brightness

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self.coordinator.data.state

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the current rgb color."""
        return self.coordinator.data.color

    async def async_turn_on(self, **kwargs):
        """Turn device on."""
        await self.coordinator.setStateBuffered(True)

        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs.get(ATTR_BRIGHTNESS, 255) #1-255
            brightness_mapped = num_to_range(brightness, 1, 255, 0, 255) #mapping from 1-255 to 0-255
            await self.coordinator.setBrightnessBuffered(round(brightness_mapped))

        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs.get(ATTR_RGB_COLOR)
            await self.coordinator.setColorBuffered(red, green, blue)
        elif self.coordinator.data.color is not None:
            #some models (e.g. H613C) stay dark after a bare power-on until a colour is sent
            red, green, blue = self.coordinator.data.color
            await self.coordinator.setColorBuffered(red, green, blue)
        
        await self.coordinator.sendPacketBuffer()

    
    async def async_turn_off(self, **kwargs):
        """Turn device off."""
        await self.coordinator.setStateBuffered(False)
        await self.coordinator.sendPacketBuffer()
