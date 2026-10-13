# SPDX-License-Identifier: MPL-2.0
"""Live recording subscription and streaming receive."""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ._errors import AudioDecodeError, ProtocolError, TimeoutError
from ._protocol import AudioCommand, ensure_success
from ._client import OpenZiloClient
from ._codec import _validate_opus_packet, build_opus_recording
from ._audio import _audio_operation, _PacketInbox

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveAudioSubscription:
    enabled: bool


@dataclass(frozen=True)
class LiveAudioStart:
    session_id: int
    record_time: int
    sample_rate: int
    channels: int
    codec: int


@dataclass(frozen=True)
class LiveAudioData:
    session_id: int
    sequence: int
    byte_offset: int
    data: bytes


@dataclass(frozen=True)
class LiveAudioEnd:
    error_code: int
    session_id: int
    produced_bytes: int
    sent_bytes: int
    dropped_frames: int


@dataclass(frozen=True)
class LiveAudioRecording:
    start: LiveAudioStart
    end: LiveAudioEnd
    data: bytes  # Complete OP2C file, suitable for decode_audio_to_wav().


async def set_live_audio_subscription(
    client: OpenZiloClient, enabled: bool, *, timeout_s: float | None = None,
) -> LiveAudioSubscription:
    """Select live-only output for subsequent recordings (no Flash copy).

    Enabling requires NUS notifications and ATT MTU >= 128. Firmware is the
    authority on MTU readiness. Disabling aborts an active live recording;
    disconnect clears the subscription. This never presses the record button.
    """
    if enabled and client._audio_owner not in (None, asyncio.current_task()):
        raise ProtocolError("Another audio operation is already active")
    timeout = client.command_timeout_s if timeout_s is None else timeout_s
    return await asyncio.wait_for(_set_live_audio_subscription(client, enabled, timeout), timeout)


async def _set_live_audio_subscription(
    client: OpenZiloClient, enabled: bool, timeout_s: float,
) -> LiveAudioSubscription:
    async with client._live_subscription_lock:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a bool")
        client._check_command_access(AudioCommand.LIVE_SUBSCRIBE)
        # If an enable response is lost, conservatively require disable/reconnect
        # before OTA rather than assuming the device still saves to Flash.
        if enabled:
            client._live_audio_subscribed = True
        packet = await client.request(
            AudioCommand.LIVE_SUBSCRIBE, AudioCommand.LIVE_SUBSCRIBE_RESP,
            bytes([int(enabled)]), timeout_s=timeout_s,
        )
        if len(packet.body) != 3 or packet.body[2] not in (0, 1):
            raise ProtocolError("Invalid live subscription response")
        error = struct.unpack_from(">H", packet.body)[0]
        client._live_audio_subscribed = bool(packet.body[2])
        ensure_success(error)
        if client._live_audio_subscribed != enabled:
            raise ProtocolError("Live subscription response does not match request")
        return LiveAudioSubscription(client._live_audio_subscribed)


def parse_live_audio_start(body: bytes) -> LiveAudioStart:
    if len(body) != 20:
        raise ProtocolError("Invalid live START length")
    session, reserved1, timestamp, reserved2, rate, channels, codec = struct.unpack(">IIIIHBB", body)
    if not session or reserved1 or reserved2 or (rate, channels, codec) != (16000, 2, 3):
        raise ProtocolError("Unsupported live START format")
    return LiveAudioStart(session, timestamp, rate, channels, codec)


def parse_live_audio_data(body: bytes) -> LiveAudioData:
    if len(body) < 15:
        raise ProtocolError("Truncated live DATA")
    session, sequence, offset, length = struct.unpack_from(">IIIH", body)
    if not session or not 1 <= length <= 100 or len(body) != 14 + length:
        raise ProtocolError("Invalid live DATA length or session")
    packet = body[14:]
    try:
        _validate_opus_packet(packet)
    except AudioDecodeError as exc:
        raise ProtocolError(str(exc)) from exc
    return LiveAudioData(session, sequence, offset, packet)


