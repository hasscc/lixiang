"""Support for select."""
import logging

from homeassistant.components.select import (
    SelectEntity,
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


class XSelectEntity(BaseEntity, SelectEntity):
    _attr_current_option = None

    def __init__(self, name, device: BaseDevice, option=None):
        super().__init__(name, device, option)
        self._options = self._option.get('options') or {}
        self._attr_options = []
        if isinstance(self._options, dict):
            self._attr_options = [
                v.get('name', k) if isinstance(v, dict) else v
                for k, v in self._options.items()
            ]

    async def update_from_device(self):
        await super().update_from_device()
        opt = self._options.get(self._attr_state, self._attr_state)
        if isinstance(opt, dict):
            opt = opt.get('name')
        self._attr_current_option = opt

    async def async_select_option(self, option: str):
        """Change the selected option."""
        return await self.hass.async_add_executor_job(self.select_option, option)


class RemoteCtrlSelectEntity(XSelectEntity):

    async def async_select_option(self, option: str):
        """Change the selected option."""
        cmd = None
        dat = None
        if isinstance(self._options, dict):
            for k, v in self._options.items():
                opt = v if isinstance(v, dict) else {'name': v}
                if option == opt.get('name', k):
                    cmd = k
                    dat = opt.get('data')
                    break
        if not cmd:
            _LOGGER.warning('%s: Remote control failed: %s not in %s', self.name, option, self._options)
            return False
        return await self.device.remote_control(cmd, dat)
