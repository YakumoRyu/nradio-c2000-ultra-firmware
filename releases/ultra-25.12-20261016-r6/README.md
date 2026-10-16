# 完整固件：Ultra25.12 r6 — 2026-10-16

适用设备：NRadio-C2000MAX-Ultra。基线为ImmortalWrt25.12-SNAPSHOT、Linux6.12.103、联发科闭源Wi-Fi8.3.1.2及巴龙WebUI3.0.2-r2。

本版在r5上集成运营商图标修复，原登录页、网口管理、5G、UPnP/IPv6、PCDN绕过、短信和媒体资源管理继续保留。

| 文件 | 用途 |
| --- | --- |
| `ultra-25.12-20261016-r6-nradio-c2000ultra-sysupgrade.bin` | 内核与完整根文件系统，供本项目Ultra TF系统升级。 |
| `ultra-25.12-20261016-r6-optional-packages.tar.gz` | 与本版对应的离线软件仓库。 |

布局兼容号2.0，根分区预留512MiB。安装步骤见[完整固件安装](../../docs/INSTALL.md)。r4/r5用户也可使用[累计维护升级包](../ultra-maintenance-20261016-2/README.md)。

## 本次集成

- 补齐移动、电信、广电图标，与原联通图标一同放入ROM。
- 图标解码后显示，加载失败隐藏，状态轮询不再重复请求同一图片。
- 保留r5全部CPU与首页修复，内核和驱动沿用同一构建。

## 验证与出厂数据

完整镜像完成板型、FIT/DTB、内核ABI、闭源驱动、原登录页、资源内容、用户态、离线仓库和个人数据检查，具体结果见`VERIFICATION.json`。同一图标修复已在当前Ultra实机安装并通过浏览器验收。

本版完整镜像的硬件启动与恢复出厂待验收，按预发布提供。持续几分钟的卡顿仍待现场采样。

公开镜像使用通用配置，不含个人密码、订阅、SSH身份、Cloudflare/PushPlus凭据或短信/媒体数据。ROM内的通用功能和修复在恢复出厂后保留。

离线仓库解压至`/overlay/ultra-packages/`，运行`ultra-package-feeds`和`opkg update`。
