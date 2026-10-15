# 完整固件：Ultra25.12 r4 — 2026-10-15

适用设备：NRadio-C2000MAX-Ultra。基线为ImmortalWrt25.12-SNAPSHOT、Linux6.12.103、联发科闭源Wi-Fi8.3.1.2与巴龙WebUI3.0.2-r2。

本版在r3上集成网口管理、AT字段清洗与界面显示修复，并保留原登录页、5G、UPnP/IPv6、设备统计和资源管理补丁。

| 文件 | 用途 |
| --- | --- |
| `ultra-25.12-20261015-r4-nradio-c2000ultra-sysupgrade.bin` | 内核和完整根文件系统，通过兼容Ultra TF系统的升级入口安装。 |
| `ultra-25.12-20261015-r4-optional-packages.tar.gz` | 与本版匹配的可选离线软件仓库。 |

布局兼容号2.0，根分区内预留512MiB。安装步骤见[完整固件安装](../../docs/INSTALL.md)。已有Ultra25.12系统也可选择[维护升级包](../ultra-maintenance-20261015-1/README.md)。

## 新增功能

- 网口1可切换WAN/LAN，支持DHCP、PPPoE、静态IPv4，90秒内确认设置。
- 上级网关接入提示，居中卡片弹窗，适配手机。
- AT应答分离异步上报，校验型号和IMEI，清理异常缓存值。
- 侧栏完整显示型号，按词换行。

## 验证状态

完整镜像已通过板型、FIT/DTB、内核ABI、布局、驱动、原登录页、包内容、用户态与隐私检查，具体数量见`VERIFICATION.json`。同一维护更新已在生产路由器完成安装和网口切换验收。

本版为预发布，完整镜像的硬件启动与恢复出厂仍待验收。

## 出厂数据

镜像采用通用配置，不含个人密码、SSH身份、订阅、域名、转发凭据、短信/媒体数据或设备校准。恢复出厂后，ROM内的通用功能和修复保留，个人配置重新设置。

可选仓库解压到`/overlay/ultra-packages/`后运行`ultra-package-feeds`和`opkg update`，仓库标签与本固件对应。内置程序可直接使用。
