from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.components.light import (ColorMode, LightEntity, ATTR_BRIGHTNESS, ATTR_RGB_COLOR)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .api import GoveeAPI
from .const import DOMAIN
from .coordinator import GoveeCoordinator

import logging
_LOGGER = logging.getLogger(__name__)

#used for a bare turn_on when no colour has ever been known (e.g. a fresh install)
_DEFAULT_COLOR = (255, 255, 255)


@dataclass
class GoveeLightExtraStoredData(ExtraStoredData):
    """ last colour and brightness, kept while the light is off (HA drops them from the off state) """

    color: tuple[int, int, int] | None
    brightness: int | None

    def as_dict(self) -> dict[str, Any]:
        return {"color": list(self.color) if self.color else None, "brightness": self.brightness}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoveeLightExtraStoredData:
        color = data.get("color")
        return cls(tuple(color) if color else None, data.get("brightness"))

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
        #e.g. the H613C answers colour requests with zeros, so its colour only exists in HA.
        #The extra data survives a restart while the light is off; the state attributes don't.
        if self.coordinator.data.color is not None:
            return
        color = None
        if (extra := await self.async_get_last_extra_data()) is not None:
            color = GoveeLightExtraStoredData.from_dict(extra.as_dict()).color
        if color is None and (last_state := await self.async_get_last_state()):
            rgb = last_state.attributes.get(ATTR_RGB_COLOR)
            color = tuple(rgb) if rgb else None
        if color is not None:
            await self.coordinator.restoreColor(color)

    @property
    def extra_restore_state_data(self) -> GoveeLightExtraStoredData:
        """Remember the colour and brightness even while the light is off."""
        return GoveeLightExtraStoredData(self.coordinator.data.color, self.coordinator.data.brightness)

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
            #HA brightness is 1-255; pass it through unchanged so the reported value matches what was set
            brightness = max(1, min(255, round(kwargs.get(ATTR_BRIGHTNESS, 255))))
            await self.coordinator.setBrightnessBuffered(brightness)

        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs.get(ATTR_RGB_COLOR)
            await self.coordinator.setColorBuffered(red, green, blue)
        else:
            #some models (e.g. H613C) only update their LEDs when a colour arrives: a bare power-on
            #stays dark and a brightness change is stored but not shown, so re-send the colour
            #(and, on a bare power-on, the brightness it had)
            if ATTR_BRIGHTNESS not in kwargs and self.coordinator.data.brightness:
                await self.coordinator.setBrightnessBuffered(self.coordinator.data.brightness)
            red, green, blue = self.coordinator.data.color or _DEFAULT_COLOR
            await self.coordinator.setColorBuffered(red, green, blue)
        
        await self.coordinator.sendPacketBuffer()

    
    async def async_turn_off(self, **kwargs):
        """Turn device off."""
        await self.coordinator.setStateBuffered(False)
        await self.coordinator.sendPacketBuffer()
