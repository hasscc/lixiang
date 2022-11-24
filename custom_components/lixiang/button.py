"""Support for button."""
import logging

from homeassistant.components.button import (
    ButtonEntity,
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
