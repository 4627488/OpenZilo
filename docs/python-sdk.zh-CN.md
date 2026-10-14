# OpenZilo Python SDK 使用手册

SDK 是 Python 包 `openzilo`（源码在 `src/openzilo/`），当前版本为 `0.5.0`。本手册面向固件 `V2.001.0002.0000`、协议 v4，列出本版本适用的类型、函数和使用示例。

## 文档导航

- [架构与数据流](architecture.zh-CN.md)：BLE 收包、录音传输、Speex 解码和 IMU 事件。
- [协议参考](protocol.zh-CN.md)：Python SDK 当前公开功能使用的通信协议字段表，供协议联调时查阅。

公开接口以 `openzilo.__all__` 为准，统一从 `import openzilo` 导入；下划线开头的子模块属于内部实现，可能随版本调整。协议字段和数据流分别在上述两份文档中说明。

## 接入前

协议 v4 存在不同固件实现，不能仅根据基础版本号假定功能一致：

- 旧单点 IMU 固件：`0x0601` 启动硬件采集和上报，`0x0603` 停止采集；未实现 SDK 所定义的 `0x0701`～`0x0704` 事件上报。不要先等待按键事件再启动 IMU。
- 手势固件：需要先进入手势模式，`0x0601`／`0x0603` 控制 BLE 上报；本地采集可继续供手势检测使用。下文动作事件定义仅适用于支持该功能的固件。

SDK 兼容 22 字节单点包和批量 IMU 包，都返回 `SensorDataBatch`。单点包的 `frame_count=1`。SDK 没有能力查询或模式切换命令，不会自动判断设备是否支持手势。

旧 Speex 固件录音保存后，设备可直接上报连续的 `0x0505`，前面没有 `0x0504` 文件信息。已连接的应用可用 `receive_auto_audio_file()` 接收；错过上报时再按文件索引下载。这是保存后的传输，不是边录边传。

