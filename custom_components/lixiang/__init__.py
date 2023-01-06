"""The component."""
import logging
import asyncio
import time
import json
import uuid
import base64
import hashlib
import datetime
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.const import *
from homeassistant.config import DATA_CUSTOMIZE
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.reload import (
    async_integration_yaml_config,
    async_reload_integration_platforms,
)
from homeassistant.components import persistent_notification
from homeassistant.util.dt import DEFAULT_TIME_ZONE
import homeassistant.helpers.config_validation as cv
from asyncio import TimeoutError
from aiohttp import ClientConnectorError, ClientResponseError

from .const import *

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = datetime.timedelta(seconds=60)

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VIN): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Required(CONF_API_SIGN): cv.string,
        vol.Required(CONF_API_TOKEN): cv.string,
        vol.Required(CONF_DEVICE_ID): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_CARS): vol.All(cv.ensure_list, [DEVICE_SCHEMA]),
            },
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, hass_config: dict):
    init_integration_data(hass)
    config = hass_config.get(DOMAIN) or {}
    await async_reload_integration_config(hass, config)

    component = EntityComponent(_LOGGER, DOMAIN, hass, SCAN_INTERVAL)
    hass.data[DOMAIN]['component'] = component
    await component.async_setup(config)

    car = None
    cls = config.get(CONF_CARS) or []
    for cfg in cls:
        if car := get_car_from_config(hass, cfg):
            await car.update_coordinator_first()

    for platform in (SUPPORTED_DOMAINS if car else []):
        hass.async_create_task(
            hass.helpers.discovery.async_load_platform(platform, DOMAIN, {}, config)
        )

    ComponentServices(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    init_integration_data(hass)
    if car := get_car_from_config(hass, config_entry):
        await car.update_coordinator_first()

    for platform in SUPPORTED_DOMAINS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, platform)
        )
    return True


def init_integration_data(hass):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(CONF_CARS, {})
    hass.data[DOMAIN].setdefault(CONF_ENTITIES, {})
    hass.data[DOMAIN].setdefault('add_entities', {})


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(config_entry, sd)
                for sd in SUPPORTED_DOMAINS
            ]
        )
    )
    return unload_ok


async def async_setup_device(hass: HomeAssistant, config, domain, add_entities=None):
    if car := get_car_from_config(hass, config):
        if eid := car.get_config('entry_id'):
            hass.data[DOMAIN]['add_entities'].setdefault(eid, {})
            hass.data[DOMAIN]['add_entities'][eid][domain] = add_entities
        else:
            hass.data[DOMAIN]['add_entities'][domain] = add_entities
        await car.update_hass_entities(domain)


def get_car_from_config(hass, config, renew=False):
    if isinstance(config, ConfigEntry):
        cfg = {
            **config.data,
            **config.options,
            'entry_id': config.entry_id,
            'config_entry': config,
        }
    else:
        cfg = config
    if not isinstance(cfg, dict):
        return None
    vin = cfg.get(CONF_VIN)
    if not vin:
        return None
    car = hass.data[DOMAIN][CONF_CARS].get(vin)
    if not car or renew:
        car = BaseDevice(hass, cfg)
        hass.data[DOMAIN][CONF_CARS][car.vin] = car
    return car


async def async_reload_integration_config(hass, config):
    hass.data[DOMAIN]['config'] = config
    return config


