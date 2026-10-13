# 固件升级

[English](https://github.com/ziloai/OpenZilo/wiki/Firmware-Updates) | [简体中文](https://github.com/ziloai/OpenZilo/wiki/Firmware-Updates-zh-CN)

适用固件：**V2.001.0002.0000** · 协议：**v4** · Python SDK：**0.5.0**

## 可用状态

本说明面向固件 `V2.001.0002.0000`，版本号本身不代表升级包已经提供。请仅使用官方发布说明明确指定、与硬件匹配的升级包和升级工具。

当前源码新增 `update_firmware()` 和 `ota-update`，用于应用固件升级，尚待发布和实机验证。页首 SDK 版本不代表已安装的 0.5.0 包包含此功能；可通过 `python -m openzilo ota-update --help` 检查。实际升级仍需官方提供与设备兼容的升级包。

## 官方升级发布后

1. 阅读支持型号、可升级的起始版本、已知问题和录音保留说明。设备不在支持列表时，请先联系支持。
2. 备份重要录音，确保电量充足、连接稳定，并停止录音与 IMU 数据流。升级工具如有电量要求，以其要求为准。
3. 下载官方用户升级包，核对公开的 SHA-256 校验值。校验值用于检查下载内容，不代表设备兼容性已确认。
4. 打开该版本指定的升级工具，选择戒指和升级包，按提示操作。保持设备靠近，避免中断供电或蓝牙。
5. 工具提示完成后重新连接，读取固件版本，再测试一段短录音和 IMU 数据，确认正常后继续使用。

## SDK 命令

在已审阅的 SDK 源码目录运行 `python -m pip install -e .` 安装。完成上面的准备后执行：

```bash
python -m openzilo ota-update --address "DEVICE_ADDRESS" "path/to/official-update.bin" --version V2.001.0002.0000 --sha256 "SHA256_FROM_RELEASE" --model "MODEL_FROM_RELEASE"
```

替换设备标识、文件路径、校验值和型号；文件名只是占位示例，不代表已有下载附件。`--version` 必须与升级包发布说明一致。可选参数 `--sha256` 和 `--model` 分别检查文件内容与已连接设备的型号，不代表已确认起始固件版本兼容。

SDK 原样传送升级包，按戒指请求发送分片，等待重启并重连，核对设备身份和运行版本。**传输 100% 不等于安装成功**；只有重启后读到目标版本才报告成功。SDK 不升级 bootloader，也不会自动下载固件包。

超时参数以秒计：`--timeout 30` 为单次操作上限，`--total-timeout 600` 为前置检查和传输总上限，`--reboot-timeout 90` 为重启与核验总上限。Python 调用见 [SDK 手册](https://github.com/ziloai/OpenZilo/blob/main/docs/python-sdk.zh-CN.md#固件升级)及[示例](https://github.com/ziloai/OpenZilo/blob/main/examples/update_firmware.py)。

## 升级失败

超时、断线或取消表示安装结果尚未确认；取消客户端不会撤销戒指已经收到的升级包。重连后先读取运行版本，再决定是否重试。记录工具错误和设备当前版本。若能重新连接，按工具说明重试；无法连接时请[联系支持](mailto:openzilo@ziloring.com)。除非发布说明明确确认，否则不要假设支持自动回滚、降级或升级后录音一定保留。

## 版本发布信息

公开固件下载如有提供，其用途是设备升级。发布说明应包含目标型号、版本、可升级的起始版本、配套工具、校验值、已知问题和恢复联系方式。下载位置由官方发布说明提供。
