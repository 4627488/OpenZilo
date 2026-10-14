# SPDX-License-Identifier: MPL-2.0
"""Saved recording transfer: listing, downloading and automatic receive."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import IntEnum
from functools import wraps
from typing import Any

from ._errors import ProtocolError, TimeoutError, TransportError
from ._protocol import AudioCommand, BinaryReader, BinaryWriter, ensure_success, Packet, read_error
from ._client import OpenZiloClient


@dataclass(frozen=True)
class AudioFileInfo:
    file_index: int
    record_time: int
    data_size: int


@dataclass(frozen=True)
class AudioDataFrame:
    file_index: int
    frame_offset: int
    frame_size: int
    is_end: bool
    data: bytes


@dataclass(frozen=True)
class AudioRecordResult:
    file_index: int


AudioProgressCallback = Callable[[int, int], None]


class ProgressPrinter:
    def __init__(self, *, prefix: str = "progress") -> None:
        self.prefix = prefix
        self._last_percent = -1

    def __call__(self, current: int, total: int) -> None:
        percent = int(current * 100 / total) if total else 0
        if percent == self._last_percent:
            return
        self._last_percent = percent
        print(f"{self.prefix}: {current}/{total} bytes ({percent}%)")


def _audio_operation(function: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @wraps(function)
    async def guarded(client: OpenZiloClient, *args: Any, **kwargs: Any) -> Any:
        task = asyncio.current_task()
        if client._firmware_update_active:
            raise ProtocolError("Firmware update owns this connection")
        if client._audio_owner is not None and client._audio_owner is not task:
            raise ProtocolError("Another audio operation is already active")
        nested = client._audio_owner is task
        client._audio_owner = task
        try:
            return await function(client, *args, **kwargs)
        finally:
            if not nested:
                client._audio_owner = None
    return guarded


class _PacketInbox:
    """Temporarily own several commands in notification order, without duplicate queues."""

    def __init__(self, client: OpenZiloClient, commands: tuple[IntEnum, ...]) -> None:
        self.client = client
        self.commands = commands
        self.queue: asyncio.Queue[Packet] = asyncio.Queue(maxsize=client._receive_queue_size)
        self.error: ProtocolError | None = None
        self.registered: list[IntEnum] = []

    def _receive(self, packet: Packet) -> None:
        if self.queue.full():
            self.error = ProtocolError("Audio receive queue overflow; recording is incomplete")
        else:
            self.queue.put_nowait(packet)

    def __enter__(self) -> "_PacketInbox":
        try:
            for command in self.commands:
                if self.client._handlers[int(command)]:
                    raise ProtocolError("Audio command already has a packet handler")
            for command in self.commands:
                pending = self.client._queues[int(command)]
                while not pending.empty():
                    self._receive(pending.get_nowait())
                self.client.add_packet_handler(command, self._receive, queue_packets=False)
                self.registered.append(command)
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_args: Any) -> None:
        for command in self.registered:
            self.client.remove_packet_handler(command, self._receive)
        # A legacy automatic upload may arrive entirely in one notification.
        # Return its remaining frames to the ordinary queue after selecting the first.
        while not self.queue.empty():
            packet = self.queue.get_nowait()
            if not self.client.is_connected:
                continue
            target = self.client._queues[packet.command]
            if target.full():
                self.client._report_protocol_error(ProtocolError("Audio receive queue overflow"))
            else:
                target.put_nowait(packet)

    async def wait(self, timeout_s: float | None) -> Packet:
        if self.error is not None:
            raise self.error
        timeout = self.client.command_timeout_s if timeout_s is None else timeout_s
        if self.client._disconnected.is_set() and self.queue.empty():
            raise TransportError("BLE disconnected while receiving audio")
        packet_task = asyncio.create_task(self.queue.get())
        error_task = asyncio.create_task(self.client._protocol_errors.get())
        disconnected = asyncio.create_task(self.client._disconnected.wait())
        tasks = {packet_task, error_task, disconnected}
        try:
            done, _ = await asyncio.wait(tasks, timeout=max(0.0, timeout),
                                         return_when=asyncio.FIRST_COMPLETED)
            if self.error is not None:
                raise self.error
            if error_task in done:
                raise error_task.result()
            if packet_task in done:
                return packet_task.result()
            if disconnected in done:
                raise TransportError("BLE disconnected while receiving audio")
            raise TimeoutError("Timed out waiting for recording data or completion")
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def parse_audio_record_result(body: bytes) -> AudioRecordResult:
    reader = BinaryReader(body)
    ensure_success(reader.u16())  # Firmware error replies can contain only two bytes.
    result = AudioRecordResult(reader.u32())
    if reader.remaining:
        raise ProtocolError("Unexpected recording result bytes")
    return result


@_audio_operation
async def wait_audio_record_result(
    client: OpenZiloClient, *, timeout_s: float | None = None,
) -> AudioRecordResult:
    """Wait for 050A local-save completion; does not download or start recording."""
    packet = await client.wait_for_command(AudioCommand.RECORD_RESULT, timeout_s=timeout_s)
    return parse_audio_record_result(packet.body)


async def get_audio_file_count(
    client: OpenZiloClient,
    *,
    timeout_s: float | None = None,
) -> int:
    packet = await client.request(
        AudioCommand.GET_LIST,
        AudioCommand.LIST_RESP,
        timeout_s=timeout_s,
    )
    reader = BinaryReader(packet.body)
    ensure_success(read_error(reader))
    return reader.u32()


@_audio_operation
async def get_audio_file_info(
    client: OpenZiloClient,
    file_index: int,
    *,
    timeout_s: float | None = None,
) -> AudioFileInfo:
    """Start the normal 0x0503 extraction flow and return recording metadata."""
    body = BinaryWriter().u16(0).u32(file_index).build()
    packet = await client.request(
        AudioCommand.START_EXTRACT,
        AudioCommand.FILE_INFO_RESP,
        body,
        timeout_s=timeout_s,
    )
    return parse_audio_file_info(packet.body)


@_audio_operation
async def read_audio_frame(
    client: OpenZiloClient,
    file_index: int,
    frame_offset: int,
    *,
    timeout_s: float | None = None,
) -> AudioDataFrame:
    body = _audio_frame_request_body(file_index, frame_offset)
    packet = await client.request(
        AudioCommand.NEXT_FRAME,
        AudioCommand.DATA_FRAME,
        body,
        timeout_s=timeout_s,
    )
    return parse_audio_data_frame(packet.body)


@_audio_operation
async def end_audio_extract(
    client: OpenZiloClient,
    file_index: int,
    *,
    timeout_s: float | None = None,
    ignore_timeout: bool = True,
) -> None:
    body = BinaryWriter().u16(0).u32(file_index).build()
    try:
        packet = await client.request(
            AudioCommand.END_EXTRACT,
            AudioCommand.EXTRACT_DONE,
            body,
            timeout_s=timeout_s,
        )
    except TimeoutError:
        if ignore_timeout:
            return
        raise
    reader = BinaryReader(packet.body)
    ensure_success(read_error(reader))


def _audio_frame_request_body(file_index: int, frame_offset: int) -> bytes:
    # Keep the reserved bytes required by the 12-byte 0x0506 request body.
    return BinaryWriter().u16(0).u32(file_index).u32(frame_offset).u16(0).build()


async def _wait_audio_data_frame(
    client: OpenZiloClient,
    file_index: int,
    *,
    timeout_s: float | None = None,
) -> AudioDataFrame:
    timeout = client.command_timeout_s if timeout_s is None else timeout_s
    deadline = asyncio.get_running_loop().time() + max(0.001, timeout)
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(
                f"Timed out waiting for audio frame for file_index={file_index}"
            )
        packet = await client.wait_for_command(
            AudioCommand.DATA_FRAME,
            timeout_s=remaining,
        )
        frame = parse_audio_data_frame(packet.body)
        if frame.file_index == file_index:
            return frame


async def _request_audio_retry(
    client: OpenZiloClient,
    file_index: int,
    frame_offset: int,
) -> None:
    await client.send_command(
        AudioCommand.NEXT_FRAME,
        _audio_frame_request_body(file_index, frame_offset),
    )


@_audio_operation
async def receive_auto_audio_file(
    client: OpenZiloClient,
    *,
    timeout_s: float | None = None,
) -> tuple[int, bytes]:
    """Receive one saved recording from either firmware generation.

    Legacy firmware pushes 0505; new firmware sends 050A and the SDK downloads
    that file explicitly. Returns (file_index, original bytes), which may be
    Speex or OP2C. Live-only recordings use receive_live_audio_file instead.
    Competing audio operations are rejected.
    """
    if not client.is_connected:
        raise TransportError("BLE client is not connected")

    with _PacketInbox(client, (AudioCommand.RECORD_RESULT, AudioCommand.DATA_FRAME)) as inbox:
        packet = await inbox.wait(timeout_s)
    if packet.command == AudioCommand.RECORD_RESULT:
        result = parse_audio_record_result(packet.body)
        info, data = await download_audio_file(client, result.file_index, quick=False, timeout_s=timeout_s)
        return info.file_index, data
    frame = parse_audio_data_frame(packet.body)
    file_index = frame.file_index
    received = bytearray()
    pending: dict[int, AudioDataFrame] = {}
    end_offset: int | None = None
    expected_size: int | None = None
    recovery_attempts = 0

    def add_frame(current: AudioDataFrame) -> bool:
        nonlocal end_offset

        if current.file_index != file_index:
            raise ProtocolError(
                f"Audio file index mismatch: expected {file_index}, "
                f"got {current.file_index}"
            )

        if expected_size is not None and current.frame_offset > expected_size:
            raise ProtocolError(
                f"Audio frame offset {current.frame_offset} exceeds "
                f"file size {expected_size}"
            )

        frame_data = current.data
        if expected_size is not None:
            remaining = max(0, expected_size - current.frame_offset)
            frame_data = frame_data[:remaining]

        frame_end = current.frame_offset + len(frame_data)
        if current.is_end and expected_size is None:
            if end_offset is not None and end_offset != frame_end:
                raise ProtocolError(
                    "Conflicting audio end offsets: "
                    f"{end_offset} and {frame_end}"
                )
            end_offset = frame_end

        previous_size = len(received)
        if frame_end <= previous_size:
            overlap_size = len(frame_data)
            if received[current.frame_offset:frame_end] != frame_data[:overlap_size]:
                raise ProtocolError(
                    f"Conflicting audio data at offset {current.frame_offset}"
                )
            return False
        if current.frame_offset <= previous_size:
            overlap = previous_size - current.frame_offset
            if received[current.frame_offset:previous_size] != frame_data[:overlap]:
                raise ProtocolError(
                    f"Conflicting audio overlap at offset {current.frame_offset}"
                )
            received.extend(frame_data[overlap:])
            return len(received) > previous_size

        existing = pending.get(current.frame_offset)
        if existing is None or len(existing.data) < len(current.data):
            pending[current.frame_offset] = current
        return False

    async def ensure_recovery_metadata() -> None:
        nonlocal end_offset, expected_size

        if expected_size is not None:
            return
        info = await get_audio_file_info(
            client,
            file_index,
            timeout_s=timeout_s,
        )
        if info.file_index != file_index:
            raise ProtocolError(
                f"Audio metadata index mismatch: expected {file_index}, "
                f"got {info.file_index}"
            )
        if info.data_size <= 0:
            raise ProtocolError(
                f"Audio metadata has invalid data_size={info.data_size}"
            )
        expected_size = info.data_size
        end_offset = expected_size
        if len(received) > expected_size:
            del received[expected_size:]
        for offset in list(pending):
            if offset >= expected_size:
                pending.pop(offset)

    def append_pending() -> bool:
        grew = False
        while pending:
            offset = min(pending)
            if offset > len(received):
                break
            current = pending.pop(offset)
            if add_frame(current):
                grew = True
        return grew

    while True:
        grew = add_frame(frame)
        if append_pending():
            grew = True
        if grew:
            recovery_attempts = 0

        if end_offset is not None and len(received) >= end_offset:
            return file_index, bytes(received[:end_offset])

        has_gap = bool(pending) and min(pending) > len(received)
        if has_gap:
            recovery_attempts += 1
            if recovery_attempts > 3:
                raise ProtocolError(
                    "Audio frame gap: "
                    f"unable to recover offset {len(received)}"
                )
            await ensure_recovery_metadata()
            if expected_size is not None and len(received) >= expected_size:
                return file_index, bytes(received[:expected_size])
            await _request_audio_retry(client, file_index, len(received))

        while True:
            try:
                frame = await _wait_audio_data_frame(
                    client,
                    file_index,
                    timeout_s=timeout_s,
                )
                break
            except (TimeoutError, ProtocolError) as exc:
                recovery_attempts += 1
                if recovery_attempts > 3:
                    raise ProtocolError(
                        "Audio stream stalled: "
                        f"unable to recover offset {len(received)}"
                    ) from exc
                await ensure_recovery_metadata()
                if expected_size is not None and len(received) >= expected_size:
                    return file_index, bytes(received[:expected_size])
                await _request_audio_retry(client, file_index, len(received))


async def _download_audio_file_quick(
    client: OpenZiloClient,
    file_index: int,
    *,
    progress: AudioProgressCallback | None = None,
    timeout_s: float | None = None,
) -> tuple[AudioFileInfo, bytes]:
    client._drain_queue(int(AudioCommand.FILE_INFO_RESP))
    client._drain_queue(int(AudioCommand.DATA_FRAME))
    await client.send_command(
        AudioCommand.START_EXTRACT_QUICK,
        BinaryWriter().u16(0).u32(file_index).build(),
    )

    info_packet = await client.wait_for_command(
        AudioCommand.FILE_INFO_RESP,
        timeout_s=timeout_s,
    )
    info = parse_audio_file_info(info_packet.body)
    if info.file_index != file_index:
        raise ProtocolError(
            f"Audio metadata index mismatch: expected {file_index}, got {info.file_index}"
        )
    received = bytearray()
    gap_retries = 0

    while True:
        try:
            frame = await _wait_audio_data_frame(
                client,
                file_index,
                timeout_s=timeout_s,
            )
        except TimeoutError as exc:
            gap_retries += 1
            if gap_retries > 3:
                raise ProtocolError(
                    f"Audio stream stalled at offset {len(received)}"
                ) from exc
            await _request_audio_retry(client, file_index, len(received))
            frame = await _wait_audio_data_frame(
                client,
                file_index,
                timeout_s=timeout_s,
            )

        if frame.frame_offset > len(received):
            gap_retries += 1
            if gap_retries > 3:
                raise ProtocolError(
                    "Audio frame gap: "
                    f"expected offset {len(received)}, got {frame.frame_offset}"
                )
            await _request_audio_retry(client, file_index, len(received))
            continue

        overlap = len(received) - frame.frame_offset
        overlap_size = min(overlap, len(frame.data))
        if overlap_size > 0:
            existing = received[
                frame.frame_offset : frame.frame_offset + overlap_size
            ]
            if existing != frame.data[:overlap_size]:
                raise ProtocolError(
                    f"Conflicting audio overlap at offset {frame.frame_offset}"
                )
        if overlap < len(frame.data):
            new_data = frame.data[overlap:]
            if info.data_size > 0:
                new_data = new_data[: max(0, info.data_size - len(received))]
            received.extend(new_data)

        if overlap < len(frame.data):
            gap_retries = 0

        if progress:
            progress(len(received), info.data_size)
        if info.data_size > 0 and len(received) >= info.data_size:
            break
        if frame.is_end:
            gap_retries += 1
            if gap_retries > 3:
                raise ProtocolError(
                    f"Audio stream ended at {len(received)} of {info.data_size} bytes"
                )
            await _request_audio_retry(client, file_index, len(received))
        elif not frame.data:
            raise ProtocolError(
                f"Empty audio frame at offset {frame.frame_offset} before end"
            )

    data = bytes(received[: info.data_size] if info.data_size > 0 else received)
    return info, data


@_audio_operation
async def clear_audio_files(
    client: OpenZiloClient,
    *,
    timeout_s: float | None = None,
) -> None:
    packet = await client.request(
        AudioCommand.CLEAR_ALL,
        AudioCommand.CLEAR_ALL_RESP,
        timeout_s=timeout_s,
    )
    reader = BinaryReader(packet.body)
    ensure_success(read_error(reader))


@_audio_operation
async def download_audio_file(
    client: OpenZiloClient,
    file_index: int,
    *,
    progress: AudioProgressCallback | None = None,
    timeout_s: float | None = None,
    quick: bool = True,
) -> tuple[AudioFileInfo, bytes]:
    if quick:
        return await _download_audio_file_quick(
            client,
            file_index,
            progress=progress,
            timeout_s=timeout_s,
        )

    try:
        info = await get_audio_file_info(
            client,
            file_index,
            timeout_s=timeout_s,
        )
        if info.file_index != file_index:
            raise ProtocolError(
                f"Audio metadata index mismatch: expected {file_index}, got {info.file_index}"
            )
        received = bytearray()

        while True:
            frame = await read_audio_frame(
                client,
                file_index,
                len(received),
                timeout_s=timeout_s,
            )
            if frame.frame_offset > len(received):
                raise ProtocolError(
                    f"Audio frame gap: expected offset {len(received)}, "
                    f"got {frame.frame_offset}"
                )
            overlap = len(received) - frame.frame_offset
            overlap_size = min(overlap, len(frame.data))
            if overlap_size > 0:
                existing = received[
                    frame.frame_offset : frame.frame_offset + overlap_size
                ]
                if existing != frame.data[:overlap_size]:
                    raise ProtocolError(
                        f"Conflicting audio overlap at offset {frame.frame_offset}"
                    )
            new_data = frame.data[overlap:]
            if info.data_size > 0:
                new_data = new_data[: max(0, info.data_size - len(received))]
            received.extend(new_data)
            if progress:
                progress(len(received), info.data_size)
            if info.data_size > 0 and len(received) >= info.data_size:
                break
            if frame.is_end:
                raise ProtocolError(
                    f"Audio stream ended at {len(received)} of {info.data_size} bytes"
                )
            if not new_data:
                raise ProtocolError(
                    f"Audio transfer made no progress at offset {len(received)}"
                )
    except (Exception, asyncio.CancelledError):
        if client.is_connected:
            try:
                await asyncio.wait_for(client.request(
                    AudioCommand.END_EXTRACT, AudioCommand.EXTRACT_DONE,
                    BinaryWriter().u16(0).u32(file_index).build(), timeout_s=2.0,
                ), timeout=2.0)
            except (Exception, asyncio.CancelledError):
                pass
        raise
    await end_audio_extract(client, file_index, timeout_s=timeout_s, ignore_timeout=False)
    data = bytes(received[: info.data_size] if info.data_size > 0 else received)
    return info, data


def parse_audio_file_info(body: bytes) -> AudioFileInfo:
    reader = BinaryReader(body)
    ensure_success(read_error(reader))
    info = AudioFileInfo(
        file_index=reader.u32(),
        record_time=reader.u32(),
        data_size=reader.u32(),
    )
    if reader.remaining:
        raise ProtocolError(
            f"Unexpected trailing audio file info bytes: {reader.remaining}"
        )
    return info


def parse_audio_data_frame(body: bytes) -> AudioDataFrame:
    reader = BinaryReader(body)
    ensure_success(read_error(reader))
    file_index = reader.u32()
    frame_offset = reader.u32()
    frame_size = reader.u32()
    is_end = bool(reader.u8())
    if reader.remaining != frame_size:
        raise ProtocolError(
            f"Audio frame size mismatch: declared {frame_size}, "
            f"got {reader.remaining}"
        )
    data = reader.bytes(frame_size)
    return AudioDataFrame(
        file_index=file_index,
        frame_offset=frame_offset,
        frame_size=frame_size,
        is_end=is_end,
        data=data,
    )