class ComponentServices:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass

        hass.helpers.service.async_register_admin_service(
            DOMAIN, SERVICE_RELOAD, self.handle_reload_config,
        )

        hass.services.async_register(
            DOMAIN, 'request_api', self.async_request_api,
            schema=vol.Schema({
                vol.Required(ATTR_ENTITY_ID): cv.string,
                vol.Required('api'): cv.string,
                vol.Optional('params', default={}): vol.Any(dict, None),
                vol.Optional('headers', default={}): vol.Any(dict, None),
                vol.Optional('throw', default=True): cv.boolean,
            }),
        )

    async def handle_reload_config(self, call):
        config = await async_integration_yaml_config(self.hass, DOMAIN)
        if not config or DOMAIN not in config:
            return
        await async_reload_integration_config(self.hass, config.get(DOMAIN) or {})
        current_entries = self.hass.config_entries.async_entries(DOMAIN)
        reload_tasks = [
            self.hass.config_entries.async_reload(entry.entry_id)
            for entry in current_entries
        ]
        await asyncio.gather(*reload_tasks)
        await async_reload_integration_platforms(self.hass, DOMAIN, SUPPORTED_DOMAINS)

    async def async_request_api(self, call):
        dat = call.data or {}
        eid = dat.get(ATTR_ENTITY_ID)
        car = None
        ent = self.hass.data[DOMAIN][CONF_ENTITIES].get(eid) if eid else None
        if ent and isinstance(ent, BaseEntity):
            car = ent.device
        api = dat['api']
        pms = dat.get('params') or {}
        hds = dat.get('headers') or {}
        if car:
            rdt = await car.async_request(api, pms, headers=hds)
        else:
            rdt = ['Not found car.']
        if dat.get('throw', True):
            persistent_notification.async_create(
                self.hass, f'{rdt}', 'Request LiXiang API result', f'{DOMAIN}-debug',
            )
        self.hass.bus.async_fire(f'{DOMAIN}.request_api', {
            'vin': car.vin if car else None,
            'api': api,
            'params': pms,
            'headers': hds,
            'result': rdt,
        })
        return rdt


