# 完整固件：Ultra25.12 r8 — 2026-10-23

NRadio-C2000MAX-Ultra；ImmortalWrt25.12、Linux6.12.103、联发科闭源Wi-Fi8.3.1.2、巴龙WebUI3.0.2-r2。

本版将SIM号码解析、短信单一管理入口、系统切换按钮和LTE SINR修复集成到ROM，保留r7全部修复及原登录页。QModem和短信LuCI软件包一同重编，匹配离线仓库。

| 文件 | 用途 |
| --- | --- |
| `ultra-25.12-20261023-r8-nradio-c2000ultra-sysupgrade.bin` | 当前Ultra TF系统的完整sysupgrade固件。 |
| `ultra-25.12-20261023-r8-optional-packages.tar.gz` | 与本版匹配的签名离线软件仓库。 |

布局兼容号2.0，根分区预留512MiB。[安装说明](../../docs/INSTALL.md)；已有r4/r5/r6/r7可用[保留配置升级包](../ultra-maintenance-20261023-1/README.md)。

1150实物对比与采用项见[对比记录](../../docs/MWRT1150_COMPARISON.md)。保留本项目25.12基线和原驱动；号码、短信与界面补丁已在实机验收。

完整镜像完成结构、ABI、内容差异、用户态、仓库及隐私检查；整镜像尚未刷写，作为预发布提供。实际切入官方系统和实机4G回落待验证。现场另记录一次约16:47的未确认原因重启。

公开镜像为通用出厂数据，个人号码、IMSI、密码、凭据、订阅、短信和媒体数据不进入产物。恢复出厂保留ROM修复并清理个人数据。
