"""Support for button."""
import logging

from homeassistant.core import HomeAssistant
from homeassistant.components.button import (
    ButtonEntity,
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


class XButtonEntity(BaseEntity, ButtonEntity):
    def __init__(self, name, device: BaseDevice, option=None):
        super().__init__(name, device, option)

    async def async_press(self):
        """Press the button."""
        ret = False
        fun = self._option.get('async_press')
        if callable(fun):
            kws = {
                'entity': self,
            }
            ret = await fun(**kws)
        return ret
