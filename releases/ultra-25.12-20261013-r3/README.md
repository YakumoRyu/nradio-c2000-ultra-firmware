# 完整固件：Ultra 25.12 — 20261013-r3

适用设备：NRadio-C2000MAX-Ultra。保持ImmortalWrt25.12-SNAPSHOT、Linux6.12.103、联发科闭源Wi-Fi驱动8.3.1.2和已验收的WebUI3.0.2-r2。

主文件`ultra-25.12-20261013-r3-nradio-c2000ultra-sysupgrade.bin`约205.93MiB，包含内核和完整根文件系统。本版本将QModem连续异常计数修复同时加入软件包和ROM，QModem包版本为3.4.0_rc3-r1.ultra3。

通过兼容的Ultra TF系统升级入口安装，布局兼容号2.0，根分区内预留512MiB。上传后完成板型与布局检查。

## 与独立升级包的区别

- 只修复现有系统且保留配置，使用[小型IPK升级包](https://github.com/YakumoRyu/nradio-c2000-ultra-firmware/releases/tag/ultra-qmodem-hotfix-20261013-1)。
- 需要整套新系统及恢复出厂后仍保留通用修复，选择本页sysupgrade；刷写前按[安装说明](../../docs/INSTALL.md)备份和核对兼容性。

新完整固件没有在生产路由器刷写；当前生产设备只安装了独立补丁。

## 可选离线软件仓库

`ultra-25.12-20261013-r3-optional-packages.tar.gz`提供本版可选软件包，内置程序可直接使用。只在本版固件中，将其解压到`/overlay/ultra-packages`，让该目录直接含有`RELEASE`和各软件源子目录，然后运行`ultra-package-feeds`和`opkg update`。仓库标签与固件版本对应。

## 验证状态与分享

新镜像的板型/FIT/DTB、内核模块ABI、512MiB布局、原登录页面、闭源驱动补丁、QModem源码及包版本检查通过；19项用户态检查通过，隐私检查覆盖7000个文件，无已知私人值命中。详见`VERIFICATION.json`。

完整镜像为预发布，待验收项目为实机刷写、启动和恢复出厂。

公开镜像不含个人密码、SSH身份、订阅、私人域名、PushPlus/Cloudflare凭据、短信/媒体数据库或设备校准。恢复出厂会清理个人可写配置，ROM内的通用程序与修复保留。原登录页面及此前Wi-Fi、5G、UPnP/IPv6、设备统计和资源保护补丁保持。
