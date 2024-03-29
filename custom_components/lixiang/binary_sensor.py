"""Support for binary_sensor."""
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    DOMAIN as ENTITY_DOMAIN,
)

from . import (
    DOMAIN,
    BaseEntity,
    async_setup_device,
)

_LOGGER = logging.getLogger(__name__)

DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_device(hass, config_entry, ENTITY_DOMAIN, async_add_entities)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    await async_setup_device(hass, config, ENTITY_DOMAIN, async_add_entities)


class XBinarySensorEntity(BaseEntity, BinarySensorEntity):
    _attr_is_on = None

    async def update_from_device(self):
        await super().update_from_device()
        if self._attr_state is None:
            self._attr_is_on = None
        else:
            self._attr_is_on = not not self._attr_state
