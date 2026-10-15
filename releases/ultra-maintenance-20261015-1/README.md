# Ultra维护升级包 — 2026-10-15

在现有NRadio-C2000MAX-Ultra的Ultra25.12 TF系统上安装本次维护更新，保留个人配置。

## 内容

- 网口1的WAN/LAN切换，支持DHCP、PPPoE和静态IPv4。
- 检测上级网关后的接入提示，点击后进入上网方式设置。
- 应用配置后90秒内确认，到期自动回退。
- 居中卡片弹窗、模糊背景、渐变图标和紫色主按钮。
- 分离异步流量上报与模组AT应答，修复型号、IMEI异常显示。
- 修复侧栏型号断字，适配手机布局。
- 附带上一版QModem连续异常计数修复包，已有修复继续保留。

## 安装

下载`ultra-maintenance-20261015-1-upgrade.tar.gz`，上传到路由器`/tmp`，执行：

```sh
tar -xzf /tmp/ultra-maintenance-20261015-1-upgrade.tar.gz -C /tmp
sh /tmp/ultra-maintenance-20261015-1/install.sh
```

安装器核对待更新文件，备份到`/overlay/ultra-hotfix-backups/`，随后安装网口管理组件。正常重启保留更新。完整r4将这些修复编入ROM，恢复出厂后仍保留通用功能。

网口设置位于**网络→网口切换**，首页网口1卡片也可打开。安装保持原网口角色；应用新设置后点击“保留更改”。网口2保持LAN，5G保持现有主出口。

## 回退

先在网口页面把1口切回LAN并确认，再在原解压目录执行：

```sh
python3 /tmp/ultra-maintenance-20261015-1/ultra-ui-hotfix.py rollback
opkg remove ultra-port-manager
```

显示补丁会从已校验备份恢复。独立QModem补丁的回退入口为`/usr/libexec/ultra-qmodem-hotfix rollback --activate`。

## 验证

已在运行中的Ultra安装。浏览器提交、身份校验、网口WAN/LAN切换与90秒自动回退通过；型号和15位IMEI读取正确，短信读/投递状态保持，5G、OpenClash、UPnP服务正常。

桌面和390px手机视口排版通过。切换观测期间网口持续在线，没有新增接口错误或丢包。具体记录见`VERIFICATION.json`。

待实测项目：物理有线上级设备的DHCP/PPPoE接入、真实新短信同时查看与转发。
