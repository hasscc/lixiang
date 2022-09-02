import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import *

from . import get_car_from_config, init_integration_data
from .const import *

DEFAULT_NAME = 'LiXiang Auto'


def get_flow_schema(defaults: dict):
    return {
        vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
        vol.Required(CONF_API_KEY, default=defaults.get(CONF_API_KEY, '')): str,
        vol.Required(CONF_API_SIGN, default=defaults.get(CONF_API_SIGN, '')): str,
        vol.Required(CONF_API_TOKEN, default=defaults.get(CONF_API_TOKEN, '')): str,
        vol.Required(CONF_DEVICE_ID, default=defaults.get(CONF_DEVICE_ID, '')): str,
    }


class LiXiangConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(entry)

    async def async_step_user(self, user_input=None):
        init_integration_data(self.hass)
        errors = {}
        if user_input is None:
            user_input = {}
        if user_input.get(CONF_VIN):
            if car := get_car_from_config(self.hass, user_input):
                await car.update_status()
                if car.car_status and not car.car_status.get('code'):
                    await self.async_set_unique_id(f'{DOMAIN}-{car.vin}')
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input.get(CONF_NAME) or DEFAULT_NAME,
                        data=user_input,
                    )
                self.context['last_error'] = f'```{car.car_status}```'
            errors['base'] = 'cannot_access'
        return self.async_show_form(
            step_id='user',
            data_schema=vol.Schema({
                vol.Required(CONF_VIN, default=user_input.get(CONF_VIN, '')): str,
                **get_flow_schema(user_input),
            }),
            errors=errors,
            description_placeholders={'tip': self.context.pop('last_error', '')},
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        if user_input is None:
            user_input = {}
        if user_input.get(CONF_API_TOKEN):
            vin = self.config_entry.data.get(CONF_VIN)
            if car := get_car_from_config(self.hass, {**user_input, CONF_VIN: vin}):
                await car.update_status()
                if car.car_status and not car.car_status.get('code'):
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data={**self.config_entry.data, **user_input}
                    )
                    return self.async_create_entry(title='', data={})
                self.context['last_error'] = f'```{car.car_status}```'
            errors['base'] = 'cannot_access'
        user_input = {
            **self.config_entry.data,
            **self.config_entry.options,
            **user_input,
        }
        return self.async_show_form(
            step_id='init',
            data_schema=vol.Schema(get_flow_schema(user_input)),
            description_placeholders={'tip': self.context.pop('last_error', '')},
        )