def parse_live_audio_end(body: bytes) -> LiveAudioEnd:
    if len(body) != 22:
        raise ProtocolError("Invalid live END length")
    error, session, reserved, produced, sent, dropped = struct.unpack(">HIIIII", body)
    if not session or reserved or sent > produced:
        raise ProtocolError("Invalid live END counters or session")
    return LiveAudioEnd(error, session, produced, sent, dropped)


@_audio_operation
async def receive_live_audio_file(
    client: OpenZiloClient,
    *,
    on_packet: Callable[[LiveAudioData], Any] | None = None,
    on_subscribed: Callable[[], Any] | None = None,
    timeout_s: float = 60.0,
    recording_timeout_s: float = 70.0,
) -> LiveAudioRecording:
    """Subscribe, receive one button-triggered recording and unsubscribe.

    No Flash copy is made by the device. on_packet receives each validated Opus
    packet immediately and may be sync or async. on_subscribed signals readiness
    to press the button. A successful return includes
    a complete OP2C file; gaps, errors, missing END or disconnect never succeed.
    """
    for value in (timeout_s, recording_timeout_s):
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Live audio timeouts must be finite and positive")
    if client._live_audio_subscribed:
        raise ProtocolError("Disable the existing live subscription before starting a managed recording")
    commands = (AudioCommand.LIVE_START, AudioCommand.LIVE_DATA, AudioCommand.LIVE_END)
    for command in commands:
        client._drain_queue(int(command))
    complete = False
    try:
        with _PacketInbox(client, commands) as inbox:
            await set_live_audio_subscription(client, True, timeout_s=timeout_s)
            if on_subscribed is not None:
                ready = on_subscribed()
                if inspect.isawaitable(ready):
                    await asyncio.wait_for(ready, timeout_s)
            first = await inbox.wait(timeout_s)
            if first.command != AudioCommand.LIVE_START:
                raise ProtocolError("Live recording did not begin with START")
            start = parse_live_audio_start(first.body)
            deadline = asyncio.get_running_loop().time() + recording_timeout_s
            packets: list[bytes] = []
            received = 0
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError("Live recording exceeded its time limit")
                packet = await inbox.wait(min(5.0, remaining))
                if packet.command == AudioCommand.LIVE_DATA:
                    frame = parse_live_audio_data(packet.body)
                    if (frame.session_id != start.session_id or frame.sequence != len(packets)
                            or frame.byte_offset != received):
                        raise ProtocolError("Live recording session, sequence or offset mismatch")
                    if len(packets) >= 3000:
                        raise ProtocolError("Live recording exceeds firmware's 60-second limit")
                    packets.append(frame.data)
                    received += len(frame.data)
                    if on_packet is not None:
                        result = on_packet(frame)
                        if inspect.isawaitable(result):
                            await asyncio.wait_for(result, max(0.0, deadline - asyncio.get_running_loop().time()))
                elif packet.command == AudioCommand.LIVE_END:
                    end = parse_live_audio_end(packet.body)
                    if end.session_id != start.session_id:
                        raise ProtocolError("Live END belongs to another recording")
                    ensure_success(end.error_code)
                    if end.dropped_frames or end.produced_bytes != received or end.sent_bytes != received:
                        raise ProtocolError("Live recording is incomplete according to END counters")
                    complete = True
                    return LiveAudioRecording(start, end, build_opus_recording(packets))
                else:
                    raise ProtocolError("Unexpected START during live recording")
    finally:
        if client.is_connected and client._live_audio_subscribed:
            try:
                await set_live_audio_subscription(client, False, timeout_s=2.0)
            except Exception as exc:
                # Live audio has no Flash copy, so keep a verified recording even if cleanup fails.
                if complete:
                    _logger.warning("Live recording completed, but unsubscribe failed: %s", exc)
            except asyncio.CancelledError:
                if complete:
                    raise
