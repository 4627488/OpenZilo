# Buttons and Modes

[English](https://github.com/ziloai/OpenZilo/wiki/Buttons-and-Modes) | [简体中文](https://github.com/ziloai/OpenZilo/wiki/Buttons-and-Modes-zh-CN)

Firmware: **V2.001.0002.0000** · Protocol: **v4** · Python SDK: **0.5.0**

The ring starts in **recording mode**. A successful single press switches between recording and gesture modes.

| Action | Recording mode | Gesture mode |
| --- | --- | --- |
| Single short press | Switch to gesture mode | Switch to recording mode |
| Double press of the button | Report a button double-press event; keep the current mode | Same |
| Press and hold | Start recording after about 0.3 seconds; release to finish and save | No recording action |
| Physical double tap detected by the IMU | IMU detection is inactive | Report a double-tap event while connected |

A short press is under about 0.2 seconds. Two short presses within the roughly 0.5-second double-click window count as a double press. A single press is therefore confirmed after a short delay. Wait for the blue mode-switch indication before continuing; rapid extra presses can be interpreted as a double press.

Mode changes can be ignored while recording or immediately after a long press. A single-press event confirms that a press was recognized, not that the mode changed. Both switch directions show the same blue indication. The SDK has no query / set-mode command.

## Recording

Hold the button until green appears, speak, then release it. Below 20% reported battery, the ring refuses to start a recording and shows the error indication. Charge first if recording fails with a low battery.

Recordings can be saved without a BLE connection. While connected, a completed recording can be sent automatically. If your application misses that transfer, query the stored recording count and download the file. Downloading does not clear the stored recordings; clearing all recordings is an explicit, irreversible operation.

When storage is full, new recording storage can fail. Back up recordings before clearing them; do not expect automatic replacement of older recordings.

## IMU and Tap Detection

Enter gesture mode and keep a BLE connection. The SDK can receive batch IMU data with `start_sensor_report()` and `wait_sensor_data()`. Use `stop_sensor_report()` to stop streaming; local tap detection can continue in gesture mode.

A physical double tap (`0x0701`) is distinct from pressing the button twice (`0x0703`). Receive physical double taps with `wait_sensor_double_tap_event()`. Waiting for this event does not require starting the raw-data stream.

Disconnection pauses local IMU capture and turns streaming off. Gesture mode can resume local capture after reconnection, but the application must start streaming again. Only one BLE client can connect at a time; disconnect a phone app before connecting a desktop script.
