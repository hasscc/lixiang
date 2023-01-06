"""Support for climate."""
import logging

from homeassistant.const import *
from homeassistant.components.climate import (
    ClimateEntity,
    HVACMode, HVACAction,
    ClimateEntityFeature,
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


class XClimateEntity(BaseEntity, ClimateEntity):
    _attr_hvac_mode = None
    _attr_hvac_modes = []


class CarAcEntity(XClimateEntity):
    _attr_max_temp = 32
    _attr_min_temp = 16
    _attr_temperature_unit = TEMP_CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_supported_features = 0

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
        self._attr_supported_features |= ClimateEntityFeature.FAN_MODE

    @property
    def ac_status(self):
        return self.device.ac_status

    def get_status(self, key=None, default=None):
        dat = self.ac_status
        return BaseDevice.to_number(dat.get(key, {}).get('value'), default) if key else dat

    async def update_from_device(self):
        await super().update_from_device()
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.AUTO,
            HVACMode.COOL,
            HVACMode.HEAT,
        ]
        if self.get_status('acAutoStatus'):
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_hvac_action = None
        elif self.get_status('acCoolReq'):
            self._attr_hvac_mode = HVACMode.COOL
            self._attr_hvac_action = HVACAction.COOLING
        elif self.get_status('acHeatReq'):
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_hvac_action = HVACAction.HEATING
        elif not self.device.ac_onoff:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_hvac_action = HVACAction.OFF

        self._attr_current_temperature = self.device.indoor_temperature
        self._attr_target_temperature = self.get_status('acFLTempStatus')
        self._attr_fan_mode = self.get_status('acWindSpeed')
        self._attr_fan_modes = list(range(1, 8))
        self._attr_extra_state_attributes = self.ac_status

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        return await self.device.ac_control(22, self._attr_target_temperature or '26.0')

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        return await self.device.ac_control(20, self._attr_target_temperature or '26.0')

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        ret = False
        if ATTR_TEMPERATURE in kwargs:
            num = kwargs[ATTR_TEMPERATURE]
            if ret := await self.device.ac_control(21, num):
                self._attr_target_temperature = num
        return ret

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.OFF:
            return await self.async_turn_off()
        if hvac_mode == HVACMode.AUTO:
            return await self.device.ac_control(22, self._attr_target_temperature or '26.0')
        if hvac_mode == HVACMode.COOL:
            return await self.device.ac_control(31, '16.0')
        if hvac_mode == HVACMode.HEAT:
            return await self.device.ac_control(29, '32.0')
        return False
