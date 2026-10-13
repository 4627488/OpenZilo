# Firmware Updates

[English](https://github.com/ziloai/OpenZilo/wiki/Firmware-Updates) | [简体中文](https://github.com/ziloai/OpenZilo/wiki/Firmware-Updates-zh-CN)

Firmware: **V2.001.0002.0000** · Protocol: **v4** · Python SDK: **0.5.0**

## Availability

This guide targets firmware `V2.001.0002.0000`; the version label does not by itself mean an update package is available. Use only a package and updater explicitly provided for your hardware in an official release announcement.

This checkout adds `update_firmware()` and `ota-update` for application firmware updates. The addition is pending release and hardware validation; the SDK version label above does not mean an already installed 0.5.0 package includes it. Check `uv run openzilo ota-update --help` in your installation. An official compatible update package is still required.

## When an official update is available

1. Read its supported models, compatible starting versions, known issues, and recording-data retention policy. If your device is not listed, contact support before updating.
2. Back up important recordings. Ensure sufficient battery, a stable connection, and that recording / IMU streaming has stopped. Follow any battery requirement specified by the updater.
3. Download the official user update package and verify its published SHA-256 checksum. A checksum verifies the downloaded bytes, not device compatibility.
4. Open the updater named in that release, select the ring and package, and follow its progress. Keep the devices nearby and avoid interrupting power or Bluetooth.
5. After the updater reports completion, reconnect and read the firmware version. Verify a short recording and IMU capture before normal use.

## SDK command

Run `uv sync` in the reviewed SDK checkout. After completing the preparation above, run:

```bash
uv run openzilo ota-update --address "DEVICE_ADDRESS" "path/to/official-update.bin" --version V2.001.0002.0000 --sha256 "SHA256_FROM_RELEASE" --model "MODEL_FROM_RELEASE"
```

Replace the address, file path, checksum, and model with the actual values. The file name is a placeholder, not a published asset. `--version` must match the package's release. The optional `--sha256` and `--model` check the package bytes and connected model respectively; they do not establish compatibility with the starting firmware version.

The SDK sends the package unchanged, follows the ring's chunk requests, waits for reboot, reconnects, and checks the device identity and running firmware version. **100% transfer is not installation success.** Success is reported only after the target version is read back. The SDK does not update the bootloader or automatically download a package.

Timeouts are `--timeout 30` per operation, `--total-timeout 600` for preflight and transfer, and `--reboot-timeout 90` for reboot and verification, in seconds. Python integration is shown in the [SDK guide](https://github.com/ziloai/OpenZilo/blob/main/docs/python-sdk.zh-CN.md#固件升级) and [example](https://github.com/ziloai/OpenZilo/blob/main/examples/update_firmware.py).

## If an update fails

A timeout, disconnect, or cancellation leaves installation unconfirmed; cancelling the client does not roll back a package already received by the ring. Read the running version after reconnecting before deciding whether to retry. Record the updater's error and the current device version. If the ring reconnects, follow the updater's retry instructions; if it does not, contact [support](mailto:openzilo@ziloring.com). Do not assume automatic rollback, downgrade support, or unchanged recordings unless the release explicitly confirms them.

## Release information

Any public firmware download is a device update package. Its release notes should identify the target model, version, compatible starting versions, supported updater, checksum, known issues, and recovery contact. The package location will be linked from the official release announcement.
