# OpenZilo 使用与开发文档

[English](https://github.com/ziloai/OpenZilo/wiki/Home) | [简体中文](https://github.com/ziloai/OpenZilo/wiki/Home-zh-CN)

适用固件：**V2.001.0002.0000** · 协议：**v4** · Python SDK：**0.5.0**

了解如何使用戒指，并通过 OpenZilo SDK 开发应用。

## 使用戒指

- [首次使用](https://github.com/ziloai/OpenZilo/wiki/First-Use-zh-CN)：充电、连接、录音、下载与 IMU 数据。
- [按键与工作模式](https://github.com/ziloai/OpenZilo/wiki/Buttons-and-Modes-zh-CN)：录音、IMU、敲击检测与按键事件。
- [灯光说明](https://github.com/ziloai/OpenZilo/wiki/LED-Indicators-zh-CN)：颜色、节奏与处理方式。
- [固件升级](https://github.com/ziloai/OpenZilo/wiki/Firmware-Updates-zh-CN)：可用状态、兼容条件、升级与恢复。

## 开发接入

- [SDK 安装与示例](https://github.com/ziloai/OpenZilo/blob/main/README.zh-CN.md#快速开始)
- [Python SDK 手册](https://github.com/ziloai/OpenZilo/blob/main/docs/python-sdk.zh-CN.md)
- [BLE 协议参考](https://github.com/ziloai/OpenZilo/blob/main/docs/protocol.zh-CN.md)
- [架构与数据流](https://github.com/ziloai/OpenZilo/blob/main/docs/architecture.zh-CN.md)

## 兼容性与支持

本手册面向页首标注的固件版本，使用前请核对设备版本。仅凭硬件型号名称不能保证兼容；每次 OTA 发布需列出支持型号与起始版本。公开 SDK 覆盖录音、IMU、敲击检测和按键事件，当前源码也提供 OTA 升级 API 与命令行（可用状态见[固件升级](https://github.com/ziloai/OpenZilo/wiki/Firmware-Updates-zh-CN)）；目前没有公开 PPG API。

[反馈问题](https://github.com/ziloai/OpenZilo/issues) · [私下报告安全问题](https://github.com/ziloai/OpenZilo/blob/main/SECURITY.md) · [OpenZilo 官网](https://openzilo.com)
