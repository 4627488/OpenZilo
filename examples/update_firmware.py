# SPDX-License-Identifier: MPL-2.0
"""Update application firmware using an official, device-compatible package."""
import argparse
import asyncio
from pathlib import Path

import openzilo as sdk


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", required=True)
    parser.add_argument("--version", required=True, help="Target version from the release.")
    parser.add_argument("--sha256", required=True, help="SHA-256 from the official release.")
    parser.add_argument("--model", required=True, help="Compatible model from the release.")
    parser.add_argument("firmware", type=Path)
    args = parser.parse_args()
    data = args.firmware.read_bytes()
    # Stop recording and IMU streaming first; use this connection exclusively.
    async with sdk.OpenZiloClient(address=args.address) as ring:
        info = await sdk.update_firmware(
            ring, data, version=args.version, sha256=args.sha256,
            expected_model=args.model, progress=sdk.ProgressPrinter(prefix="OTA transfer"),
        )
        print(f"Verified after reboot: {info.firmware_version}")


if __name__ == "__main__":
    asyncio.run(main())
