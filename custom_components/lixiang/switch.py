"""Support for switch."""
import logging
import asyncio

from homeassistant.components.switch import (
    SwitchEntity,
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


class XSwitchEntity(BaseEntity, SwitchEntity):
    _attr_is_on = None

    async def update_from_device(self):
        await super().update_from_device()
        if self._attr_state is None:
            self._attr_is_on = None
        else:
            self._attr_is_on = not not self._attr_state

    async def async_turn_switch(self, on=True, **kwargs):
        """Turn the entity on/off."""
        ret = False
        fun = self._option.get('async_turn_on' if on else 'async_turn_off')
        if callable(fun):
            kwargs['entity'] = self
            ret = await fun(**kwargs)
        if ret:
            self._attr_is_on = not not on
            self.async_write_ha_state()
            await asyncio.sleep(1)
            self._handle_coordinator_update()
        return ret

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        return await self.async_turn_switch(True)

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        return await self.async_turn_switch(False)


class DoorLockEntity(XSwitchEntity):

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        return await self.device.remote_control('remote_central_lock_unlock')

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        return await self.device.remote_control('remote_central_lock_lock')
