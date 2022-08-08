"""Support for number."""
import logging

from homeassistant.core import HomeAssistant
from homeassistant.components.number import (
    NumberEntity,
    DOMAIN as ENTITY_DOMAIN,
)

from . import (
    DOMAIN,
    BaseDevice,
    BaseEntity,
    async_setup_devices,
)

_LOGGER = logging.getLogger(__name__)

DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'


async def async_setup_entry(hass, config_entry, async_add_entities):
    cfg = {**config_entry.data, **config_entry.options}
    await async_setup_platform(hass, cfg, async_add_entities)


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    await async_setup_devices(hass, ENTITY_DOMAIN, async_add_entities)


class XNumberEntity(BaseEntity, NumberEntity):
    _attr_value = None
    _attr_native_value = None
    _attr_max_value = None
    _attr_min_value = None
    _attr_step = None

    def __init__(self, name, device: BaseDevice, option=None):
        super().__init__(name, device, option)
        self._attr_max_value = self._option.get('max')
        self._attr_min_value = self._option.get('min')
        self._attr_step = self._option.get('step', 1)
        self._attr_native_max_value = self._attr_max_value
        self._attr_native_min_value = self._attr_min_value
        self._attr_native_step = self._attr_step

    async def update_from_device(self):
        await super().update_from_device()
        try:
            self._attr_value = self._attr_state
        except (TypeError, ValueError):
            self._attr_value = None
        self._attr_native_value = self._attr_value or 0

    async def async_set_value(self, value: float):
        """Set new value."""
        return await self.async_set_native_value(value)

    async def async_set_native_value(self, value: float):
        """Set new value."""
        return await self.async_set_property(value)
