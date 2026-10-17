# 完整固件：Ultra25.12 r7 — 2026-10-17

适用设备：NRadio-C2000MAX-Ultra。ImmortalWrt25.12-SNAPSHOT、Linux6.12.103、联发科闭源Wi-Fi8.3.1.2、巴龙WebUI3.0.2-r2。

本版将无线RX DMA恢复补丁954编入驱动，保留r6全部通用修复。原登录页、WPA2/WPA3、5G、网口、UPnP/IPv6、PCDN绕过、短信和媒体功能保持现有方案。

| 文件 | 用途 |
| --- | --- |
| `ultra-25.12-20261017-r7-nradio-c2000ultra-sysupgrade.bin` | 内核和完整根文件系统，供本项目Ultra TF系统升级。 |
| `ultra-25.12-20261017-r7-optional-packages.tar.gz` | 与本版对应的签名离线软件仓库。 |

布局兼容号2.0，根分区预留512MiB。完整安装步骤见[安装说明](../../docs/INSTALL.md)。r4/r5/r6用户可使用[配置保留升级包](../ultra-maintenance-20261017-1/README.md)。

## 本次集成

- 描述符异常经厂商SER异步队列请求恢复，30秒节流，不回填猜测的DMA地址或token。
- 检查DMA所有权之后补充读屏障；异常校验提前到拷贝缓冲分配之前。
- 内核与r6相同，原有NAPI空转、QoS及逐设备接收计数修复保留。

## 验证与出厂数据

同一驱动已在Ultra实机重启加载，双频无线、5G IPv4/IPv6、网页和后台复验通过。完整镜像完成板型、FIT/DTB、ABI、原登录页、r6差异、用户态、软件仓库和个人数据检查，记录见`VERIFICATION.json`。

本版完整镜像尚未刷写，整镜像启动和恢复出厂验收待完成，按预发布提供。公开镜像使用通用配置；个人配置、凭据、订阅、短信和媒体数据不进入产物。ROM内的通用修复在恢复出厂后保留。

离线仓库解压至`/overlay/ultra-packages/`，运行`ultra-package-feeds`和`opkg update`。
