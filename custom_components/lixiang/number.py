"""Support for number."""
import logging

from homeassistant.components.number import (
    NumberEntity,
    DOMAIN as ENTITY_DOMAIN,
)

from . import (
    DOMAIN,
    BaseDevice,
    BaseEntity,
    async_setup_device,
)

_LOGGER = logging.getLogger(__name__)

DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_device(hass, config_entry, ENTITY_DOMAIN, async_add_entities)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    await async_setup_device(hass, config, ENTITY_DOMAIN, async_add_entities)


class XNumberEntity(BaseEntity, NumberEntity):
    _attr_native_value = None

    def __init__(self, name, device: BaseDevice, option=None):
        super().__init__(name, device, option)
        self._attr_native_max_value = self._option.get('max')
        self._attr_native_min_value = self._option.get('min')
        self._attr_native_step = self._option.get('step', 1)

    async def update_from_device(self):
        await super().update_from_device()
        try:
            val = self._attr_state
        except (TypeError, ValueError):
            val = None
        self._attr_native_value = val or 0

    async def async_set_native_value(self, value: float):
        """Set new value."""
        return await self.hass.async_add_executor_job(self.set_native_value, value)
