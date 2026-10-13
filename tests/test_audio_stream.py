# SPDX-License-Identifier: MPL-2.0
"""New firmware wire compatibility; all recordings are synthetic."""
import asyncio
import io
import shutil
import struct
import unittest
import wave

import openzilo as sdk

OPUS = b"\xfc\xff\xfe"  # Synthetic stereo 20 ms silence.
HEADER = struct.pack("<4sHHHH", b"OP2C", 1, 2, 16000, 320)
RECORDING = HEADER + struct.pack("<H", len(OPUS)) + OPUS


class AudioPeer:
    is_connected = True

    def __init__(self, fault=None):
        self.fault = fault
        self.commands = []
        self.started = asyncio.Event()
        self.client = sdk.OpenZiloClient(transport=self, receive_queue_size=2 if fault == "overflow" else 256)
        self.client._disconnected.clear()

    def emit(self, *packets):
        self.client._on_rx(b"".join(sdk.encode_packet(command, body) for command, body in packets))

    async def write(self, data):
        p = sdk.decode_packet(data)
        self.commands.append((p.command, p.body))
        if p.command == 0x050D:
            enabled = p.body[0]
            if not enabled and self.fault == "unsubscribe":
                raise sdk.TransportError("unsubscribe write failed")
            self.emit((0x050E, struct.pack(">HB", 8 if self.fault == "mtu" and enabled else 0,
                                          0 if self.fault == "mtu" else enabled)))
            if not enabled or self.fault == "mtu":
                return
            self.started.set()
            start = (0x050F, struct.pack(">IIIIHBB", 7, 0, 100, 0, 16000, 2, 3))
            count = 3
            packets = [start]
            for index in range(count):
                sequence = index + 1 if self.fault == "gap" else index
                packets.append((0x0510, struct.pack(">IIIH", 7, sequence, index * 3, 3) + OPUS))
            packets.append((0x0511, struct.pack(">HIIIII", 8 if self.fault == "device" else 0,
                                                8 if self.fault == "session" else 7, 0,
                                                10 if self.fault == "length" else 9, 9, 0)))
            if self.fault == "cancel":
                self.emit(start)
            elif self.fault == "disconnect":
                self.is_connected = False
                self.client._on_disconnect()
            else:
                # START/DATA/END can all arrive before subscription await resumes.
                self.emit(*packets)
        elif p.command == 0x0503:
            self.emit((0x0504, struct.pack(">HIII", 0, 4, 100, len(RECORDING))))
        elif p.command == 0x0506:
            offset = struct.unpack_from(">I", p.body, 6)[0]
            chunk = RECORDING[offset:offset + 7]
            self.emit((0x0505, struct.pack(">HIIIB", 0, 4, offset, len(chunk),
                                          offset + len(chunk) == len(RECORDING)) + chunk))
        elif p.command == 0x0507:
            self.emit((0x0508, struct.pack(">HI", 0, 4)))