class BaseDevice:
    data: dict

    def __init__(self, hass: HomeAssistant, config: dict):
        self.hass = hass
        self.config = config
        self.entities = {}
        self.listeners = {}
        self.car_info = {}
        self.car_status = {}
        self.car_mileage = {}
        self.tire_status = {}
        self.energy_cost = {}
        self.park_photos = {}
        self.http = aiohttp_client.async_create_clientsession(hass, auto_cleanup=False)

        self.coordinators = {
            'status': {
                'update_interval': self.update_interval,
                'update_method': self.update_all_status,
                'add_listeners': self._handle_listeners,
            },
            'hourly': {
                'update_interval': datetime.timedelta(hours=1),
                'update_method': self.update_energy_cost,
                'add_listeners': self._handle_listeners,
            },
        }
        for k, v in self.coordinators.items():
            kws = {**v}
            listener = kws.pop('add_listeners', None)
            coordinator = DataUpdateCoordinator(
                self.hass,
                _LOGGER,
                name=f'{DOMAIN}-{self.vin}-{k}',
                **kws,
            )
            if listener:
                coordinator.async_add_listener(listener)
            v['coordinator'] = coordinator  # noqa

    def _handle_listeners(self):
        for fun in self.listeners.values():
            fun()

    def get_adder(self, domain):
        als = self.hass.data[DOMAIN].get('add_entities') or {}
        if eid := self.get_config('entry_id'):
            als = als.get(eid) or als
        return als.get(domain)

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def get_info(self, key, default=None):
        return self.config.get('info', {}).get(key, default)

    @property
    def update_interval(self):
        return self.get_config(CONF_SCAN_INTERVAL, SCAN_INTERVAL)

    @property
    def vin(self):
        return self.config.get(CONF_VIN)

    @property
    def vin_sort(self):
        vin = f'{self.vin}'
        return f'{vin[:6]}_{vin[-6:]}'

    @property
    def name(self):
        return self.config.get(CONF_NAME) or self.get_info('plateNumber') or 'LiXiang'

    @property
    def model_desc(self):
        series = self.get_info('carSeries') or 'LiXiang'
        model = self.get_info('variableModel') or ''
        return f'{series} {model}'.strip()

    async def update_entities(self):
        for ent in self.entities.values():
            await ent.update_from_device()

    async def update_all_status(self):
        await self.update_status()
        await self.update_mileage()
        await self.update_tire_status()

        now = datetime.datetime.now(DEFAULT_TIME_ZONE)
        if now.minute % 5 == 0:
            await self.update_photos()

        await self.update_entities()

    async def update_coordinator_first(self):
        if not self.car_info:
            await self.update_vehicle_info()
        for v in self.coordinators.values():
            if coo := v.get('coordinator'):
                await coo.async_config_entry_first_refresh()
        await self.update_photos()

    async def update_vehicle_info(self, vin=None):
        if vin is None:
            vin = self.vin
        if not vin:
            return {}
        api = f'/aisp-account-api/v1-0/vehicles/{vin}'
        self.car_info = await self.async_request(api) or {}
        return self.car_info

    async def update_status(self):
        api = f'/ssp-as-mobile-api/v3-0/vehicles/{self.vin}/real-time-state'
        self.car_status = await self.async_request(api) or {}
        return self.car_status

    async def update_mileage(self):
        api = f'/ssp-as-mobile-api/v3-0/vehicles/energy-cost/total/{self.vin}'
        self.car_mileage = await self.async_request(api) or {}
        return self.car_mileage

    async def update_tire_status(self):
        api = f'/ssp-as-mobile-api/v1-0/vehicles/tire/alarm/{self.vin}'
        self.tire_status = await self.async_request(api) or {}
        return self.tire_status

    async def update_energy_cost(self):
        now = datetime.datetime.now(DEFAULT_TIME_ZONE)
        api = f'/ssp-as-mobile-api/v3-0/vehicles/energy-cost/monthly/{now.year}/{now.month}/{self.vin}'
        self.energy_cost = await self.async_request(api) or {}
        await self.update_entities()
        return self.energy_cost

    async def update_photos(self):
        api = f'/ssp-as-mobile-api/v1-0/vehicles/{self.vin}/parking-photos'
        pps = await self.async_request(api) or {}
        if pps.get('pictures'):
            self.park_photos = pps
        return pps

    async def take_photo(self, **kwargs):
        api = '/ssp-as-mobile-api/v1-0/vehicles/svm/take-photo'
        pms = {'vin': self.vin}
        rdt = await self.async_request(api, pms) or {}
        err = rdt.get('code') if isinstance(rdt, dict) else 0
        if err:
            _LOGGER.warning('%s: Take photo failed: %s', self.name, rdt)
        return rdt

    async def remote_search(self, **kwargs):
        return self.remote_control('remote_veh_search')

    async def ac_control(self, typ, temp):
        dat = {
            'Type': str(typ),
            'Temp': str(temp),
        }
        return await self.remote_control('remote_ac_ctrl_new', dat)

    async def remote_control(self, cmd, data=None, **kwargs):
        api = '/ssp-as-mobile-api/v3-0/remote-vehicle-control/send-command'
        pms = {
            'vin': self.vin,
            'commandKey': cmd,
        }
        if data:
            pms['commandData'] = data
        rdt = await self.async_request(api, pms) or {}
        if ret := rdt.get('code'):
            _LOGGER.warning('%s: Remote control failed: %s', self.name, [pms, rdt])
        return ret

    @property
    def status(self):
        vos = self.car_status.get('vehOnlineStatus') or {}
        sta = vos.get('deviceStatus') or vos.get('status', '')
        return f'{sta}'.lower()

    def status_attrs(self):
        adt = self.car_status.get('vehOnlineStatus') or {}
        kls = [
            'vehicleNickname',
            'plateNumber',
            'seriesNo',
            'materialNumber',
            'carModel',
            'color',
            'interiorName',
            'wheelName',
            'deviceId',
            'electricPedal',
        ]
        for k in kls:
            adt[k] = self.car_info.get(k, None)
        kls = [
            'vehPowerMode',
            'remoteStartStatus',
            'caseCoverStatus',
            'keyInCarWarning',
            'forgetCloseDoorWarning',
            'vehRealtimeAlarm',
            'vehRealtimeMaint',
            'otaUpgradeInfo',
        ]
        for k in kls:
            adt[k] = self.car_status.get(k, {})
        return adt

    @property
    def charge(self):
        sta = self.to_number(self.charge_attrs().get('chargeStatus'))
        dic = {
            10: 'disconnected',
            11: 'connected',
            50: 'charging',
            70: 'full',
        }
        return dic.get(sta, sta)

    def charge_setting(self):
        return self.car_status.get('chargeSetting') or {}

    def charge_attrs(self):
        adt = {
            k: self.to_number(v)
            for k, v in (self.charge_setting().get('chargeStatus') or {}).items()
        }
        return {
            **adt,
            'chargingFaults': self.charge_setting().get('chargingFaults') or [],
            'chargingTarget': self.charge_setting().get('chargingTarget') or {},
            'batteryWarmSwitch': self.charge_setting().get('batteryWarmSwitch') or {},
        }

    @property
    def endurance(self):
        endurance_status = self.endurance_attrs()
        battEndurance = self.to_number(endurance_status.get('batteryEndurance'))
        fuelEndurance = self.to_number(endurance_status.get('fuelEndurance'))
        if battEndurance is None or fuelEndurance is None:
            return None
        return battEndurance + fuelEndurance

    def endurance_attrs(self):
        return self.charge_setting().get('enduranceStatus') or {}

    @property
    def battery(self):
        return self.to_number(self.endurance_attrs().get('residueBattery'))

    @property
    def fuel_level(self):
        return self.to_number(self.endurance_attrs().get('residueFuel'))

    @property
    def door_opened(self):
        cnt = 0
        for v in self.doors_attrs().values():
            if int(v.get('isOpen', 0)):
                cnt += 1
        return cnt

    def door_opened_attrs(self):
        adt = {}
        for k, v in self.doors_attrs().items():
            adt[k] = {
                'isOpen': v.get('isOpen'),
                'actionTime': v.get('actionTime'),
            }
        return adt

    @property
    def door_lock(self):
        return self.door_unlocked > 0

    @property
    def door_unlocked(self):
        cnt = 0
        for v in self.doors_attrs().values():
            if not int(v.get('isLock', 0)):
                cnt += 1
        return cnt

    def door_unlocked_attrs(self):
        adt = {}
        for k, v in self.doors_attrs().items():
            adt[k] = {
                'isLock': v.get('isLock'),
                'lockTime': v.get('lockTime'),
            }
        return adt

    def doors_attrs(self):
        return self.car_status.get('doorSwitchStatus') or {}

    @property
    def window_opened(self):
        cnt = 0
        for v in self.windows_attrs().values():
            if int(v.get('openStatus', 0)):
                cnt += 1
        return cnt

    def windows_attrs(self):
        return self.car_status.get('windowSwitchStatus') or {}

    @property
    def indoor_temperature(self):
        return self.to_number(self.temperature_attrs().get('indoorTemperature'))

    @property
    def outdoor_temperature(self):
        return self.to_number(self.temperature_attrs().get('outdoorTemperature'))

    @property
    def pm25(self):
        return self.to_number(self.temperature_attrs().get('airPollutionIndex'))

    def temperature_attrs(self):
        return self.car_status.get('temperatureStatus') or {}

    @property
    def ac_status(self):
        return self.car_status.get('airConditioningStatus') or {}

    @property
    def ac_onoff(self):
        return self.to_number(self.ac_status.get('acOffStatus', {}).get('value'), 0)

    @property
    def wheel_warm(self):
        return self.to_number(self.wheel_warm_attrs.get('warmOnOff'), 0)

    @property
    def wheel_warm_attrs(self):
        return self.car_status.get('wheelWarmStatus') or {}

    @property
    def location_status(self):
        return self.car_status.get('locationStatus') or {}

    def location_attrs(self):
        tim = self.to_number(self.location_status.get('ct'))
        if tim:
            tim = datetime.datetime.fromtimestamp(tim / 1000).replace(tzinfo=DEFAULT_TIME_ZONE)
        else:
            tim = None
        return {
            'direction': self.location_status.get('dir'),
            'altitude':  self.location_status.get('alt'),
            'timestamp': tim,
        }

    @property
    def gear(self):
        return self.car_status.get('travelStatus', {}).get('gear')

    @property
    def tire_alarm(self):
        return self.to_number(self.tire_status.get('alarmCount', 0))

    def tire_alarm_attrs(self):
        tad = {**self.tire_status}
        tad.update(tad.pop('tireAlarmState', None) or {})
        return tad

    @property
    def mileage(self):
        return self.to_number(self.mileage_attrs().get('totalMileage'))

    def mileage_attrs(self):
        return self.car_mileage or {}

    def parking_photos(self):
        tim = self.to_number(self.park_photos.get('picTimestamp'))
        if tim:
            tim = datetime.datetime.fromtimestamp(tim / 1000).replace(tzinfo=DEFAULT_TIME_ZONE)
        return {
            **(self.park_photos or {}),
            'timestamp':  tim,
        }

    @property
    def monthly_elec(self):
        return self.to_number(self.energy_cost.get('elecEnergy'))

    def monthly_elec_attrs(self):
        return {
            'travelMileage': self.energy_cost.get('travelMileage'),
            'elecMileage': self.energy_cost.get('elecMileage'),
            'elecEnergy': self.energy_cost.get('elecEnergy'),
            'avgElecEnergy': self.energy_cost.get('avgElecEnergy'),
            'dailyList': self.energy_cost.get('dailyList', []),
        }

    @property
    def monthly_fuel(self):
        return self.to_number(self.energy_cost.get('fuelConsumption'))

    def monthly_fuel_attrs(self):
        return {
            'travelMileage': self.energy_cost.get('travelMileage'),
            'hybridMileage': self.energy_cost.get('hybridMileage'),
            'fuelConsumption': self.energy_cost.get('fuelConsumption'),
            'avgFuelConsumption': self.energy_cost.get('avgFuelConsumption'),
            'dailyList': self.energy_cost.get('dailyList', []),
        }

    @staticmethod
    def to_number(num, default=None):
        if num in [None, -2147483648, '-2147483648']:
            return default
        try:
            num = float(num)
        except (TypeError, ValueError):
            num = default
        return num

    @property
    def hass_sensor(self):
        from .sensor import SensorStateClass
        dat = {
            'status': {
                'icon': 'mdi:car',
                'attrs': self.status_attrs,
                'picture': self.get_info('mainPictureUrl') or None,
            },
            'mileage': {
                'icon': 'mdi:gauge',
                'unit': LENGTH_KILOMETERS,
                'attrs': self.mileage_attrs,
                'state_class': SensorStateClass.TOTAL,
            },
            'endurance': {
                'icon': 'mdi:speedometer',
                'unit': LENGTH_KILOMETERS,
                'attrs': self.endurance_attrs,
                'state_class': SensorStateClass.MEASUREMENT,
            },
            'charge': {
                'icon': 'mdi:ev-station',
                'attrs': self.charge_attrs,
            },
            'battery': {
                'class': DEVICE_CLASS_BATTERY,
                'unit': PERCENTAGE,
                'state_class': SensorStateClass.MEASUREMENT,
            },
            'fuel_level': {
                'unit': PERCENTAGE,
                'state_class': SensorStateClass.MEASUREMENT,
            },
            'door_opened': {
                'icon': 'mdi:car-door',
                'attrs': self.door_opened_attrs,
            },
            'door_unlocked': {
                'icon': 'mdi:car-door-lock',
                'attrs': self.door_unlocked_attrs,
            },
            'window_opened': {
                'icon': 'mdi:dock-window',
                'attrs': self.windows_attrs,
            },
            'indoor_temperature': {
                'class': DEVICE_CLASS_TEMPERATURE,
                'unit': TEMP_CELSIUS,
                'state_class': SensorStateClass.MEASUREMENT,
            },
            'outdoor_temperature': {
                'class': DEVICE_CLASS_TEMPERATURE,
                'unit': TEMP_CELSIUS,
                'state_class': SensorStateClass.MEASUREMENT,
            },
            'pm25': {
                'class': DEVICE_CLASS_PM25,
                'unit': CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
                'state_class': SensorStateClass.MEASUREMENT,
            },
            'gear': {
                'icon': 'mdi:cog',
            },
            'tire_alarm': {
                'icon': 'mdi:tire',
                'attrs': self.tire_alarm_attrs,
            },
            'monthly_elec': {
                'class': DEVICE_CLASS_ENERGY,
                'unit': ENERGY_KILO_WATT_HOUR,
                'icon': 'mdi:car-electric',
                'attrs': self.monthly_elec_attrs,
                'state_class': SensorStateClass.TOTAL_INCREASING,
            },
            'monthly_fuel': {
                'unit': VOLUME_LITERS,
                'icon': 'mdi:gas-station',
                'attrs': self.monthly_fuel_attrs,
                'state_class': SensorStateClass.TOTAL_INCREASING,
            },
        }
        return dat

    @property
    def hass_device_tracker(self):
        from .device_tracker import CarTrackerEntity
        return {
            'location': {
                'attrs': self.location_attrs,
                'entity': CarTrackerEntity,
            },
        }

    @property
    def hass_switch(self):
        from .switch import RemoteControlSwitchEntity, AcCtrlSwitchEntity
        return {
            'door_lock': {
                'icon': 'mdi:lock',
                'attrs': self.door_unlocked_attrs,
                'entity': RemoteControlSwitchEntity,
                'on_cmd': 'remote_central_lock_unlock',
                'off_cmd': 'remote_central_lock_lock',
            },
            'wheel_warm': {
                'icon': 'mdi:steering',
                'attrs': self.wheel_warm_attrs,
                'entity': AcCtrlSwitchEntity,
                'off_type': 1,
                'on_type': 2,
            },
        }

    @property
    def hass_button(self):
        return {
            'find': {
                'icon': 'mdi:car-search',
                'async_press': self.remote_search,
            },
            'take_photo': {
                'icon': 'mdi:camera',
                'async_press': self.take_photo,
            },
        }

    @property
    def hass_climate(self):
        from .climate import CarAcEntity
        return {
            'ac': {
                'entity': CarAcEntity,
            },
        }

    @property
    def hass_camera(self):
        from .camera import CarCameraEntity
        return {
            'photos': {
                'attrs': self.parking_photos,
                'entity': CarCameraEntity,
            },
        }

    async def update_hass_entities(self, domain):
        from .binary_sensor import XBinarySensorEntity
        from .button import XButtonEntity
        from .sensor import XSensorEntity
        from .switch import XSwitchEntity
        from .select import XSelectEntity
        from .number import XNumberEntity
        hdk = f'hass_{domain}'
        add = self.get_adder(domain)
        if not add or not hasattr(self, hdk):
            return
        for k, cfg in getattr(self, hdk).items():
            new = None
            cls = cfg.get('entity')
            key = f'{domain}.{k}.{self.vin}'
            if key in self.entities:
                pass
            elif isinstance(cls, type):
                new = cls(k, self, cfg)
            elif domain == 'binary_sensor':
                new = XBinarySensorEntity(k, self, cfg)
            elif domain == 'button':
                new = XButtonEntity(k, self, cfg)
            elif domain == 'sensor':
                new = XSensorEntity(k, self, cfg)
            elif domain == 'switch':
                new = XSwitchEntity(k, self, cfg)
            elif domain == 'select':
                new = XSelectEntity(k, self, cfg)
            elif domain == 'number':
                new = XNumberEntity(k, self, cfg)
            if new:
                self.entities[key] = new
                add([new])

    def api_url(self, api=''):
        if api[:6] == 'https:' or api[:5] == 'http:':
            return api
        bas = 'https://api-app.lixiang.com'
        return f"{bas.rstrip('/')}/{api.lstrip('/')}"

    async def async_request(self, api, pms=None, **kwargs):
        uri = self.api_url(api)
        jso = json.dumps(pms, separators=(',', ':')) if pms else ''
        how = kwargs.get('method', 'POST' if pms else 'GET')
        hds = {
            'Content-Type': 'application/json',
            'Content-Language': 'zh-CN',
            'Content-MD5': base64.b64encode(hashlib.md5(jso.encode()).digest()).decode(),
            'User-Agent': 'M01/5.11.0 (Android; 6.0.1)',
            'x-chj-deviceid': self.get_config(CONF_DEVICE_ID, ''),
            'x-chj-app-version': '5.11.0',
            'x-chj-env': 'prod',
            'x-chj-version': '0.1-20160523142212',
            'x-chj-key': self.get_config(CONF_API_KEY, ''),
            'x-chj-timestamp': str(int(time.time() * 1000)),
            'x-chj-nonce': str(uuid.uuid4()),
            'x-chj-sign': self.get_config(CONF_API_SIGN, ''),
            'x-chj-token': self.get_config(CONF_API_TOKEN, ''),
            'x-chj-devicetype': '2',
            'x-chj-modelname': 'ANDROID',
            'x-chj-devicemodel': 'XiaoMi',
            'x-chj-vin': self.vin,
            'x-chj-traceid': str(uuid.uuid4()),
            'x-chj-metadata': '{"language":"zh","code":"102004"}',
        }
        rsp = None
        try:
            rsp = await self.http.request(how, uri, data=jso, headers=hds)
            dat = await rsp.json() or {}
        except ClientResponseError as exc:
            dat = {}
            if rsp:
                txt = await rsp.text()
                _LOGGER.error('Request api failed: %s', [api, pms, kwargs, exc, txt])
        except (ClientConnectorError, TimeoutError) as exc:
            dat = {}
            _LOGGER.error('Request api failed: %s', [api, pms, kwargs, exc])
        if not dat or dat.get('code'):
            _LOGGER.warning('Request api: %s', [api, pms, kwargs, dat])
        return dat.get('data') or dat


