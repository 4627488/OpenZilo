# SPDX-License-Identifier: MPL-2.0
"""BLE Nordic UART Service transport built on bleak."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ._errors import TransportError
from ._tasks import start_background_task


NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
DEFAULT_SCAN_TIMEOUT_S = 25.0
_NUS_WRITE_CHUNK_SIZE = 20


@dataclass(frozen=True)
class BleDeviceInfo:
    name: str | None
    address: str
    rssi: int | None = None


RxCallback = Callable[[bytes], None | Awaitable[None]]
DisconnectCallback = Callable[[], None | Awaitable[None]]


def _normalize_ble_address(address: str | None) -> str:
    return "".join(ch for ch in str(address or "") if ch.isalnum()).lower()


def _address_matches(candidate: object, expected: str | None) -> bool:
    expected_norm = _normalize_ble_address(expected)
    if not expected_norm:
        return True
    return _normalize_ble_address(str(candidate or "")) == expected_norm


class NusClient:
    """Cross-platform BLE/NUS client using bleak."""

    def __init__(
        self,
        *,
        address: str | None = None,
        service_uuid: str = NUS_SERVICE_UUID,
        tx_uuid: str = NUS_TX_UUID,
        rx_uuid: str = NUS_RX_UUID,
        scan_timeout_s: float = DEFAULT_SCAN_TIMEOUT_S,
        write_with_response: bool = False,
    ) -> None:
        self.address = address
        self.service_uuid = service_uuid
        self.tx_uuid = tx_uuid
        self.rx_uuid = rx_uuid
        self.scan_timeout_s = scan_timeout_s
        self.write_with_response = write_with_response
        self._client: Any | None = None
        self._rx_callback: RxCallback | None = None
        self._disconnect_callback: DisconnectCallback | None = None
        self._notify_started = False
        self._callback_tasks: set[asyncio.Task[Any]] = set()

    @staticmethod
    async def discover(
        *,
        address: str | None = None,
        timeout_s: float = DEFAULT_SCAN_TIMEOUT_S,
    ) -> list[BleDeviceInfo]:
        try:
            from bleak import BleakScanner
        except ImportError as exc:
            raise TransportError("Install bleak to use BLE transport") from exc

        devices = await BleakScanner.discover(
            timeout=timeout_s,
            return_adv=False,
        )

        results: list[BleDeviceInfo] = []
        for dev in devices:
            device_address = str(getattr(dev, "address", ""))
            if not _address_matches(device_address, address):
                continue
            results.append(
                BleDeviceInfo(
                    name=getattr(dev, "name", None),
                    address=device_address,
                    rssi=getattr(dev, "rssi", None),
                )
            )
        return results

    def set_rx_callback(self, callback: RxCallback | None) -> None:
        self._rx_callback = callback

    def _set_disconnect_callback(self, callback: DisconnectCallback | None) -> None:
        self._disconnect_callback = callback

    @property
    def is_connected(self) -> bool:
        return bool(self._client and self._client.is_connected)

    async def connect(self) -> None:
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError as exc:
            raise TransportError("Install bleak to use BLE transport") from exc

        if self.address is None:
            raise TransportError("BLE address is required; pass address='AA:BB:CC:DD:EE:FF'")

        target: Any = await BleakScanner.find_device_by_filter(
            lambda dev, _adv: _address_matches(getattr(dev, "address", ""), self.address),
            timeout=self.scan_timeout_s,
        )
        if target is None:
            target = self.address

        client = BleakClient(target, disconnected_callback=self._handle_disconnect)
        self._client = client
        try:
            await client.connect()
            await client.start_notify(self.tx_uuid, self._handle_notify)
            self._notify_started = True
        except BaseException as exc:
            self._client = None
            self._notify_started = False
            try:
                await asyncio.wait_for(client.disconnect(), 2.0)
            except asyncio.CancelledError:
                if not isinstance(exc, asyncio.CancelledError):
                    raise
            except Exception:
                pass
            if not isinstance(exc, Exception):
                raise
            raise TransportError(
                f"BLE connect failed for address={self.address!r}. "
                "The device was not found during scanning, then direct address connect also failed."
            ) from exc

    async def disconnect(self) -> None:
        if self._client is None:
            return
        try:
            if self._notify_started and self._client.is_connected:
                await self._client.stop_notify(self.tx_uuid)
        finally:
            self._notify_started = False
            if self._client.is_connected:
                await self._client.disconnect()
            self._client = None

    async def write(self, data: bytes | bytearray | memoryview) -> None:
        if self._client is None or not self._client.is_connected:
            raise TransportError("BLE client is not connected")

        payload = bytes(data)
        for offset in range(0, len(payload), _NUS_WRITE_CHUNK_SIZE):
            chunk = payload[offset : offset + _NUS_WRITE_CHUNK_SIZE]
            await self._client.write_gatt_char(
                self.rx_uuid,
                chunk,
                response=self.write_with_response,
            )
            await asyncio.sleep(0)

    async def __aenter__(self) -> "NusClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.disconnect()

    def _handle_notify(self, _sender: Any, data: bytearray) -> None:
        callback = self._rx_callback
        if callback is None:
            return

        result = callback(bytes(data))
        if inspect.isawaitable(result):
            start_background_task(self._callback_tasks, result, "BLE receive callback")

    def _handle_disconnect(self, _client: Any) -> None:
        self._notify_started = False
        callback = self._disconnect_callback
        if callback is None:
            return

        result = callback()
        if inspect.isawaitable(result):
            start_background_task(self._callback_tasks, result, "BLE disconnect callback")
