# SPDX-License-Identifier: MPL-2.0
"""Consume live PCM as it arrives and optionally save one verified WAV.

Install with uv sync --extra pcm. No ffmpeg executable is required.
"""

import argparse
import asyncio
import wave
from pathlib import Path

import openzilo as sdk


async def main(address: str, output: Path | None) -> None:
    # This example collects PCM only when a file is requested. Streaming itself
    # keeps bounded queues; applications can feed frames directly to ASR/playback.
    chunks: list[bytes] = []
    async with sdk.OpenZiloClient(address=address) as ring:
        async with sdk.open_live_audio_stream(ring) as stream:
            print("Subscribed. Hold the record button; release to finish.", flush=True)
            async for event in stream:
                if isinstance(event, sdk.LiveAudioStart):
                    print(f"START: {event.sample_rate} Hz, {event.channels} channels")
                elif isinstance(event, sdk.LivePcmFrame):
                    # event.data: s16le, interleaved L/R, 320 samples per channel.
                    # Forward to a bounded application queue; avoid blocking I/O.
                    if output is not None:
                        chunks.append(event.data)
                    if event.sample_offset % 16000 == 0:
                        print(f"PCM: {event.sample_offset / 16000:.2f}s", flush=True)
                elif isinstance(event, sdk.LiveAudioEnd):
                    print(f"Verified END: {event.sent_bytes} encoded bytes; {event.dropped_frames} dropped")
    if output is not None:
        # Publish only after verified END. Errors/cancellation produce no WAV.
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes(b"".join(chunks))
        print(f"Saved {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", required=True)
    parser.add_argument("--output", type=Path, help="Optional destination WAV")
    args = parser.parse_args()
    asyncio.run(main(args.address, args.output))
