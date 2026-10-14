# SPDX-License-Identifier: MPL-2.0
"""Receive one live recording and save its raw and playable forms."""

import asyncio

import openzilo as sdk


ADDRESS = "AA:BB:CC:DD:EE:FF"


async def main() -> None:
    async with sdk.OpenZiloClient(address=ADDRESS) as ring:
        recording = await sdk.receive_live_audio_file(
            ring,
            on_subscribed=lambda: print("Hold the ring button to record; release to finish."),
        )
    bundle = sdk.save_audio_bundle(
        file_index=0,
        data=recording.data,
        metadata={"record_time": recording.start.record_time},
        output_dir="audio",
    )
    print(f"raw: {bundle.raw_path}")
    print(f"playable: {bundle.play_path}")


if __name__ == "__main__":
    asyncio.run(main())
