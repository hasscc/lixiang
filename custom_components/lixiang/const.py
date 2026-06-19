from homeassistant.const import (  # noqa
    CONF_NAME,
    CONF_API_KEY,
    CONF_API_TOKEN,
    CONF_DEVICE_ID,
    ATTR_TEMPERATURE,
)

DOMAIN = 'lixiang'

APP_VERSION = '8.22.0'

CONF_CARS = 'cars'
CONF_VIN = 'vin'
CONF_API = 'api'
CONF_HMAC_KEY = 'hmac_key'

SUPPORTED_DOMAINS = [
    'binary_sensor',
    'sensor',
    'switch',
    'select',
    'number',
    'button',
    'climate',
    'camera',
    'device_tracker',
]
