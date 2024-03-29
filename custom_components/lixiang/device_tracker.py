"""Support for device tracker."""
import logging
import json
from math import sin, asin, cos, radians, fabs, sqrt

from homeassistant.components.device_tracker.config_entry import (
    TrackerEntity,
    DOMAIN as ENTITY_DOMAIN,
)
from homeassistant.util import dt
from aiohttp.client_exceptions import ClientConnectorError

from . import (
    DOMAIN,
    BaseEntity,
    async_setup_device,
)

_LOGGER = logging.getLogger(__name__)

DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
EARTH_RADIUS = 6371
KNOTS_TO_KPH_RATIO = 0.539957


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_device(hass, config_entry, ENTITY_DOMAIN, async_add_entities)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    await async_setup_device(hass, config, ENTITY_DOMAIN, async_add_entities)


class CarTrackerEntity(BaseEntity, TrackerEntity):
    _prev_updated = None
    _prev_location = None

    async def update_from_device(self):
        pre = self._prev_updated
        if state := self.hass.states.get(self.entity_id):
            if pre := state.attributes.get('timestamp'):
                pre = dt.as_timestamp(pre)

        await super().update_from_device()

        tim = self.updated_at
        if tim and pre and tim > pre:
            if spd := self.get_speed():
                self._attr_extra_state_attributes['speed'] = spd

            await self.update_to_traccar()
            await self.update_to_baidu_yingyan()

            self._prev_updated = tim
            self._prev_location = (self.latitude, self.longitude)
            self.hass.bus.fire(f'{DOMAIN}.location_updated', {'vin': self.device.vin})

    @property
    def battery_level(self):
        """Return the battery level of the device.
        Percentage from 0-100.
        """
        if self.device.battery is None:
            return None
        return int(self.device.battery)

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the device."""
        return 'gps'

    @property
    def location_status(self):
        return self.device.location_status

    @property
    def updated_at(self):
        return self.device.to_number(self.location_status.get('ct'), 0) / 1000

    @property
    def latitude(self):
        """Return latitude value of the device."""
        val = self.location_status.get('lat')
        return float(val) if val else None

    @property
    def longitude(self):
        """Return longitude value of the device."""
        val = self.location_status.get('lon')
        return float(val) if val else None

    def get_speed(self):
        if self._prev_location and self._prev_updated:
            dur = self.updated_at - self._prev_updated
            if dur >= 2:
                dis = get_distance_hav(
                    self._prev_location[0], self._prev_location[1],
                    self.latitude, self.longitude,
                )
                spd = round(dis / (dur / 3600), 2)
                return spd
        return None

    async def update_to_traccar(self):
        host = self.get_customize('traccar_host')
        did = self.get_customize('traccar_did') or self.device.vin
        if not host or not did:
            return None
        # https://github.com/traccar/traccar/blob/master/src/main/java/org/traccar/protocol/OsmAndProtocolDecoder.java
        # https://github.com/traccar/traccar/blob/master/src/main/java/org/traccar/model/Position.java
        # http://demo.traccar.org:5055?id=123456&lat={0}&lon={1}&timestamp={2}&hdop={3}&altitude={4}&speed={5}
        pms = {
            'id': did,
            'timestamp': int(self.updated_at * 1000),
            'lat': self.latitude,
            'lon': self.longitude,
            'altitude': self.location_status.get('alt'),
            'heading': self.location_status.get('dir'),
            'speed': self._attr_extra_state_attributes.get('speed', 0) * KNOTS_TO_KPH_RATIO,  # km/h -> knots
            'batt': self.battery_level,
            'fuel': self.device.to_number(self.device.endurance_attrs().get('residueFuel')),
            'deviceTemp': self.device.indoor_temperature,
        }
        dis = self.device.to_number(self.device.mileage_attrs().get('totalMileage'))
        if dis is not None:
            pms['totalDistance'] = int(dis * 1000)
        pms = {
            k: v
            for k, v in pms.items()
            if v is not None
        }
        url = host if '://' in host else f'http://{host}'
        try:
            await self.device.http.get(url, params=pms)
        except (ClientConnectorError, Exception) as exc:
            _LOGGER.warning('Update to traccar: %s', [pms, exc])

    async def update_to_baidu_yingyan(self):
        key = self.get_customize('baidu_yingyan_key')
        sid = self.get_customize('baidu_yingyan_sid')
        if not key or not sid:
            return None
        pms = {
            'ak': key,
            'service_id': sid,
            'entity_name': self.device.vin,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'loc_time': int(self.updated_at),
            'height': self.location_status.get('alt'),
            'direction': int(self.location_status.get('dir', 0)),
            'speed': self._attr_extra_state_attributes.get('speed', 0),
            'coord_type_input': 'wgs84',
        }
        url = 'https://yingyan.baidu.com/api/v3/track/addpoint'
        jss = None
        try:
            res = await self.device.http.post(url, data=pms)
            jss = await res.text()
            rdt = json.loads(jss) or {}
            if not rdt or rdt.get('status'):
                _LOGGER.warning('Update to baidu yingyan: %s', [pms, jss])
        except (ClientConnectorError, Exception) as exc:
            _LOGGER.warning('Update to baidu yingyan: %s', [pms, jss, exc])


def hav(theta):
    s = sin(theta / 2)
    return s * s


def get_distance_hav(lat0, lng0, lat1, lng1):
    lat0 = radians(lat0)
    lat1 = radians(lat1)
    lng0 = radians(lng0)
    lng1 = radians(lng1)
    dlng = fabs(lng0 - lng1)
    dlat = fabs(lat0 - lat1)
    h = hav(dlat) + cos(lat0) * cos(lat1) * hav(dlng)
    distance = 2 * EARTH_RADIUS * asin(sqrt(h))  # km
    return distance
