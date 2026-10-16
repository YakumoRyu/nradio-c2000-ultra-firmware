# 完整固件：Ultra25.12 r5 — 2026-10-16

适用设备：NRadio-C2000MAX-Ultra。本版将CPU周期检查、首页状态与JSON解析修复编入完整根文件系统，并保留r4网口管理、AT字段清洗、侧栏显示及原登录页面。

| 组件 | 版本 |
| --- | --- |
| 系统 | ImmortalWrt25.12-SNAPSHOT |
| 内核 | Linux6.12.103 |
| Wi-Fi | 联发科闭源8.3.1.2 |
| 巴龙WebUI | 3.0.2-r2 |
| 布局 | 兼容号2.0，根分区预留512MiB |

## 下载与安装

| 文件 | 用途 |
| --- | --- |
| `ultra-25.12-20261016-r5-nradio-c2000ultra-sysupgrade.bin` | 内核与完整根文件系统，在本项目Ultra TF系统中升级。 |
| `ultra-25.12-20261016-r5-optional-packages.tar.gz` | 与本版匹配的离线软件仓库。 |

步骤见[完整固件安装](../../docs/INSTALL.md)。现有r4系统可选择[CPU修复升级包](../ultra-cpu-hotfix-20261016-1/README.md)。

## 本次更新

- 减少5G每分钟自愈检查创建的进程，保留原AT锁清理与故障恢复逻辑。
- 首页使用共享CPU采样和原生状态读取，取消请求内等待，页面隐藏时暂停轮询。
- 修复普通LAN布局下旧PCDN独立接口引起的JSON报错。
- 既有5G、闭源Wi-Fi、UPnP/IPv6、设备统计、短信共享存储和媒体资源管理继续集成。

## 验证与出厂数据

本版完成镜像内容、板型、FIT/DTB、内核ABI、驱动、原登录页、用户态和个人数据检查，具体结果见`VERIFICATION.json`。新增修复文件与已安装实机逐字节比对。

完整镜像的硬件启动与恢复出厂测试待执行，按预发布提供。持续几分钟的卡顿仍待故障现场采样。

镜像使用通用出厂配置，个人密码、订阅、SSH身份、Cloudflare/PushPlus凭据和短信/媒体数据均由用户单独保存。恢复出厂后ROM中的程序与修复保留，个人配置重新设置。

离线仓库解压到`/overlay/ultra-packages/`，运行`ultra-package-feeds`和`opkg update`。
