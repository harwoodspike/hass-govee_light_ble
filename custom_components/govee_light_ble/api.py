import asyncio
import bleak_retry_connector
from bleak_retry_connector import BleakOutOfConnectionSlotsError
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak import (
    BleakClient,
    BLEDevice
)
from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant
from homeassistant.components import bluetooth
from .const import WRITE_CHARACTERISTIC_UUID, READ_CHARACTERISTIC_UUID
from .api_utils import (
    LedPacketHead,
    LedPacketCmd,
    LedColorType,
    LedPacket,
    GoveeUtils
)

import logging
_LOGGER = logging.getLogger(__name__)

_SLOT_ERROR_THRESHOLD = 2
_SLOT_BACKOFF_DURATION = timedelta(minutes=5)
_MAX_CONNECTION_AGE = timedelta(hours=1)
# Some models (e.g. H613C fw 1.07.04) drop the first write after notifications are enabled,
# and back-to-back write-without-response frames get dropped too, so pace the link.
_POST_CONNECT_SETTLE = 0.3
_INTER_PACKET_DELAY = 0.05

class GoveeAPI:
    state: bool | None = None
    brightness: int | None = None
    color: tuple[int, ...] | None = None

    def __init__(self, hass: HomeAssistant, ble_device: BLEDevice, update_callback, segmented: bool = False):
        self._conn = None
        self._hass = hass
        self._ble_device = ble_device
        self._segmented = segmented
        self._packet_buffer = []
        # values from buffered commands, applied once the buffer is actually transmitted
        self._pending: dict[str, object] = {}
        self._client = None
        self._connected_at: datetime | None = None
        self._update_callback = update_callback
        self._slot_error_count = 0
        self._slot_backoff_until: datetime | None = None
        self._lock = asyncio.Lock()

    @property
    def address(self):
        return self._ble_device.address

    def update_ble_device(self, ble_device: BLEDevice) -> None:
        self._ble_device = ble_device

    async def _ensureConnected(self):
        """ connects to a bluetooth device """
        if self._client is not None and self._client.is_connected:
            age = datetime.now() - self._connected_at if self._connected_at else None
            if age is None or age > _MAX_CONNECTION_AGE:
                _LOGGER.debug("Forcing reconnect to %s — connection age %s", self.address, age)
                try:
                    await self._client.disconnect()
                except Exception:
                    pass
                self._client = None
                self._connected_at = None
            else:
                return None
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None
        await self._connect()

    async def _connect(self):
        def _disconnected(client: BleakClient) -> None:
            if self._client is client:
                self._client = None
                self._connected_at = None

        connectable_device = bluetooth.async_ble_device_from_address(
            self._hass, self.address, connectable=True
        ) or self._ble_device

        self._client = await bleak_retry_connector.establish_connection(
            BleakClient,
            connectable_device,
            self.address,
            disconnected_callback=_disconnected
        )
        try:
            await self._client.start_notify(READ_CHARACTERISTIC_UUID, self._handleReceive)
        except Exception:
            client = self._client
            self._client = None
            try:
                await client.disconnect()
            except Exception:
                pass
            raise
        self._connected_at = datetime.now()
        await asyncio.sleep(_POST_CONNECT_SETTLE)

    async def _transmitPacket(self, packet: LedPacket):
        """ transmit the actiual packet """
        #convert to bytes
        frame = await GoveeUtils.generateFrame(packet)
        #transmit to UUID
        await self._client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, frame, False)

    async def _handleRequest(self, packet: LedPacket):
        """ process received responses """
        match packet.cmd:
            case LedPacketCmd.POWER:
                self.state = packet.payload[0] == 0x01
            case LedPacketCmd.BRIGHTNESS:
                #segmented devices 0-100
                self.brightness = round(packet.payload[0] / 100 * 255) if self._segmented else packet.payload[0]
            case LedPacketCmd.COLOR:
                mode = packet.payload[0]
                red = packet.payload[1]
                green = packet.payload[2]
                blue = packet.payload[3]
                if mode == LedColorType.LEGACY and not (red or green or blue):
                    #LEGACY replies carry no colour on some models (e.g. H613C): keep the last commanded one
                    return
                self.color = (red, green, blue)
            case LedPacketCmd.SEGMENT:
                red = packet.payload[2]
                green = packet.payload[3]
                blue = packet.payload[4]
                self.color = (red, green, blue)

    async def _handleReceive(self, characteristic: BleakGATTCharacteristic, frame: bytearray):
        """ receives packets async """
        if not await GoveeUtils.verifyChecksum(frame):
            _LOGGER.warning("Received packet with bad checksum, ignoring")
            return
        
        packet = LedPacket(
            head=frame[0],
            cmd=frame[1],
            payload=frame[2:-1]
        )
        _LOGGER.debug("Received from %s: %s", self.address, bytes(frame).hex(" "))
        #only requests are expected to send a response
        if packet.head == LedPacketHead.REQUEST:
            await self._handleRequest(packet)
            await self._update_callback()

    async def _preparePacket(self, cmd: LedPacketCmd, payload: bytes | list = b'', request: bool = False, repeat: int = 3):
        """ add data to transmission buffer """
        #request data or perform a change
        head = LedPacketHead.REQUEST if request else LedPacketHead.COMMAND
        packet = LedPacket(head, cmd, payload)
        for _ in range(repeat):
            self._packet_buffer.append(packet)

    async def sendPacketBuffer(self):
        """ transmits all buffered data """
        async with self._lock:
            _LOGGER.debug("sendPacketBuffer called for %s with %d packets", self.address, len(self._packet_buffer))
            if not self._packet_buffer:
                return None
            if self._slot_backoff_until is not None:
                now = datetime.now()
                if now < self._slot_backoff_until:
                    remaining = int((self._slot_backoff_until - now).total_seconds())
                    _LOGGER.debug("Proxy slot backoff active, skipping for %ds more", remaining)
                    self._packet_buffer = []
                    self._pending = {}
                    return None
                self._slot_backoff_until = None
            packets, self._packet_buffer = self._packet_buffer, []
            pending, self._pending = self._pending, {}
            try:
                await self._ensureConnected()
                for packet in packets:
                    await self._transmitPacket(packet)
                    await asyncio.sleep(_INTER_PACKET_DELAY)
                self._slot_error_count = 0
            except BleakOutOfConnectionSlotsError:
                self._slot_error_count += 1
                _LOGGER.warning("No proxy connection slots available (consecutive errors: %d)", self._slot_error_count)
                if self._slot_error_count >= _SLOT_ERROR_THRESHOLD:
                    self._slot_backoff_until = datetime.now() + _SLOT_BACKOFF_DURATION
                    _LOGGER.warning(
                        "Backing off for %d minutes after repeated slot exhaustion",
                        int(_SLOT_BACKOFF_DURATION.total_seconds() // 60)
                    )
                raise
            except Exception as err:
                _LOGGER.error("Error communicating with %s: %s", self.address, err, exc_info=True)
                client = self._client
                self._client = None
                if client is not None:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                raise
        if pending:
            #show commanded values right away; replies to the queued requests correct them
            for attr, value in pending.items():
                setattr(self, attr, value)
            await self._update_callback()

    async def disconnect(self):
        """ disconnects the BLE client, guarded by the same lock as sendPacketBuffer """
        async with self._lock:
            if self._client is not None:
                client = self._client
                self._client = None
                self._connected_at = None
                try:
                    await client.disconnect()
                except Exception:
                    pass

    async def requestStateBuffered(self):
        """ adds a request for the current power state to the transmit buffer """
        await self._preparePacket(LedPacketCmd.POWER, request=True)

    async def requestBrightnessBuffered(self):
        """ adds a request for the current brightness state to the transmit buffer """
        await self._preparePacket(LedPacketCmd.BRIGHTNESS, request=True)

    async def requestColorBuffered(self):
        """ adds a request for the current color state to the transmit buffer """
        if self._segmented:
            #0x01 means first segment
            await self._preparePacket(LedPacketCmd.SEGMENT, b'\x01', request=True)
        else:
            #legacy devices
            await self._preparePacket(LedPacketCmd.COLOR, request=True)
    
    # The setters always send: the cached state can be stale (changes from the Govee app or
    # remote aren't pushed), and skipping "unchanged" values would silently drop commands.
    async def setStateBuffered(self, state: bool):
        """ adds the state to the transmit buffer """
        #0x1 = ON, Ox0 = OFF
        await self._preparePacket(LedPacketCmd.POWER, [0x1 if state else 0x0])
        await self.requestStateBuffered()
        self._pending["state"] = state

    async def setBrightnessBuffered(self, brightness: int):
        """ adds the brightness to the transmit buffer """
        #legacy devices 0-255
        payload = round(brightness)
        if self._segmented:
            #segmented devices 0-100
            payload = round(brightness / 255 * 100)
        await self._preparePacket(LedPacketCmd.BRIGHTNESS, [payload])
        await self.requestBrightnessBuffered()
        self._pending["brightness"] = brightness

    async def setColorBuffered(self, red: int, green: int, blue: int):
        """ adds the color to the transmit buffer """
        if self._segmented:
            await self._preparePacket(LedPacketCmd.COLOR, [LedColorType.SEGMENTS, 0x01, red, green, blue, 0, 0, 0, 0, 0, 0xff, 0xff])
        else:
            #legacy devices
            await self._preparePacket(LedPacketCmd.COLOR, [LedColorType.SINGLE, red, green, blue])
            await self._preparePacket(LedPacketCmd.COLOR, [LedColorType.LEGACY, red, green, blue])
        await self.requestColorBuffered()
        self._pending["color"] = (red, green, blue)