class NewAudioTests(unittest.IsolatedAsyncioTestCase):
    def test_op2c_parser_rejects_bad_header_truncation_and_wrong_audio_format(self):
        self.assertEqual(sdk.parse_opus_recording(RECORDING), [OPUS])
        self.assertEqual(sdk.build_opus_recording([OPUS]), RECORDING)
        for raw in (HEADER[:9], HEADER + b"\x03", RECORDING[:-1],
                    HEADER + b"\x00\x00", HEADER + b"\x03\x00\xf8\xff\xfe",
                    HEADER + b"\x03\x00\xf4\xff\xfe"):
            with self.subTest(raw=raw), self.assertRaises(sdk.AudioDecodeError):
                sdk.parse_opus_recording(raw)
        with self.assertRaises(sdk.DeviceError) as error:
            sdk.parse_audio_record_result(struct.pack(">H", 1))
        self.assertEqual(error.exception.error_code, 1)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is optional")
    def test_opus_decodes_to_stereo_wav_without_legacy_mono_defaults(self):
        raw = sdk.build_opus_recording([OPUS] * 5)
        playable = sdk.build_playable_audio(raw, pcm_config=sdk.PcmConfig(channels=1))
        self.assertEqual(playable.source_type, "opus-stereo")
        with wave.open(io.BytesIO(playable.bytes)) as wav:
            self.assertEqual((wav.getnchannels(), wav.getframerate(), wav.getsampwidth(), wav.getnframes()),
                             (2, 16000, 2, 1600))

    async def test_saved_notification_download_and_legacy_push_both_work(self):
        peer = AudioPeer()
        asyncio.get_running_loop().call_soon(peer.emit, (0x050A, struct.pack(">HI", 0, 4)))
        index, data = await sdk.receive_auto_audio_file(peer.client, timeout_s=1)
        self.assertEqual((index, data), (4, RECORDING))
        self.assertEqual(peer.commands[-1][0], 0x0507)
        self.assertNotIn(0x050D, [command for command, _ in peer.commands])
        peer.commands.clear()
        chunks = [b"abc", b"def"]
        packets = [(0x0505, struct.pack(">HIIIB", 0, 5, n * 3, 3, n == 1) + chunk)
                   for n, chunk in enumerate(chunks)]
        asyncio.get_running_loop().call_soon(peer.emit, *packets)
        self.assertEqual(await sdk.receive_auto_audio_file(peer.client, timeout_s=1), (5, b"abcdef"))
        self.assertEqual(peer.commands, [])

    async def test_live_notifications_before_ack_resume_are_ordered_and_unsubscribed(self):
        peer = AudioPeer()
        received = []
        ready = []
        recording = await sdk.receive_live_audio_file(
            peer.client, on_packet=received.append, on_subscribed=lambda: ready.append(True), timeout_s=1,
        )
        self.assertEqual(ready, [True])
        self.assertEqual([frame.sequence for frame in received], [0, 1, 2])
        self.assertEqual(recording.data, sdk.build_opus_recording([OPUS] * 3))
        self.assertEqual(recording.end.sent_bytes, 9)
        self.assertEqual(peer.commands, [(0x050D, b"\x01"), (0x050D, b"\x00")])
        self.assertFalse(peer.client._live_audio_subscribed)

    async def test_verified_live_recording_survives_unsubscribe_failure(self):
        peer = AudioPeer("unsubscribe")
        with self.assertLogs("openzilo", "WARNING"):
            recording = await sdk.receive_live_audio_file(peer.client, timeout_s=1)
        self.assertEqual(recording.data, sdk.build_opus_recording([OPUS] * 3))
        self.assertTrue(peer.client._live_audio_subscribed)

    async def test_incomplete_or_failed_live_stream_never_returns_success(self):
        for fault, expected in (("gap", sdk.ProtocolError), ("length", sdk.ProtocolError),
                                ("session", sdk.ProtocolError), ("device", sdk.DeviceError),
                                ("mtu", sdk.DeviceError), ("overflow", sdk.ProtocolError),
                                ("disconnect", sdk.TransportError)):
            with self.subTest(fault=fault):
                peer = AudioPeer(fault)
                with self.assertRaises(expected):
                    await sdk.receive_live_audio_file(peer.client, timeout_s=0.1)
                self.assertFalse(peer.client._live_audio_subscribed)
                self.assertIsNone(peer.client._audio_owner)
                self.assertFalse(peer.client._callback_only)

    async def test_cancellation_unsubscribes_without_losing_cancellation(self):
        peer = AudioPeer("cancel")
        task = asyncio.create_task(sdk.receive_live_audio_file(peer.client, timeout_s=1))
        await peer.started.wait()
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(peer.commands[-1], (0x050D, b"\x00"))
        self.assertFalse(peer.client._live_audio_subscribed)
        self.assertIsNone(peer.client._audio_owner)
