"""Support for camera."""
import logging
import datetime
import collections
import io
from PIL import Image, ImageDraw, ImageFont

from homeassistant.core import callback
from homeassistant.components.camera import (
    Camera as CameraEntity,
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


class CarCameraEntity(BaseEntity, CameraEntity):
    _latest_url = None
    _latest_img = None

    def __init__(self, name, device: BaseDevice, option=None):
        super().__init__(name, device, option)
        CameraEntity.__init__(self)
        self.access_tokens = collections.deque(self.access_tokens, 12 * 2)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._vars['location_update_unsub'] = self.hass.bus.async_listen(
            f'{DOMAIN}.location_updated',
            self.async_update_event_handler,
        )

    async def async_will_remove_from_hass(self):
        """Run when entity will be removed from hass.
        To be extended by integrations.
        """
        await super().async_will_remove_from_hass()
        if unsub := self._vars.pop('location_update_unsub', None):
            unsub()

    async def async_update_event_handler(self, event):
        if self.device.vin != event.data.get('vin'):
            return
        if self.device.gear != 'P':
            return
        if self.device.ac_onoff:
            return
        await self.async_update()

    async def async_update(self):
        await self.device.update_photos()
        await self.device.update_entities()

    @callback
    def async_update_token(self):
        """Update the used token."""
        super().async_update_token()

        if tok := self.get_customize('camera_token'):
            if tok not in self.access_tokens:
                self.access_tokens.appendleft(tok)

    async def async_merge_image(self):
        pls = self.device.park_photos.get('pictures') or []
        if not pls:
            return None
        url = pls[0]['photoUrl']
        if url == self._latest_url and self._latest_img:
            return self._latest_img
        width = 1380
        height = 720
        target = None
        idx = 0
        pos = [(0, 0), (1, 0), (1, 1), (0, 1)]
        for p in pls:
            url = p.get('photoUrl')
            if not url:
                continue
            res = await self.device.http.get(url)
            img = Image.open(io.BytesIO(await res.read()))
            if not target:
                width = img.width
                height = img.height
                target = Image.new('RGB', (width * 2, height * 2))
            tar = pos[idx]
            target.paste(img, (width * tar[0], height * tar[1]))
            idx += 1
            if idx >= len(pos):
                break
        if target:
            draw = ImageDraw.Draw(target)
            font = ImageFont.load_default()
            tim = self.device.parking_photos().get('timestamp')
            if not isinstance(tim, datetime.date):
                tim = datetime.datetime.now()
            draw.text((10, 10), str(tim.strftime('%Y-%m-%d %H:%M:%S')),
                      (255, 255, 255), font=font)
            self._latest_url = url
            self._latest_img = target
        return self._latest_img

    async def async_camera_image(self, width=None, height=None):
        """Return bytes of camera image."""
        img = await self.async_merge_image()
        if not img:
            return None
        img = img.copy()
        if width and height:
            img.resize((width, height))
        buf = io.BytesIO()
        img.save(buf, 'JPEG', optimize=True, quality=50)
        return buf.getvalue()
