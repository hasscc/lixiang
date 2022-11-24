"""Support for sensor."""
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,  # noqa
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


class XSensorEntity(BaseEntity, SensorEntity):
    _attr_native_value = None
    _attr_native_unit_of_measurement = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._attr_state_class = self._option.get('state_class')
        self._attr_native_unit_of_measurement = self._attr_unit_of_measurement

    async def update_from_device(self):
        await super().update_from_device()
        self._attr_native_value = self._attr_state
