# 首次使用

[English](https://github.com/ziloai/OpenZilo/wiki/First-Use) | [简体中文](https://github.com/ziloai/OpenZilo/wiki/First-Use-zh-CN)

适用固件：**V2.001.0002.0000** · 协议：**v4** · Python SDK：**0.5.0**

## 1. 充电并检查戒指

使用戒指配套的充电附件。红灯闪烁表示充电中，充满时绿灯常亮，详见[灯光说明](https://github.com/ziloai/OpenZilo/wiki/LED-Indicators-zh-CN)。测试录音前先充电，尤其是报告电量低于 20% 时。

## 2. 安装 SDK

需要 Python 3.10+ 和 BLE 适配器；Linux 还需 BlueZ 与蓝牙访问权限。录音转 WAV 需要安装 `ffmpeg`，并确保可从命令行执行。

```bash
git clone https://github.com/ziloai/OpenZilo.git
cd OpenZilo
python -m pip install -e .
python -m openzilo scan --timeout 10
```

识别广播名为 `Open Zilo` 的戒指，使用扫描返回的地址或设备标识；不同操作系统的格式可能不同。下面的地址只是占位符。关闭其他正在连接戒指的应用。

```bash
python -m openzilo info --address AA:BB:CC:DD:EE:FF
```

确认固件版本为 `V2.001.0002.0000`。版本不同请先核对兼容性。每条命令只在执行期间连接设备，不会留下永久连接。

## 3. 录制一段短音频

戒指启动后默认处于录音模式。按住按键，看到绿灯后说一句话，松开结束。如果之前切换过模式，请按[按键与工作模式](https://github.com/ziloai/OpenZilo/wiki/Buttons-and-Modes-zh-CN)返回录音模式。

```bash
python -m openzilo audio-count --address AA:BB:CC:DD:EE:FF
```

检查录音数量是否增加。使用索引 `0` 下载第一条已存录音进行测试；它不一定是刚录制的那条：

```bash
python -m openzilo audio-download --address AA:BB:CC:DD:EE:FF 0 first-recording.wav
```

播放生成的 WAV，原始录音也会保存。原始 `.bin` 不能通过改扩展名直接播放。WAV 转换失败时请检查 `ffmpeg`，保留原始文件以便重新转换。

## 4. 尝试 IMU 数据

从录音模式短按一次进入手势模式，等待蓝灯闪两次。把 `examples/imu_stream.py` 中的 `ADDRESS` 改成扫描得到的设备标识，然后运行：

```bash
python examples/imu_stream.py
```

运行前设备需已处于手势模式。移动手部，确认收到批量数据。若返回设备忙碌，请检查模式和连接；按 Ctrl+C 停止。敲击与按键事件 API 见 [SDK 手册](https://github.com/ziloai/OpenZilo/blob/main/docs/python-sdk.zh-CN.md)。

## 遇到问题

- **扫描不到／无法连接**：先充电，检查蓝牙权限，断开其他客户端。
- **无法录音**：确认录音模式、电量和剩余空间，留意红灯快闪三次的错误提示。
- **没有 IMU 数据**：确认手势模式和开始上报的成功响应；重连后需重新开启上报。
- **下载成功但无法生成 WAV**：检查 `ffmpeg`，保留已下载的原始录音。

[反馈问题](https://github.com/ziloai/OpenZilo/issues)时请记录固件版本、SDK 版本与复现步骤，公开反馈前移除私人录音和设备标识。
