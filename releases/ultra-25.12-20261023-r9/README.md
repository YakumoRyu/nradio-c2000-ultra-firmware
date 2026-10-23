# Ultra25.12 r9完整固件

版本：`ultra-25.12-20261023-r9`。

基线为ImmortalWrt25.12-SNAPSHOT、Linux6.12.103、联发科闭源Wi-Fi8.3.1.2和巴龙WebUI3.0.2-r2。本次将媒体保护超时、分步恢复、重启状态保存和Emby内存水位修复编入ROM。

下载文件：

- `ultra-25.12-20261023-r9-nradio-c2000ultra-sysupgrade.bin`：完整系统，约206MiB。
- `ultra-25.12-20261023-r9-optional-packages.tar.gz`：配套离线软件仓库。
- `VERIFICATION.json`：镜像、运行与公开产物检查记录。

镜像采用通用出厂配置。原登录页、5G、闭源无线、短信共享后台、UPnP/IPv6、网口管理和现有修复集成在系统中。r9与r8的差异为两个媒体保护文件和两个版本/软件仓库标识文件。

媒体保护补丁已在线运行，媒体库和内外网视频分段读取通过；完整镜像已完成解包、文件差异与用户态检查，整镜像启动和恢复出厂验收待执行，本Release设为预发布。

安装步骤见[完整固件安装](../../docs/INSTALL.md)。当前系统只安装补丁可使用[保留配置升级包](../ultra-maintenance-20261023-2/README.md)。
