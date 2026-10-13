# SPDX-License-Identifier: MPL-2.0
"""IMU reports and gesture/button events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from ._errors import ProtocolError
from ._protocol import BinaryReader, ensure_success, read_error, SensorCommand
from ._client import OpenZiloClient


class SensorGestureId(IntEnum):
    IDLE = 0
    ROTATE_BACK = 1
    ROTATE_FRONT = 2
    WAVE = 3


_SENSOR_GESTURE_NAMES: dict[int, str] = {
    int(SensorGestureId.IDLE): "idle",
    int(SensorGestureId.ROTATE_BACK): "rotate_back",
    int(SensorGestureId.ROTATE_FRONT): "rotate_front",
    int(SensorGestureId.WAVE): "wave",
}


@dataclass(frozen=True)
class SensorStartInfo:
    sample_rate_hz: int
    accel_range_g: int
    gyro_range_dps: int


@dataclass(frozen=True)
class SensorStopInfo:
    pass


@dataclass(frozen=True)
class SensorDataSample:
    timestamp_ms: int
    accel_x: int
    accel_y: int
    accel_z: int
    gyro_x: int
    gyro_y: int
    gyro_z: int


@dataclass(frozen=True)
class SensorDataBatch:
    sequence_start: int
    frame_count: int
    sample_size: int
    samples: tuple[SensorDataSample, ...]


@dataclass(frozen=True)
class SensorDoubleTapEvent:
    timestamp_ms: int


@dataclass(frozen=True)
class SensorGestureEvent:
    timestamp_ms: int
    gesture_id: int


@dataclass(frozen=True)
class SensorKeyDoublePressEvent:
    timestamp_ms: int


@dataclass(frozen=True)
class SensorKeySinglePressEvent:
    timestamp_ms: int


async def start_sensor_report(
    client: OpenZiloClient,
    *,
    timeout_s: float | None = None,
) -> SensorStartInfo:
    """Start IMU reports. single-sample IMU firmware starts capture; gesture firmware requires
    gesture mode first. Both single-sample and batch reports are supported.
    """
    packet = await client.request(
        SensorCommand.START_REPORT,
        SensorCommand.START_REPORT_RESP,
        timeout_s=timeout_s,
    )
    reader = BinaryReader(packet.body)
    ensure_success(read_error(reader))
    return SensorStartInfo(
        sample_rate_hz=reader.u16(),
        accel_range_g=reader.u16(),
        gyro_range_dps=reader.u16(),
    )


async def stop_sensor_report(
    client: OpenZiloClient,
    *,
    timeout_s: float | None = None,
) -> SensorStopInfo:
    """Stop reports; single-sample IMU firmware also stops capture, gesture firmware may retain it."""
    packet = await client.request(
        SensorCommand.STOP_REPORT,
        SensorCommand.STOP_REPORT_RESP,
        timeout_s=timeout_s,
    )
    reader = BinaryReader(packet.body)
    ensure_success(read_error(reader))
    return SensorStopInfo()


async def wait_sensor_data(
    client: OpenZiloClient,
    *,
    timeout_s: float | None = None,
) -> SensorDataBatch:
    """Wait for one 0x0605 batch after start_sensor_report() succeeds."""
    packet = await client.wait_for_command(SensorCommand.DATA_FRAME, timeout_s=timeout_s)
    return parse_sensor_data_batch(packet.body)


def _read_sensor_sample(reader: BinaryReader) -> SensorDataSample:
    return SensorDataSample(
        timestamp_ms=reader.u32(),
        accel_x=reader.i16(),
        accel_y=reader.i16(),
        accel_z=reader.i16(),
        gyro_x=reader.i16(),
        gyro_y=reader.i16(),
        gyro_z=reader.i16(),
    )


def parse_sensor_data_batch(body: bytes) -> SensorDataBatch:
    reader = BinaryReader(body)
    ensure_success(read_error(reader))
    sequence_start = reader.u32()
    # The original single-sample IMU format is exactly 22 bytes; a valid batch is
    # 10 + N * 16 bytes, so the two wire formats cannot overlap.
    if len(body) == 22:
        return SensorDataBatch(
            sequence_start=sequence_start, frame_count=1, sample_size=16,
            samples=(_read_sensor_sample(reader),),
        )
    frame_count = reader.u16()
    sample_size = reader.u16()
    if sample_size != 16:
        raise ProtocolError(f"Unsupported sensor sample size: {sample_size}")
    expected_remaining = frame_count * sample_size
    if reader.remaining != expected_remaining:
        raise ProtocolError(
            f"Sensor batch length mismatch: expected {expected_remaining} sample bytes, "
            f"got {reader.remaining}"
        )
    samples = tuple(_read_sensor_sample(reader) for _ in range(frame_count))
    return SensorDataBatch(
        sequence_start=sequence_start,
        frame_count=frame_count,
        sample_size=sample_size,
        samples=samples,
    )


def parse_sensor_double_tap_event(body: bytes) -> SensorDoubleTapEvent:
    reader = BinaryReader(body)
    event = SensorDoubleTapEvent(timestamp_ms=reader.u32())
    if reader.remaining:
        raise ProtocolError(f"Unexpected trailing double-tap event bytes: {reader.remaining}")
    return event


def parse_sensor_gesture_event(body: bytes) -> SensorGestureEvent:
    reader = BinaryReader(body)
    event = SensorGestureEvent(timestamp_ms=reader.u32(), gesture_id=reader.u8())
    if reader.remaining:
        raise ProtocolError(f"Unexpected trailing gesture event bytes: {reader.remaining}")
    return event


def sensor_gesture_name(gesture_id: int | SensorGestureId) -> str:
    value = int(gesture_id)
    return _SENSOR_GESTURE_NAMES.get(value, f"unknown({value})")


def parse_sensor_key_double_press_event(body: bytes) -> SensorKeyDoublePressEvent:
    reader = BinaryReader(body)
    event = SensorKeyDoublePressEvent(timestamp_ms=reader.u32())
    if reader.remaining:
        raise ProtocolError(
            f"Unexpected trailing key double-press event bytes: {reader.remaining}"
        )
    return event


def parse_sensor_key_single_press_event(body: bytes) -> SensorKeySinglePressEvent:
    reader = BinaryReader(body)
    event = SensorKeySinglePressEvent(timestamp_ms=reader.u32())
    if reader.remaining:
        raise ProtocolError(
            f"Unexpected trailing key single-press event bytes: {reader.remaining}"
        )
    return event


async def wait_sensor_double_tap_event(
    client: OpenZiloClient,
    *,
    timeout_s: float | None = None,
) -> SensorDoubleTapEvent:
    packet = await client.wait_for_command(SensorCommand.DOUBLE_TAP, timeout_s=timeout_s)
    return parse_sensor_double_tap_event(packet.body)


async def wait_sensor_gesture_event(
    client: OpenZiloClient,
    *,
    timeout_s: float | None = None,
) -> SensorGestureEvent:
    packet = await client.wait_for_command(SensorCommand.GESTURE, timeout_s=timeout_s)
    return parse_sensor_gesture_event(packet.body)


async def wait_sensor_key_double_press_event(
    client: OpenZiloClient,
    *,
    timeout_s: float | None = None,
) -> SensorKeyDoublePressEvent:
    packet = await client.wait_for_command(
        SensorCommand.KEY_DOUBLE_PRESS,
        timeout_s=timeout_s,
    )
    return parse_sensor_key_double_press_event(packet.body)


async def wait_sensor_key_single_press_event(
    client: OpenZiloClient,
    *,
    timeout_s: float | None = None,
) -> SensorKeySinglePressEvent:
    packet = await client.wait_for_command(
        SensorCommand.KEY_SINGLE_PRESS,
        timeout_s=timeout_s,
    )
    return parse_sensor_key_single_press_event(packet.body)
