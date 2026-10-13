# First Use

[English](https://github.com/ziloai/OpenZilo/wiki/First-Use) | [简体中文](https://github.com/ziloai/OpenZilo/wiki/First-Use-zh-CN)

Firmware: **V2.001.0002.0000** · Protocol: **v4** · Python SDK: **0.5.0**

## 1. Charge and check the ring

Use the charging accessory supplied for your ring. Red blinking indicates charging; steady green indicates a full charge. See [LED Indicators](https://github.com/ziloai/OpenZilo/wiki/LED-Indicators). Charge before testing recording, especially if the reported battery is below 20%.

## 2. Install the SDK

You need [uv](https://docs.astral.sh/uv/getting-started/installation/), Python 3.10+ (uv can install it), and a BLE adapter. Linux also requires BlueZ and Bluetooth access. Install `ffmpeg` and make it available on your PATH to convert recordings to WAV.

```bash
git clone https://github.com/ziloai/OpenZilo.git
cd OpenZilo
uv sync
uv run openzilo scan --timeout 10
```

Identify your ring (advertised name: `Open Zilo`). Use the address or identifier returned by the scanner; its format varies by operating system. The address below is a placeholder. Close other applications connected to the ring.

```bash
uv run openzilo info --address AA:BB:CC:DD:EE:FF
```

Confirm the firmware version is `V2.001.0002.0000`. If it differs, check compatibility before using this guide. Each command connects for its operation; it does not keep a permanent session open.

## 3. Make a short recording

After startup the ring is in recording mode. Hold the button until green appears, say a short sentence, and release it. If you have already changed modes, use [Buttons and Modes](https://github.com/ziloai/OpenZilo/wiki/Buttons-and-Modes) to return to recording mode.

```bash
uv run openzilo audio-count --address AA:BB:CC:DD:EE:FF
```

Check that the count increased. Download index `0` to test the first stored recording (this is not necessarily the one you just recorded):

```bash
uv run openzilo audio-download --address AA:BB:CC:DD:EE:FF 0 first-recording.wav
```

Listen to the generated WAV. The raw recording is also saved. A raw `.bin` cannot be played by simply renaming it. If WAV conversion fails, check `ffmpeg`; retain the raw file for retrying conversion.

## 4. Try IMU data

Single-press to enter gesture mode from recording mode, then wait for the two blue pulses. Edit `ADDRESS` in `examples/imu_stream.py` to match your scan result and run:

```bash
uv run python examples/imu_stream.py
```

The ring must already be in gesture mode when this example starts. Move your hand and confirm batches arrive. A busy response means the prerequisites are not satisfied; check the mode and connection. Press Ctrl+C to stop. See the [SDK guide (简体中文)](https://github.com/ziloai/OpenZilo/blob/main/docs/python-sdk.zh-CN.md) for tap and button event APIs.

## If something does not work

- **Cannot scan / connect:** charge the ring, check Bluetooth permissions, and disconnect other clients.
- **No recording:** confirm recording mode and sufficient battery; check for the three red error pulses and available storage.
- **No IMU data:** confirm gesture mode and a successful streaming-start response; restart streaming after reconnecting.
- **Download succeeds but WAV fails:** check `ffmpeg`; keep the downloaded raw file.

Record your firmware version, SDK version, and reproduction steps when [reporting an issue](https://github.com/ziloai/OpenZilo/issues). Remove private recordings and device identifiers from public reports.