支持 Opus 录音的新固件保存后只上报 `0x050A`，`receive_auto_audio_file()` 会据此主动下载，调用方式不变。新固件还支持实时录音：订阅后按键录音的数据直接经 BLE 发送，**不保存到设备 Flash**，见[实时接收录音](#实时接收录音)。

当前固件的部分录音失败路径没有错误响应。此时 SDK 仍报告 `TimeoutError`，不能据此断定是文件不存在还是设备忙碌。快速发送没有可靠的取消握手，取消 SDK 等待不表示设备已经停止发送。系统配置占位、手势识别、远程录音控制等能力不会由 SDK 模拟实现。

## 快速开始

### 安装与导入

安装后导入模块：

```python
import openzilo as sdk
```

下文用 `sdk` 作为 `openzilo` 的模块别名。

### 安装依赖

推荐用 [uv](https://docs.astral.sh/uv/) 管理环境。在本仓库中运行 `uv sync`，会创建 `.venv` 并按 `uv.lock` 安装 SDK 和 `bleak`；之后用 `uv run` 执行脚本：

```powershell
uv sync
uv run python examples/system_info.py
```

在自己的 uv 项目中引用 SDK：

```powershell
uv add git+https://github.com/ziloai/openzilo
```

不用 uv 时，在仓库目录执行 `python -m pip install -e .`，`bleak` 会作为依赖一起安装。

如果需要把戒指录音解码成 WAV，还需要安装 `ffmpeg`，并确保命令行可以执行：

```powershell
ffmpeg -version
```

只下载原始录音字节、不解码时，可以不安装 `ffmpeg`。

### 最小连接示例

把 `AA:BB:CC:DD:EE:FF` 替换成实际戒指 MAC 地址：

```python
import asyncio
import openzilo as sdk

ADDRESS = "AA:BB:CC:DD:EE:FF"


async def main() -> None:
    async with sdk.OpenZiloClient(address=ADDRESS) as ring:
        info = await sdk.get_system_info(ring)
        print(info)


if __name__ == "__main__":
    asyncio.run(main())
```

`ring` 是已经连接的 `OpenZiloClient` 对象。所有需要访问设备的高层函数都把它作为第一个参数，例如 `sdk.get_system_info(ring)`。

### BLE 写入分片与 0.3.x 迁移

SDK 向戒指的 NUS RX 特征值写入数据时固定按 20 字节分片，最后一片按实际剩余长度发送。该策略不需要调用方配置，也不会关闭 Windows、Bleak 或系统蓝牙栈的 MTU 协商。戒指发送给 SDK 的通知不限制为 20 字节，接收数据仍由 `PacketStream` 按协议包头重组。

从 `0.4.0` 开始，`NusClient` 不再接受 `write_chunk_size` 参数。使用 `0.3.x` 自定义传输的代码需要移除该参数：

```python
# 0.3.x 旧写法，不再支持
# transport = sdk.NusClient(address=ADDRESS, write_chunk_size=20)

# 0.4.0
transport = sdk.NusClient(address=ADDRESS)
ring = sdk.OpenZiloClient(transport=transport)
```

## 运行环境配置要求

### Python

- 推荐 Python `3.11` 或更新版本。
- SDK 使用 `asyncio`，所有 BLE 设备访问函数都需要在 `async def` 中通过 `await` 调用。
- PyCharm 中请确认运行脚本使用的是安装了 `bleak` 的同一个虚拟环境。

### Windows

- 推荐 Windows 10/11。
- 打开系统蓝牙，并确认没有其他程序独占连接戒指。
- 如果出现设备可以被其他设备扫描到、但本机连接失败，优先尝试关闭再打开蓝牙、断开其他 BLE 工具、重启戒指广播。

### Ubuntu/Linux

- 也需要安装 `bleak`。
- 通常还需要 BlueZ 蓝牙栈，并确保当前用户有访问蓝牙设备的权限。
- 如果扫描或连接权限异常，可先用系统蓝牙工具确认本机能看到该 MAC 地址。

### 音频解码

录音 `.bin` 是旧固件的 Speex 帧流，或新固件的 OP2C 双声道 Opus 文件。SDK 会保留原始 `.bin`，按内容识别编码，并借助 `ffmpeg` 解码为 `.wav`；格式说明见[录音文件格式](architecture.zh-CN.md#录音文件格式)。

```python
bundle = sdk.save_audio_bundle(file_index=0, data=raw_audio, output_dir="audio")
print(bundle.raw_path)
print(bundle.play_path)
```

如果缺少 `ffmpeg`，下载录音仍然可行，但解码会抛出 `SpeexDecoderUnavailable` 或 `OpusDecoderUnavailable`。

## 接口分层

| 层级 | 常用名称 | 说明 |
| --- | --- | --- |
| 连接会话 | `scan_rings()`、`connect_ring()`、`OpenZiloClient` | 扫描、连接、发送请求、等待设备上报 |
| 系统信息 | `get_system_info()`、`parse_system_info()` | 获取固件版本、时间、存储、电量、SN、CPUID、型号 |
| 校时服务 | `enable_time_sync()`、`send_time_response()` | 设备发出 `0x0401` 时自动或手动回复 `0x0402` |
| 六轴和事件 | `start_sensor_report()`、`wait_sensor_data()`、`wait_sensor_double_tap_event()` | 接收批量 IMU 数据、敲击和按键事件 |
| 日志 | `get_log_storage()`、`read_log_chunk()` | 获取日志空间信息并按偏移读取日志 |
| 录音接收与下载 | `receive_auto_audio_file()`、`receive_live_audio_file()`、`download_audio_file()` | 接收刚保存或实时发送的录音，或查询并下载指定录音 |
| 录音解码保存 | `save_audio_bundle()`、`decode_audio_to_wav()` | 保存原始录音并生成 WAV |
| 协议工具 | `encode_packet()`、`decode_packet()`、`PacketStream` | 调试协议包、CRC、二进制读写 |

## 推荐调用流程

### 读取系统信息

```text
connect -> get_system_info -> disconnect
```

```python
async with sdk.OpenZiloClient(address=ADDRESS) as ring:
    info = await sdk.get_system_info(ring)
```

### 自动校时

```text
connect -> enable_time_sync -> 保持连接
```

```python
async with sdk.OpenZiloClient(address=ADDRESS) as ring:
    sdk.enable_time_sync(ring)
    await asyncio.sleep(60)
```

### 下载并保存录音

```text
connect -> get_audio_file_count -> download_audio_file -> save_audio_bundle
```

```python
async with sdk.OpenZiloClient(address=ADDRESS) as ring:
    count = await sdk.get_audio_file_count(ring)
    if count:
        info, raw_audio = await sdk.download_audio_file(ring, file_index=0)
        bundle = sdk.save_audio_bundle(
            file_index=info.file_index,
            data=raw_audio,
            metadata={"record_time": info.record_time},
            output_dir="audio",
        )
        print(bundle.raw_path)
        print(bundle.play_path)
```

`download_audio_file()` 默认 `quick=True`，走设备主动推送链路。只有需要验证普通链路时才设置 `quick=False`。

### 接收并保存刚结束的录音

```text
connect -> receive_auto_audio_file 等待 -> 用户长按录音并松开
        -> 新固件上报 0x050A 后 SDK 下载 / 旧固件连续上报 0x0505 -> save_audio_bundle
```

```python
async with sdk.OpenZiloClient(address=ADDRESS) as ring:
    print("请长按戒指录音，完成后松开")
    file_index, raw_audio = await sdk.receive_auto_audio_file(
        ring,
        timeout_s=60.0,
    )
    bundle = sdk.save_audio_bundle(
        file_index=file_index,
        data=raw_audio,
        output_dir="audio",
    )
    print(bundle.raw_path)
    print(bundle.play_path)
```

旧固件的自动上报不会预先发送 `0x0504`，因此返回值不包含 `AudioFileInfo`。正常连续接收时 SDK 不发送额外命令；需要恢复时会在内部查询元数据，以校验文件索引并将结果限制为准确的 `data_size`。等待期间必须保持 BLE 连接，并且不能同时调用 `download_audio_file()` 或 `read_audio_frame()` 消费同一个 `0x0505` 队列。若连接建立过晚而错过主动上报，应查询录音数量后使用 `download_audio_file()` 重新下载。

### 实时接收录音

```text
connect -> receive_live_audio_file 订阅 -> 用户长按录音并松开
        -> 设备实时发送 Opus -> SDK 退订 -> save_audio_bundle
```

```python
async with sdk.OpenZiloClient(address=ADDRESS) as ring:
    recording = await sdk.receive_live_audio_file(
        ring,
        on_subscribed=lambda: print("请长按戒指录音，完成后松开"),
    )
    bundle = sdk.save_audio_bundle(
        file_index=0,
        data=recording.data,
        output_dir="audio",
    )
    print(bundle.play_path)
```

实时录音只适用于新固件，订阅期间的录音不保存到设备，断线或丢包后无法补回。等 `on_subscribed` 回调后再让用户录音。

### 接收批量 IMU 数据

```text
connect -> 仅手势固件需要预先进入手势模式
        -> start_sensor_report 成功（0x0601 -> 0x0602 error_code=0）
        -> wait_sensor_data loop（接收 0x0605）
        -> stop_sensor_report
```

下面示例适用于单点 IMU 固件；手势固件须预先进入手势模式。不要使用一次 `0x0704` 推断最终模式。

```python
async with sdk.OpenZiloClient(address=ADDRESS) as ring:
    start = await sdk.start_sensor_report(ring)
    print(start)
    try:
        for _ in range(10):
            batch = await sdk.wait_sensor_data(ring, timeout_s=5.0)
            for sample in batch.samples:
                print(batch.sequence_start, sample.timestamp_ms, sample.accel_x)
    finally:
        await sdk.stop_sensor_report(ring)
```

只有 `start_sensor_report()` 成功返回后才能开始循环调用 `wait_sensor_data()`。后者只等待下一批 `0x0605`，不会自动发送 `0x0601`，也不会启动本地 IMU。

## 固件升级

当前源码新增 `update_firmware()` 和 `ota-update`，尚待发布和实机验证；已安装的 SDK 0.5.0 不一定包含此接口。它们只处理应用固件升级，不升级 bootloader。升级包需来自官方发布说明，并明确兼容设备型号和起始版本。升级前备份重要录音，停止录音、下载与 IMU 上报，保持电量和连接稳定；调用期间该连接由升级操作独占。

```python
from pathlib import Path

async with sdk.OpenZiloClient(address=ADDRESS) as ring:
    info = await sdk.update_firmware(
        ring,
        Path("path/to/official-update.bin").read_bytes(),
        version="V2.001.0002.0000",
        sha256="SHA256_FROM_RELEASE",
        expected_model="MODEL_FROM_RELEASE",
        progress=lambda sent, total: print(f"Transferred: {sent}/{total}"),
    )
    print("重启后已确认版本：", info.firmware_version)
```

路径、SHA-256 和型号都是占位值，需替换为发布说明中的实际值。SDK 原样发送升级包，不解析其中的固件内容。完整可运行示例见 [update_firmware.py](../examples/update_firmware.py)。

| 参数 | 含义 |
| --- | --- |
| `client` / `firmware` | 已连接的客户端与完整升级包字节。 |
| `version` | 必填目标版本，须与升级包的完整运行版本一致，例如 `V2.001.0002.0000` 或 `V2.001.0002.0000-prod-1234abcd`；也接受 `-debug-8位十六进制哈希` 后缀。重启后精确匹配，不忽略后缀。设备已运行此版本时拒绝重复升级。 |
| `sha256=None` | 可选的 64 位十六进制 SHA-256；建议传入官方值。校验失败时不发送升级请求。 |
| `expected_model=None` | 可选型号，必须与设备信息中的 `model` 完全相同。仍需自行确认起始版本兼容。 |
| `progress=None` | 同步回调 `(sent, total)`，单位字节；只反映传输进度。设备请求续传时可能跳过已接收的前缀。 |
| `timeout_s=30.0` | 单次设备检查、传输或重连操作的超时。 |
| `total_timeout_s=600.0` | 前置设备检查和传输阶段的总上限。 |
| `reboot_timeout_s=90.0` | 传输确认之后，等待重启、重连和版本核验的总上限。 |

返回 `SystemInfo`，来源于设备重启并重连后的查询。SDK 核对设备身份与目标版本后才成功返回；**进度到达 100% 或蓝牙断开都不表示升级成功**。设备拒绝升级时抛出 `DeviceError`；超时、通信中断或异常响应分别通过 `TimeoutError`、`TransportError` 或 `ProtocolError` 报告。取消操作不会撤销设备已收到的升级包，失败后应重连读取版本确认状态。

官方发布信息、失败处理见 [Firmware Updates](../wiki/Firmware-Updates-zh-CN.md)。

## 公开数据类型

以下类型均可通过 `import openzilo as sdk` 后使用，例如 `sdk.SystemInfo`。本手册覆盖当前固件适用的接口；SDK 为旧设备保留的兼容接口不代表当前固件支持相应功能。

### 异常类型

```python
OpenZiloError
# SDK 异常基类。只想统一捕获 SDK 异常时捕获这个类型。

TransportError
# BLE 传输异常，例如未安装 bleak、找不到设备、连接失败、未连接时写入或等待期间连接断开。

ProtocolError
# 协议异常，例如包头、CRC、包体长度、字段解析不符合预期。

TimeoutError
# 请求在排队、写入或等待响应阶段超时，或等待主动上报超时。写入被中断后需重连。

DeviceError
error_code: int  # 设备返回的非 0 错误码。
# 设备明确返回错误时抛出，例如 busy、参数错误、文件不存在。

AudioDecodeError
# 录音数据无法解码为可播放 WAV，或 ffmpeg 30 秒内未完成。

SpeexDecoderUnavailable
# 缺少 ffmpeg 或自定义 Speex 解码器不可用。

OpusDecoderUnavailable
# 缺少 ffmpeg，无法解码 OP2C 录音。
```

### BLE 和协议类型

```python
BleDeviceInfo
name: str | None    # BLE 广播名称，可能为空。
address: str        # BLE MAC 地址。
rssi: int | None    # 信号强度；部分 bleak 后端可能不提供。

Packet
command: int        # 命令字，例如 0x0605。
body: bytes         # 包体，不包含协议头。
version: int        # 协议版本，当前通常为 4。
body_crc: int       # 包体 CRC16。

OpenZiloClient
# 高层 BLE 协议客户端。负责连接、收包重组、请求响应匹配和事件分发。

NusClient
# 底层 Nordic UART Service BLE 客户端。发送固定按 20 字节分片，
# 通常只在调试或自定义传输时直接使用。

PacketStream
# 将 BLE 分片拼成完整 Packet，适合协议调试。

BinaryReader
# 按网络字节序从 bytes 中读取 u8/u16/u32/i16/string_u16。

BinaryWriter
# 按网络字节序构建 bytes 包体。
```

### 系统和日志类型

```python
SystemInfo
firmware_version: str          # 固件版本。
system_time: int               # 设备侧系统时间戳。
audio_storage_total: int       # 录音存储总字节数。
audio_storage_available: int   # 录音存储剩余字节数。
battery_percent: int           # 电量百分比。
battery_charging: bool         # 是否正在充电。
sn: str                        # 设备序列号；设备未写入时可能为 unknown。
cpuid: str                     # 芯片 ID 字符串。
model: str                     # 设备型号。

LogStorageInfo
page_size: int   # 当前日志文件大小或页大小字段，按设备端返回解释。
total_len: int   # 日志最大可读长度。
```

### 录音类型

```python
AudioFileInfo
file_index: int    # 录音索引。
record_time: int   # 录音时间戳，由设备端保存。
data_size: int     # 录音原始数据字节数。

AudioDataFrame
file_index: int     # 录音索引。
frame_offset: int   # 本帧在录音数据中的起始偏移。
frame_size: int     # 本帧声明的数据长度。
is_end: bool        # 是否为最后一帧。
data: bytes         # 本帧录音数据。

PcmConfig
sample_rate: int = 16000  # WAV 输出采样率。
channels: int = 1         # WAV 输出声道数。
bit_depth: int = 16       # WAV 输出位深。

SpeexDecodeResult
pcm_bytes: bytes          # 解码后的 PCM 数据。
pcm_config: PcmConfig     # PCM 参数。
source_type: str          # 源数据类型，例如 packet-speex、ogg-speex。
source_extension: str     # 源数据建议扩展名。
packet_count: int         # Speex 包数量，无法统计时为 0。

PlayableAudio
bytes: bytes              # 可播放音频字节，通常是 WAV。
extension: str            # 建议扩展名。
mime: str                 # MIME 类型。
play_mode: str            # direct 或 speex-decode。
label: str                # 格式标签。
pcm_config: PcmConfig | None
source_type: str
source_extension: str
source_mime: str
description: str

AudioBundle
raw_path: Path            # 原始录音保存路径。
raw_file_name: str
play_path: Path           # 解码后可播放文件路径。
play_file_name: str
play_mode: str
format_label: str
play_description: str
pcm_summary: str
raw_size: int
play_size: int
source_type: str
source_extension: str

OpusDecodeResult
pcm_bytes: bytes          # 解码后的 16 kHz、双声道、16 bit PCM。
pcm_config: PcmConfig     # PCM 参数。
source_type: str          # 固定为 opus-stereo。
source_extension: str     # 固定为 op2c。
packet_count: int         # Opus 包数量。

AudioRecordResult
file_index: int           # 新固件 0x050A 上报的录音索引。

LiveAudioSubscription
enabled: bool             # 设备确认的实时录音订阅状态。

LiveAudioStart
session_id: int           # 实时录音会话。
record_time: int          # 录音时间戳，单位秒。
sample_rate: int          # 固定为 16000。
channels: int             # 固定为 2。
codec: int                # 固定为 3，表示 Opus。

LiveAudioData
session_id: int
sequence: int             # 包序号，从 0 开始。
byte_offset: int          # Opus 数据字节偏移，从 0 开始。
data: bytes               # 一个 20 ms 双声道 Opus 包。

LiveAudioEnd
error_code: int
session_id: int
produced_bytes: int       # 设备编码产生的 Opus 字节数。
sent_bytes: int           # 设备已发送的 Opus 字节数。
dropped_frames: int       # 设备丢弃的帧数。

LiveAudioRecording
start: LiveAudioStart
end: LiveAudioEnd
data: bytes               # 完整 OP2C 文件，可直接解码或保存。

ProgressPrinter
# 可作为 download_audio_file(progress=...) 的进度回调。
```

### 六轴和事件类型

```python
SensorStartInfo
sample_rate_hz: int    # 设备返回的采样率。
accel_range_g: int     # 加速度计量程。
gyro_range_dps: int    # 陀螺仪量程。

SensorStopInfo
# 停止六轴上报的成功结果；当前没有字段。

SensorDataSample
timestamp_ms: int      # 设备侧采样时间戳，单位 ms。
accel_x: int           # 加速度 X 轴原始值。
accel_y: int           # 加速度 Y 轴原始值。
accel_z: int           # 加速度 Z 轴原始值。
gyro_x: int            # 陀螺仪 X 轴原始值。
gyro_y: int            # 陀螺仪 Y 轴原始值。
gyro_z: int            # 陀螺仪 Z 轴原始值。

SensorDataBatch
sequence_start: int                    # 本批第一个采样点序号。
frame_count: int                       # 本批采样点数量。
sample_size: int                       # 单个采样点字节数，当前为 16。
samples: tuple[SensorDataSample, ...]  # 批量采样点；第 n 个样本序号为 sequence_start + n。

SensorDoubleTapEvent
timestamp_ms: int  # 普通双击事件时间戳。

SensorKeyDoublePressEvent
timestamp_ms: int  # 本固件发送秒级设备时间；SDK 保留此历史字段名。

SensorKeySinglePressEvent
timestamp_ms: int  # 本固件发送秒级设备时间；SDK 保留此历史字段名。
```

重连后应重新调用 `start_sensor_report()`。本地采集是否自动恢复取决于固件实现，不能从连接状态推断。

## 公开函数速查表

### 连接和系统

| 函数 | 签名 | 返回值 | 使用方式 |
| --- | --- | --- | --- |
| `scan_rings()` | `await scan_rings(address=None, timeout_s=25.0)` | `list[BleDeviceInfo]` | 扫描 BLE 设备，可按 MAC 地址过滤。 |
| `connect_ring()` | `await connect_ring(address, command_timeout_s=10.0, auto_time_sync=False)` | `OpenZiloClient` | 创建并连接客户端，调用方负责 `disconnect()`。 |
| `get_system_info()` | `await get_system_info(client, timeout_s=None)` | `SystemInfo` | 读取设备系统信息。 |
| `parse_system_info()` | `parse_system_info(body)` | `SystemInfo` | 解析 `0x0102` 包体，通常只用于测试或协议调试。 |
| `enable_time_sync()` | `enable_time_sync(client)` | `None` | 注册 `0x0401` 自动应答处理器。 |
| `send_time_response()` | `await send_time_response(client, request_time, response_time=None, send_time=None)` | `None` | 手动发送 `0x0402` 校时应答。 |
| `get_log_storage()` | `await get_log_storage(client, timeout_s=None)` | `LogStorageInfo` | 查询日志存储信息。 |
| `read_log_chunk()` | `await read_log_chunk(client, index, offset, size, timeout_s=None)` | `bytes` | 按日志索引、偏移、长度读取日志。 |

### 固件升级

| 函数 | 调用方式 | 返回 | 说明 |
| --- | --- | --- | --- |
| `update_firmware()` | `await update_firmware(client, firmware, version=..., sha256=..., expected_model=..., progress=..., timeout_s=30, total_timeout_s=600, reboot_timeout_s=90)` | `SystemInfo` | 上传官方应用升级包，等待重启并核验运行版本，见[固件升级](#固件升级)。 |

### 录音下载

| 函数 | 签名 | 返回值 | 使用方式 |
| --- | --- | --- | --- |
| `get_audio_file_count()` | `await get_audio_file_count(client, timeout_s=None)` | `int` | 查询设备中保存的录音数量。 |
| `get_audio_file_info()` | `await get_audio_file_info(client, file_index, timeout_s=None)` | `AudioFileInfo` | 普通链路低层接口，发送 `0x0503` 并等待 `0x0504`。 |
| `read_audio_frame()` | `await read_audio_frame(client, file_index, frame_offset, timeout_s=None)` | `AudioDataFrame` | 普通链路低层接口，发送 `0x0506` 并等待 `0x0505`。 |
| `end_audio_extract()` | `await end_audio_extract(client, file_index, timeout_s=None, ignore_timeout=True)` | `None` | 普通链路低层接口，发送 `0x0507` 并等待 `0x0508`。 |
| `download_audio_file()` | `await download_audio_file(client, file_index, progress=None, timeout_s=None, quick=True)` | `tuple[AudioFileInfo, bytes]` | 完整下载录音；默认 quick 链路。 |
| `receive_auto_audio_file()` | `await receive_auto_audio_file(client, timeout_s=None)` | `tuple[int, bytes]` | 新固件接收 `0x050A` 后自动下载；旧固件接收连续 `0x0505`。 |
| `wait_audio_record_result()` | `await wait_audio_record_result(client, timeout_s=None)` | `AudioRecordResult` | 只等待新固件的 `0x050A`，不下载。 |
| `set_live_audio_subscription()` | `await set_live_audio_subscription(client, enabled, timeout_s=None)` | `LiveAudioSubscription` | 低层接口，发送 `0x050D` 并等待 `0x050E`。 |
| `receive_live_audio_file()` | `await receive_live_audio_file(client, on_packet=None, on_subscribed=None, timeout_s=60.0, recording_timeout_s=70.0)` | `LiveAudioRecording` | 订阅并接收一段实时录音，结束后退订。 |
| `clear_audio_files()` | `await clear_audio_files(client, timeout_s=None)` | `None` | 删除设备内所有录音，属于破坏性操作。 |
| `parse_audio_file_info()` | `parse_audio_file_info(body)` | `AudioFileInfo` | 解析 `0x0504` 包体。 |
| `parse_audio_data_frame()` | `parse_audio_data_frame(body)` | `AudioDataFrame` | 解析 `0x0505` 包体。 |
| `parse_audio_record_result()` | `parse_audio_record_result(body)` | `AudioRecordResult` | 解析 `0x050A` 包体。 |
| `parse_live_audio_start()` | `parse_live_audio_start(body)` | `LiveAudioStart` | 解析 `0x050F` 包体。 |
| `parse_live_audio_data()` | `parse_live_audio_data(body)` | `LiveAudioData` | 解析 `0x0510` 包体。 |
| `parse_live_audio_end()` | `parse_live_audio_end(body)` | `LiveAudioEnd` | 解析 `0x0511` 包体。 |

### 录音解码和文件保存

| 函数 | 签名 | 返回值 | 使用方式 |
| --- | --- | --- | --- |
| `save_audio_bundle()` | `save_audio_bundle(file_index, data, metadata=None, output_path=None, output_dir=None, pcm_config=None, ...)` | `AudioBundle` | 保存原始录音并生成可播放文件。 |
| `decode_audio_to_wav()` | `decode_audio_to_wav(data, pcm_config=None, ...)` | `bytes` | 把录音字节解码成 WAV 字节。 |
| `build_playable_audio()` | `build_playable_audio(data, pcm_config=None, ...)` | `PlayableAudio` | 自动识别 WAV、OP2C 双声道 Opus 或 Speex，返回可播放音频对象。 |
| `build_wav_from_pcm()` | `build_wav_from_pcm(pcm_bytes, pcm_config=None)` | `bytes` | 给 PCM 数据封装 WAV 头。 |
| `decode_speex_to_pcm()` | `decode_speex_to_pcm(data, pcm_config=None, ...)` | `SpeexDecodeResult` | 把 Speex 数据解码成 PCM。 |
| `decode_opus_to_pcm()` | `decode_opus_to_pcm(data, ffmpeg_path="ffmpeg")` | `OpusDecodeResult` | 把 OP2C 录音解码成双声道 PCM。 |
| `parse_opus_recording()` | `parse_opus_recording(data)` | `list[bytes]` | 校验 OP2C 文件并取出 Opus 包。 |
| `build_opus_recording()` | `build_opus_recording(packets)` | `bytes` | 把 Opus 包封装成 OP2C 文件。 |
| `decode_ogg_speex_with_ffmpeg()` | `decode_ogg_speex_with_ffmpeg(ogg_bytes, pcm_config=None, ffmpeg_path="ffmpeg")` | `bytes` | 用 ffmpeg 解码 Ogg Speex 为 PCM。 |
| `parse_packetized_speex_stream()` | `parse_packetized_speex_stream(data, allow_framed_blocks=True)` | `list[bytes]` | 解析带长度字段的 Speex 包流。 |
| `split_raw_speex_packets()` | `split_raw_speex_packets(data, quality=3, bits_size=None)` | `list[bytes]` | 按 Speex 帧大小切分原始数据。 |
| `build_ogg_speex()` | `build_ogg_speex(packets, pcm_config=None)` | `bytes` | 把 Speex 包封装成 Ogg Speex。 |
| `normalize_decoded_speex_pcm()` | `normalize_decoded_speex_pcm(pcm, packet_count, pcm_config=None)` | `bytes` | 规范解码后 PCM 长度。 |
| `normalize_pcm_config()` | `normalize_pcm_config(config=None)` | `PcmConfig` | 规范 PCM 配置输入。 |
| `format_pcm_config()` | `format_pcm_config(config=None)` | `str` | 格式化 PCM 配置说明。 |
| `build_audio_bundle_paths()` | `build_audio_bundle_paths(file_index, metadata=None, output_path=None, output_dir=None)` | `tuple[Path, Path]` | 生成原始文件和播放文件路径。 |
| `build_base_name()` | `build_base_name(file_index, metadata=None)` | `str` | 生成录音文件基础名称。 |
| `is_wav()` | `is_wav(data)` | `bool` | 判断是否为 WAV。 |
| `is_ogg_speex()` | `is_ogg_speex(data)` | `bool` | 判断是否为 Ogg Speex。 |
| `pick_speex_mode()` | `pick_speex_mode(sample_rate)` | `int` | 根据采样率选择 Speex 模式。 |
| `pick_frame_size()` | `pick_frame_size(sample_rate)` | `int` | 根据采样率选择 PCM 帧采样数。 |
| `pick_bits_size()` | `pick_bits_size(quality)` | `int` | 根据质量参数估算 Speex 帧字节数。 |

### 六轴和事件

| 函数 | 签名 | 返回值 | 使用方式 |
| --- | --- | --- | --- |
| `start_sensor_report()` | `await start_sensor_report(client, timeout_s=None)` | `SensorStartInfo` | 发送 `0x0601`；单点固件直接启动采集，手势固件须预先进入手势模式。 |
| `wait_sensor_data()` | `await wait_sensor_data(client, timeout_s=None)` | `SensorDataBatch` | 在 `start_sensor_report()` 成功后等待一个 `0x0605` 单点或批量包；不会自动发送 `0x0601`。 |
| `stop_sensor_report()` | `await stop_sensor_report(client, timeout_s=None)` | `SensorStopInfo` | 发送 `0x0603`；单点固件同时停止采集，手势固件可保留本地采集。 |
| `parse_sensor_data_batch()` | `parse_sensor_data_batch(body)` | `SensorDataBatch` | 解析 `0x0605` 包体。 |
| `wait_sensor_double_tap_event()` | `await wait_sensor_double_tap_event(client, timeout_s=None)` | `SensorDoubleTapEvent` | 等待 `0x0701` 普通双击事件。 |
| `wait_sensor_key_double_press_event()` | `await wait_sensor_key_double_press_event(client, timeout_s=None)` | `SensorKeyDoublePressEvent` | 等待 `0x0703` 按键双击事件。 |
| `wait_sensor_key_single_press_event()` | `await wait_sensor_key_single_press_event(client, timeout_s=None)` | `SensorKeySinglePressEvent` | 等待 `0x0704` 按键单击事件。 |
| `parse_sensor_double_tap_event()` | `parse_sensor_double_tap_event(body)` | `SensorDoubleTapEvent` | 解析 `0x0701` 包体。 |
| `parse_sensor_key_double_press_event()` | `parse_sensor_key_double_press_event(body)` | `SensorKeyDoublePressEvent` | 解析 `0x0703` 包体。 |
| `parse_sensor_key_single_press_event()` | `parse_sensor_key_single_press_event(body)` | `SensorKeySinglePressEvent` | 严格解析 `0x0704` 的 4 字节时间戳包体。 |

### 协议工具

| 函数 | 签名 | 返回值 | 使用方式 |
| --- | --- | --- | --- |
| `encode_packet()` | `encode_packet(command, body=b"")` | `bytes` | 构造带协议头和 CRC 的完整包。 |
| `decode_packet()` | `decode_packet(data)` | `Packet` | 解析完整协议包。 |
| `crc16_compute()` | `crc16_compute(data, initial=0xFFFF)` | `int` | 计算协议 CRC16。 |

## API 详细说明

### `scan_rings()`

作用：扫描附近 BLE 设备，可按 MAC 地址过滤。

签名：

```python
devices = await scan_rings(address=None, timeout_s=25.0)
```

返回：`list[BleDeviceInfo]`

`timeout_s` 是本次扫描允许等待的最长时间，默认值为 25 秒；调用方可按需要显式传入其他正数。

常见异常：未安装 `bleak` 时抛出 `TransportError`。

示例：

```python
devices = await sdk.scan_rings(address="AA:BB:CC:DD:EE:FF")
print(devices)
```

### `connect_ring()`

作用：创建并连接 `OpenZiloClient`。

签名：

```python
ring = await connect_ring(
    address="AA:BB:CC:DD:EE:FF",
    command_timeout_s=10.0,
    auto_time_sync=False,
)
```

返回：已连接的 `OpenZiloClient`。

注意：使用该函数时需要手动 `await ring.disconnect()`。更推荐用 `async with OpenZiloClient(...)` 自动释放连接。

### `OpenZiloClient`

作用：高层连接对象。负责 BLE 连接、协议收包、命令请求、事件等待。

常用方式：

```python
async with sdk.OpenZiloClient(address=ADDRESS) as ring:
    packet = await ring.request(0x0101, 0x0102)
```

常用成员：

- `is_connected`：当前是否连接。
- `connect()` / `disconnect()`：手动连接和断开。
- `send_command(command, body=b"")`：只发送命令，不等待响应。
- `request(command, response_command, body=b"", timeout_s=None)`：发送并等待指定响应。
- `wait_for_command(command, timeout_s=None)`：等待设备主动上报或后续响应。
- `add_packet_handler(command, handler, queue_packets=True)`：注册异步或同步包处理器。设为 `False` 时独占该命令的接收，不再保留队列副本；不能与同命令的其他处理器或等待接口混用。处理器抛出的异常会记录到 `openzilo` 日志，不会影响其他包；断线时会取消未完成的异步处理器。
- `remove_packet_handler(command, handler)`：移除处理器。

接收队列每个命令默认最多 256 个包，可通过 `OpenZiloClient(receive_queue_size=...)` 调整。溢出会清理该命令的积压包，并通过等待接口报告 `ProtocolError`，不会将数据缺失当作成功。只使用回调时建议 `queue_packets=False`；处理器应尽快返回，异步处理器自行控制处理并发。

同一响应命令的 `request()` 会串行执行。录音下载、自动接收、逐帧读取和清空等高层操作不能竞争同一连接，冲突时立即抛出 `ProtocolError`。手动组合低层录音接口时，应用仍需管理整段会话。OTA 期间拒绝其他任务的普通命令，自动校时应答除外；开始 OTA 前应停止录音及 IMU。

普通下载失败或取消后会尽力发送结束命令，清理最多等待 2 秒，清理失败不覆盖原始异常。协议没有事务 ID，同命令超时后的迟到响应无法可靠归属；需要严格隔离时应重连后再发起新请求。

### `get_system_info()` 和 `parse_system_info()`

`get_system_info()` 读取设备系统信息；`parse_system_info()` 只解析 `0x0102` 包体，通常用于测试。

```python
info = await sdk.get_system_info(ring)
print(info.firmware_version, info.battery_percent)
```

返回：`SystemInfo`

常见异常：超时抛出 `TimeoutError`；设备返回错误码抛出 `DeviceError`。

### `enable_time_sync()` 和 `send_time_response()`

`enable_time_sync()` 注册自动校时处理器。设备发送 `0x0401` 后，SDK 自动回复 `0x0402`。

```python
sdk.enable_time_sync(ring)
```

`send_time_response()` 用于手动回复校时请求：

```python
await sdk.send_time_response(ring, request_time)
```

`request_time` 应来自设备 `0x0401` 包体。

### `get_log_storage()` 和 `read_log_chunk()`

```python
storage = await sdk.get_log_storage(ring)
chunk = await sdk.read_log_chunk(ring, index=0, offset=0, size=256)
print(chunk.decode("utf-8", errors="replace"))
```

`read_log_chunk()` 返回原始 `bytes`。调用方可以按 UTF-8 或设备端实际日志编码解码。

### 录音下载链路

SDK 支持两条录音提取链路：

| 链路 | 协议顺序 | SDK 调用 |
| --- | --- | --- |
| quick 链路 | `0x0509 -> 0x0504 -> 0x0505...`，缺帧时 `0x0506` 补帧 | `download_audio_file(..., quick=True)` |
| 普通链路 | `0x0503 -> 0x0504`，循环 `0x0506 -> 0x0505`，最后 `0x0507 -> 0x0508` | `download_audio_file(..., quick=False)` |
| 旧固件保存后自动上报 | 录音保存成功后直接连续 `0x0505...`；需要恢复时查询 `0x0504` 元数据，再用 `0x0506` 补帧 | `receive_auto_audio_file()` |
| 新固件保存后通知 | `0x050A` 后按普通链路下载 | `receive_auto_audio_file()` |
| 实时录音 | `0x050D -> 0x050E` 订阅，随后 `0x050F -> 0x0510... -> 0x0511` | `receive_live_audio_file()` |

普通链路低层函数 `get_audio_file_info()`、`read_audio_frame()`、`end_audio_extract()` 主要用于调试。

### `download_audio_file()`

作用：完整下载指定录音。

签名：

```python
info, raw_audio = await download_audio_file(
    client,
    file_index,
    progress=None,
    timeout_s=None,
    quick=True,
)
```

返回：`tuple[AudioFileInfo, bytes]`

示例：

```python
info, raw_audio = await sdk.download_audio_file(
    ring,
    file_index=0,
    progress=sdk.ProgressPrinter(prefix="audio"),
)
```

注意：`file_index` 从 `0` 开始。先用 `get_audio_file_count()` 查询数量，避免访问不存在的录音。

### `receive_auto_audio_file()`

作用：取得刚保存的完整录音。新固件收到 `0x050A` 后，SDK 主动普通下载并发送 `0x0507` 释放文件；旧固件接收主动 `0x0505`，仅在恢复时查询元数据。两种情况均返回原始文件，可交给 `save_audio_bundle()` 自动识别编码。

签名：

```python
file_index, raw_audio = await sdk.receive_auto_audio_file(
    ring,
    timeout_s=60.0,
)
```

参数：

- `client`：已连接的 `OpenZiloClient`，示例中为 `ring`。
- `timeout_s`：等待每次数据到达的最长秒数；为 `None` 时使用客户端的 `command_timeout_s`。

返回：`tuple[int, bytes]`

- 第一个值是 `0x050A` 或首个有效 `0x0505` 中的 `file_index`。
- 第二个值是按 `frame_offset` 拼接完成的原始录音字节，可直接传给 `save_audio_bundle()`。
- 旧固件自动上报不会预先携带 `0x0504`，因此函数不会返回 `AudioFileInfo`；恢复期间查询到的元数据只用于完整性校验和长度控制。

接收行为：

- 第一帧确定本次接收的 `file_index`，其他文件索引的帧不会混入结果。
- 重复和重叠数据会按偏移去除。
- 偏移出现缺口、首帧后等待超时或收到损坏帧时，SDK 先查询并校验文件索引和准确 `data_size`，再使用 `0x0506` 从当前期望偏移补传，最多重试 3 次。
- 正常连续数据收到 `is_end=True` 后返回；恢复数据严格按 `data_size` 裁剪，不会返回边界后的字节。

异常：

- 首帧未在超时时间内到达：`TimeoutError`。
- 偏移缺口经过 3 次补传仍无法恢复、元数据索引不一致或帧字段不合法：`ProtocolError`。
- 设备返回非 0 错误码：`DeviceError`。
- 调用开始时未连接或等待期间 BLE 断开：`TransportError`。

并发限制：不要与 `download_audio_file()`、`read_audio_frame()` 或其他直接等待 `0x0505` 的代码同时运行。这些函数会消费同一个命令队列，可能互相取走数据。若 BLE 连接建立得太晚而错过自动上报，使用 `get_audio_file_count()` 和 `download_audio_file()` 重新下载。

保存示例：

```python
file_index, raw_audio = await sdk.receive_auto_audio_file(ring, timeout_s=60.0)
bundle = sdk.save_audio_bundle(
    file_index=file_index,
    data=raw_audio,
    output_dir="audio",
)
```

### `receive_live_audio_file()`

作用：订阅实时录音，接收用户按键录下的一段音频，然后退订。仅适用于新固件。

签名：

```python
recording = await sdk.receive_live_audio_file(
    ring,
    on_packet=None,
    on_subscribed=None,
    timeout_s=60.0,
    recording_timeout_s=70.0,
)
```

参数：

- `on_subscribed`：设备确认订阅后调用，适合提示用户开始录音。
- `on_packet`：每收到一个校验通过的 `LiveAudioData` 调用一次。它是原始 Opus 包，整段是否完整要等函数返回才能确定。
- `timeout_s`：订阅和等待录音开始的最长秒数。
- `recording_timeout_s`：从开始到结束的总上限；两个包之间最多等待 5 秒。

两个回调可以是同步函数或协程，应尽快返回，否则会拖慢接收。

返回：`LiveAudioRecording`，其中 `data` 是完整 OP2C 文件，可直接传给 `save_audio_bundle()` 或 `decode_audio_to_wav()`。

异常：

- 订阅被拒绝（例如 ATT MTU 不足）或结束包带错误码：`DeviceError`。
- 会话、序号、偏移不连续，结束包计数不符或设备报告丢帧：`ProtocolError`。
- 等待期间 BLE 断开：`TransportError`。

注意：

- 订阅期间的录音**不保存到设备 Flash**，失败后无法从设备补回。
- 函数退出时会尝试退订，包括出错和取消的情况。录音完整但退订失败时仍返回录音，并在 `openzilo` 日志记录警告；此时请断开重连，再做下载或固件升级。
- 订阅时不能与下载、`receive_auto_audio_file()` 或固件升级同时运行。

低层的 `set_live_audio_subscription(client, enabled)` 只负责开关订阅，需要自行处理 `0x050F`～`0x0511`。关闭订阅会中止正在发送的实时录音；断线后订阅自动失效。

### `clear_audio_files()`

作用：删除设备内所有录音。

```python
await sdk.clear_audio_files(ring)
```

这是破坏性操作。建议业务代码增加二次确认或环境变量保护。

### `save_audio_bundle()`

作用：保存原始录音，并尝试生成可播放 WAV。

```python
bundle = sdk.save_audio_bundle(
    file_index=0,
    data=raw_audio,
    metadata={"record_time": info.record_time},
    output_dir="audio",
)
print(bundle.raw_path)
print(bundle.play_path)
```

返回：`AudioBundle`

常见异常：缺少 `ffmpeg` 或解码失败时抛出 `SpeexDecoderUnavailable` / `OpusDecoderUnavailable` / `AudioDecodeError`。

### 录音解码辅助函数

- `decode_audio_to_wav()`：返回 WAV 字节，适合自己管理文件保存。
- `build_playable_audio()`：返回 `PlayableAudio`，包含字节、扩展名、MIME、解码说明。
- `decode_speex_to_pcm()`、`decode_opus_to_pcm()`：返回 PCM 解码结果，适合需要进一步处理 PCM 的场景。
- `parse_opus_recording()`、`build_opus_recording()`：OP2C 文件处理工具。
- `build_wav_from_pcm()`：只负责给 PCM 包 WAV 头。
- `decode_ogg_speex_with_ffmpeg()`：底层 ffmpeg 调用。
- `parse_packetized_speex_stream()`、`split_raw_speex_packets()`、`build_ogg_speex()`：Speex 包处理工具。
- `normalize_decoded_speex_pcm()`：修正解码后 PCM 长度。
- `normalize_pcm_config()`、`format_pcm_config()`：统一和展示 PCM 配置。
- `build_audio_bundle_paths()`、`build_base_name()`：生成保存路径和基础文件名。
- `is_wav()`、`is_ogg_speex()`：格式探测。
- `pick_speex_mode()`、`pick_frame_size()`、`pick_bits_size()`：Speex 参数推导。

`parse_packetized_speex_stream()` 这个公开底层函数还支持 1026 字节外层分块输入；高层 `decode_speex_to_pcm()`、`build_playable_audio()`、`decode_audio_to_wav()` 和 `save_audio_bundle()` 默认 `allow_framed_blocks=False`。处理这种兼容输入时，可显式设置 `allow_framed_blocks=True`。

### 六轴数据

设备端有录音模式和手势模式。六轴本地采集由手势模式维护：设备启动时默认是录音模式，此时 IMU 被关闭，调用 `start_sensor_report()` 会收到错误码 `2`，SDK 将其转换为 `DeviceError(error_code=2)`。

进入手势模式并保持 BLE 连接后，本地 IMU 开始采集；未连接时采集等待连接恢复：

- `0x0601` 在手势模式下确保采集开启，并启动 `0x0605` BLE 实时上报。从停止状态开启时，`sequence_start` 从 `0` 计数；重复开启已经运行的上报不会重置序号。
- `0x0603` 只关闭实时上报开关，不停止手势模式本地使用的 IMU 采集。
- BLE 连接断开时，设备会自动关闭实时上报开关。
- 采样率取决于设备配置，业务代码必须以 `start_sensor_report()` 返回的 `SensorStartInfo.sample_rate_hz` 为准。

获得实时数据的完整前置顺序是：进入手势模式，让本地 IMU 启动；调用 `start_sensor_report()` 并确认其成功返回；然后才能循环调用 `wait_sensor_data()`。`wait_sensor_data()` 不发送 `0x0601`，也不会尝试切换设备模式或启动 IMU。

设备端当前 `0x0605` 包体：

```text
error_code: u16
sequence_start: u32
frame_count: u16
sample_size: u16
samples: frame_count * sample_size
```

每个 sample 当前固定 `16` 字节：

```text
timestamp_ms: u32
accel_x: i16
accel_y: i16
accel_z: i16
gyro_x: i16
gyro_y: i16
gyro_z: i16
```

调用方式：

```python
# 前提：设备已经处于手势模式，本地 IMU 采集已开启。
start = await sdk.start_sensor_report(ring)  # 成功返回后才会有 0x0605
print(start.sample_rate_hz)
try:
    batch = await sdk.wait_sensor_data(ring, timeout_s=5.0)
    for index, sample in enumerate(batch.samples):
        sequence = batch.sequence_start + index
        print(sequence, sample.timestamp_ms, sample.accel_x, sample.gyro_x)
finally:
    await sdk.stop_sensor_report(ring)
```

### 动作事件

`0x0701` 普通双击：

该事件来自六轴双击算法。需要处于手势模式并保持 BLE 连接。等待该事件不要求先调用 `start_sensor_report()`。

```python
event = await sdk.wait_sensor_double_tap_event(ring, timeout_s=30.0)
print(event.timestamp_ms)
```

`0x0703` 按键双击：

按键双击是排他事件。双击成立时只上报 `0x0703`，不会再产生对应的 `0x0704`，也不会切换录音/手势模式。

```python
event = await sdk.wait_sensor_key_double_press_event(ring, timeout_s=30.0)
print(event.timestamp_ms)
```

`0x0704` 按键单击：

```python
event = await sdk.wait_sensor_key_single_press_event(ring, timeout_s=30.0)
print(event.timestamp_ms)
```

设备确认单击后会尝试在录音模式和手势模式之间切换，同时上报 `0x0704`。由于需要先排除双击，事件会在双击判定窗口结束后到达。事件包体只有时间戳，不包含切换后的模式；设备忙碌或处于长按收尾阶段时，即使收到 `0x0704`，也不能据此断言模式已经切换成功。

#### `wait_sensor_key_single_press_event()`

```python
event = await sdk.wait_sensor_key_single_press_event(
    ring,
    timeout_s=30.0,
)
```

- 作用：等待设备主动上报的 `0x0704` 按键单击事件。
- `ring`：已经连接的 `OpenZiloClient`。
- `timeout_s`：最长等待秒数；为 `None` 时使用客户端的 `command_timeout_s`。
- 返回值：`SensorKeySinglePressEvent`，其中 `timestamp_ms` 在本固件中是秒级设备时间，名称沿用 SDK 历史字段。
- 异常：等待超时抛出 SDK 的 `TimeoutError`；收到损坏包时可能抛出 `ProtocolError`。

#### `parse_sensor_key_single_press_event()`

```python
event = sdk.parse_sensor_key_single_press_event(body)
```

- 作用：解析已经去掉 11 字节协议头的 `0x0704` 包体，通常只用于协议测试和自定义接收流程。
- `body`：必须恰好包含一个网络字节序的 `u32` 时间戳，共 4 字节。
- 返回值：`SensorKeySinglePressEvent`。
- 异常：包体不足 4 字节或存在多余字节时抛出 `ProtocolError`。

### 协议调试工具

通常业务代码不需要直接使用这些工具。

```python
packet_bytes = sdk.encode_packet(0x0101)
packet = sdk.decode_packet(packet_bytes)
crc = sdk.crc16_compute(packet.body)
```

`PacketStream` 可用于把 BLE 分片重组成完整包：

```python
stream = sdk.PacketStream()
for packet in stream.feed(chunk):
    print(packet.command, packet.body)
```

`BinaryReader` 和 `BinaryWriter` 用于解析或构造协议包体：

```python
body = sdk.BinaryWriter().u16(0).u32(0).build()
reader = sdk.BinaryReader(body)
error_code = reader.u16()
```

## 完整业务示例

### 读取信息、下载第一条录音、保存文件

```python
import asyncio
import openzilo as sdk

ADDRESS = "AA:BB:CC:DD:EE:FF"


async def main() -> None:
    async with sdk.OpenZiloClient(address=ADDRESS) as ring:
        sdk.enable_time_sync(ring)

        info = await sdk.get_system_info(ring)
        print("system:", info)

        count = await sdk.get_audio_file_count(ring)
        print("audio count:", count)
        if count == 0:
            return

        audio_info, raw_audio = await sdk.download_audio_file(
            ring,
            file_index=0,
            progress=sdk.ProgressPrinter(prefix="audio"),
        )

    bundle = sdk.save_audio_bundle(
        file_index=audio_info.file_index,
        data=raw_audio,
        metadata={"record_time": audio_info.record_time},
        output_dir="audio",
    )
    print("raw:", bundle.raw_path)
    print("play:", bundle.play_path)


if __name__ == "__main__":
    asyncio.run(main())
```

### 接收 10 批 IMU 数据

以下示例假设设备已经处于手势模式。请先通过按键进入手势模式，再调用 `start_sensor_report()`；单击事件本身不能确认最终模式。旧单点固件无需此模式前置条件。

```python
import asyncio
import openzilo as sdk

ADDRESS = "AA:BB:CC:DD:EE:FF"


async def main() -> None:
    async with sdk.OpenZiloClient(address=ADDRESS) as ring:
        await sdk.start_sensor_report(ring)
        try:
            for _ in range(10):
                batch = await sdk.wait_sensor_data(ring, timeout_s=5.0)
                print("batch:", batch.sequence_start, batch.frame_count)
                for sample in batch.samples:
                    print(sample.timestamp_ms, sample.accel_x, sample.gyro_x)
        finally:
            await sdk.stop_sensor_report(ring)


if __name__ == "__main__":
    asyncio.run(main())
```

### 保存 `0x0605` 到 TXT

以下示例同样要求设备处于手势模式；`0601` 开启实时上报，不会替业务代码切换设备模式。

```python
import asyncio
import openzilo as sdk

ADDRESS = "AA:BB:CC:DD:EE:FF"


async def main() -> None:
    async with sdk.OpenZiloClient(address=ADDRESS) as ring:
        await sdk.start_sensor_report(ring)
        try:
            with open("imu_0605.txt", "w", encoding="utf-8") as f:
                for _ in range(20):
                    batch = await sdk.wait_sensor_data(ring, timeout_s=5.0)
                    for i, sample in enumerate(batch.samples):
                        seq = batch.sequence_start + i
                        f.write(
                            f"{seq},{sample.timestamp_ms},"
                            f"{sample.accel_x},{sample.accel_y},{sample.accel_z},"
                            f"{sample.gyro_x},{sample.gyro_y},{sample.gyro_z}\n"
                        )
        finally:
            await sdk.stop_sensor_report(ring)


if __name__ == "__main__":
    asyncio.run(main())
```

## 命令行调用

`openzilo` 包也带有简单 CLI，适合调试：

```powershell
uv run openzilo scan --address AA:BB:CC:DD:EE:FF
uv run openzilo connect --address AA:BB:CC:DD:EE:FF
uv run openzilo info --address AA:BB:CC:DD:EE:FF
uv run openzilo audio-count --address AA:BB:CC:DD:EE:FF
uv run openzilo audio-download --address AA:BB:CC:DD:EE:FF 0 audio
uv run openzilo audio-receive --address AA:BB:CC:DD:EE:FF audio
uv run openzilo audio-live --address AA:BB:CC:DD:EE:FF audio
uv run openzilo time-sync --address AA:BB:CC:DD:EE:FF --seconds 60
```

升级命令（需先替换占位值并完成[升级准备](#固件升级)）：

```powershell
uv run openzilo ota-update --address "DEVICE_ADDRESS" "path/to/official-update.bin" --version V2.001.0002.0000 --sha256 "SHA256_FROM_RELEASE" --model "MODEL_FROM_RELEASE"
```

可用 `--timeout`、`--total-timeout` 和 `--reboot-timeout` 调整超时，默认分别为 30、600 和 90 秒。

CLI 不提供按时长自动采集 IMU 的命令；六轴数据请在业务脚本中调用 `start_sensor_report()`、`wait_sensor_data()`、`stop_sensor_report()`。

## 常见问题

### `TransportError: Install bleak to use BLE transport`

当前 Python 环境没有安装 SDK 的依赖。通常是没有通过 `uv run` 运行脚本，或者用的不是 `uv sync` 创建的环境。在仓库目录执行：

```powershell
uv sync
uv run python your_script.py
```

### 扫描不到设备或连接失败

- SDK 现在按 MAC 地址筛选，不依赖设备名。
- 确认戒指正在广播，且没有被其他程序保持连接。
- Windows 上可以尝试关闭再打开蓝牙适配器。
- PyCharm 中确认解释器和安装依赖的虚拟环境一致。

### `Timed out waiting for command ...`

表示指定响应或事件没有在超时时间内到达。常见原因：

- 设备忙，例如正在录音、写 Flash、传输大文件。
- 业务代码同时发起多个命令请求，导致响应被其他流程消费。
- 设备模式不符合事件触发条件，例如在录音模式等待 `0x0702`。

建议同一连接上同一时间只发起一个“命令-响应”类请求。

### `receive_auto_audio_file()` 等待超时

首帧超时表示 SDK 在限定时间内没有收到录音保存后的 `0x050A` 或主动上报的 `0x0505`。确认调用期间 BLE 始终连接，并在开始等待后再让用户长按录音、松开。若程序连接过晚，设备可能已经发送完毕，此时应调用 `get_audio_file_count()` 查询文件，再用 `download_audio_file()` 重新下载。

不要让 `receive_auto_audio_file()` 与 `download_audio_file()`、`read_audio_frame()` 或手工 `wait_for_command(0x0505)` 并发运行；它们消费同一个 `0x0505` 队列，可能造成某个接收流程超时或出现偏移缺口。

### `start_sensor_report()` 返回设备忙碌

设备启动时默认处于录音模式，该模式会关闭并阻止 IMU 采集，所以 `0x0601` 会返回错误码 `2`。先让用户通过有效按键单击切换到手势模式，再调用 `start_sensor_report()`；只有函数成功返回后才能开始调用 `wait_sensor_data()`。`0x0704` 只确认单击事件，不返回当前模式；如果程序不是从设备刚启动的已知状态开始，需结合设备状态提示确认当前模式。

### 录音可以下载但不能解码

确认安装了 `ffmpeg`，并且命令行能执行 `ffmpeg -version`。如果只需要保存原始录音，可以直接保留 `download_audio_file()` 返回的 `bytes` 或 `save_audio_bundle()` 生成的 raw 文件。

### `clear_audio_files()` 为什么危险

该函数会删除设备保存的所有录音，成功后无法通过 SDK 恢复。业务代码应把它放在明确的维护或测试入口中，不要在普通启动流程里自动调用。