class BaseEntity(Entity):
    _attr_should_poll = False

    def __init__(self, name, device: BaseDevice, option=None):
        self.device = device
        self.hass = device.hass
        self._option = option or {}
        self._name = name
        self._byte = self._option.get('byte')
        self._attr_name = f'{device.name} {name}'.strip()
        self._attr_device_id = f'{device.vin}'
        self._attr_unique_id = f'{self._attr_device_id}-{name}'
        self.entity_id = f'{DOMAIN}.{device.vin_sort}_{name}'
        self._attr_icon = self._option.get('icon')
        self._attr_entity_picture = self._option.get('picture')
        self._attr_device_class = self._option.get('class')
        self._attr_unit_of_measurement = self._option.get('unit')
        ota = device.car_status.get('otaUpgradeInfo') or {}
        self._attr_device_info = {
            'identifiers': {(DOMAIN, self._attr_device_id)},
            'name': device.name,
            'model': device.model_desc,
            'sw_version': ota.get('baseVersion'),
            'manufacturer': device.get_info('brandNo') or device.get_info('brand') or 'LiXiang',
        }
        self._attr_extra_state_attributes = {}
        self._vars = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await self.update_from_device()
        self.hass.data[DOMAIN][CONF_ENTITIES][self.entity_id] = self
        self.device.listeners[self.entity_id] = self._handle_coordinator_update
        self._handle_coordinator_update()

    def _handle_coordinator_update(self):
        self.async_write_ha_state()

    async def async_update(self):
        await self.device.update_all_status()

    async def update_from_device(self):
        if hasattr(self.device, self._name):
            self._attr_state = getattr(self.device, self._name)

        fun = self._option.get('attrs')
        if callable(fun):
            self._attr_extra_state_attributes = fun()

    def get_customize(self, key=None, default=None):
        cus = self.hass.data[DATA_CUSTOMIZE].get(self.entity_id) or {}
        return cus.get(key, default) if key else cus
